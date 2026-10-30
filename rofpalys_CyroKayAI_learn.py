#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI learn: teach a voice detector what THIS song's singing sounds like, using the lyric timestamps as the teacher
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""WHY: the generic detector (rofpalys_CyroKayAI_ears.py) guesses 'voice' from pitch, voice band and stereo centre. It fails when the mix is dense
(a distorted guitar in the voice band, a wall of synths): it hears no voice at all. But the lyric file knows roughly where the voice is. That is
a (noisy) teacher: sounds under the sung lines = voice, sounds in the long silences between lines = no voice.

HOW (weak supervision, closed form, fast):
  1. FEATURES   per 20 ms frame: 24 band energies (spectral shape + loudness), pitch clarity, voice share, stereo centre, flatness, syllable
                modulation (2-8 Hz wobble of the voice band) -> standardised for this song and WHITENED (covariance = identity).
  2. FIND THE SHIFT  for every candidate shift of the lyrics (-20 .. +20 s, 0.1 s steps) measure how well 'lines vs silences' separate in the whitened
                feature space (between-class distance). At the right shift they separate best. The sharpness of that peak (how far above all the
                other shifts) says whether the lyrics belong to this recording at all.
  3. LEARN      Fisher / linear discriminant on the labelled frames -> one direction in feature space = 'this song's voice'; its score along the
                song, calibrated between the median of the silences and the median of the sung frames, is the learned vocal curve.
  4. REFINE     the lines are placed on the learned curve (per-line shifts, jumps, snapping - the solver in rofpalys_CyroKayAI_lyric.py), the labels
                are redrawn from the better placement, the detector is learned again (2 rounds).
  5. CHECK      held-out AUC: the detector is trained on 3/4 of the song and must separate lines from silences in the unseen quarter (4 blocked folds).
                A detector that only memorised the labels fails this. Confidence = fit x held-out AUC x peak sharpness. Lyrics of another song give a
                flat scan and AUC near 0.5, so their confidence is near zero.
  6. REMEMBER   the labelled frames of the CHOSEN fit are added (once per song) to a tally (rofpalys_CyroKayAI_memory.py); after a few songs the tally is a detector taught on your own
                music, used for songs without lyrics once it has proven it beats the generic one on songs it had not seen.
Honest limits: the label noise is real (breaths inside lines, ad-libs not in the lyrics), the guarantee is statistical, and only numpy makes this
possible (without numpy nothing here runs and the generic detector is used)."""
import math

try:
    import numpy as np
except Exception:
    np = None
import rofpalys_CyroKayAI_ears as EA
import rofpalys_CyroKayAI_text as TX
try:
    import rofpalys_CyroKayAI_memory as MEM
except Exception:
    MEM = None

__version__ = "1.0"
FPS = EA.FPS
MIN_PEAK_Z = 3.0                                    # a scan peak must stand this many standard deviations above the other shifts


def available():
    return np is not None


# ------------------------------------------------------------------ 1. features
def feature_matrix(F):
    """Frames x D matrix, robustly standardised for this song (median / inter-quartile range), smoothed over 140 ms. D = bands + 7."""
    lb = np.asarray(F["bands"], dtype=np.float64)
    mean = lb.mean(1, keepdims=True)
    cols = [lb - mean, mean]                                           # spectral shape without loudness, and loudness
    for k in ("pitch", "voice", "center"):
        cols.append(np.asarray(F[k], dtype=np.float64)[:, None])
    cols.append(np.log10(np.asarray(F["flat"], dtype=np.float64) + 1e-6)[:, None])
    env = np.asarray(F["venv"], dtype=np.float64)
    cols.append(env[:, None])
    hp = env - EA.smooth_np(env, 25)
    cols.append(np.sqrt(EA.smooth_np(hp * hp, 51))[:, None])           # syllable modulation: a voice wobbles 2-8 times per second
    X = np.concatenate(cols, 1)
    X = np.stack([EA.smooth_np(X[:, j], 7) for j in range(X.shape[1])], 1)
    med = np.median(X, 0)
    iqr = np.percentile(X, 75, 0) - np.percentile(X, 25, 0) + 1e-6
    return np.clip((X - med) / iqr, -6, 6)


def whiten(X):
    """(Z, prefix sums of Z): Z has identity covariance, so a plain distance in Z is the statistically right distance."""
    mu = X.mean(0)
    D = X.shape[1]
    C = np.cov((X - mu).T) + 1e-3 * np.eye(D)
    L = np.linalg.cholesky(C)
    Z = np.linalg.solve(L, (X - mu).T).T
    return Z, np.vstack([np.zeros(D), np.cumsum(Z, 0)])


# ------------------------------------------------------------------ 2. labels from the lyric lines
def label_spans(sung, dur):
    """(pa, pb, na, nb, po, no) in LYRIC time (seconds, numpy arrays). pos = under a sung line (0.25 s trimmed at both ends), neg = the silences the file is
    SURE about (rofpalys_CyroKayAI_text.silence_after / lead_silence: after a break line, the middle of a very long gap, the intro).
    po / no = index of the line each span belongs to. A gap that is only longer than our guess of the sung time is never used as 'silence'."""
    pa, pb, po, na, nb, no = [], [], [], [], [], []
    for i, it in enumerate(sung):
        a, b = it["t"] + 0.25, it["t"] + max(0.4, it["dur"] - 0.25)
        if b > a:
            pa.append(a)
            pb.append(b)
            po.append(i)
        g = TX.silence_after(sung, i, cap=20.0)
        if g:
            na.append(g[0])
            nb.append(g[1])
            no.append(i)
    g = TX.lead_silence(sung)
    if g:
        na.append(g[0])
        nb.append(g[1])
        no.append(0)
    return [np.asarray(x, dtype=np.float64) for x in (pa, pb, na, nb)] + [np.asarray(po, dtype=int), np.asarray(no, dtype=int)]


def _frames(x, shift, N):
    return np.clip(np.round((x + shift) * FPS).astype(int), 0, N)


def masks(spans, offs, N):
    """Boolean frame masks (pos, neg) for per-line offsets `offs` (seconds, one per sung line)."""
    pa, pb, na, nb, po, no = spans
    offs = np.asarray(offs, dtype=np.float64)
    out = []
    for a, b, o in ((pa, pb, po), (na, nb, no)):
        d = np.zeros(N + 2)
        if len(a):
            ia, ib = _frames(a, offs[o], N), _frames(b, offs[o], N)
            np.add.at(d, ia, 1)
            np.add.at(d, ib, -1)
        out.append(np.cumsum(d)[:N] > 0)
    return out[0], out[1]


# ------------------------------------------------------------------ 3. the shift scan (whitened between-class distance)
def scan_shift(PZ, N, spans, limit, step=0.1):
    """-> dict(shift, crit, z, ratio, shifts, crits). z = how many standard deviations the best shift stands above the others; ratio = best peak divided
    by the best peak at a clearly different shift (right lyrics: about 1.3 and more; unrelated lyrics: about 1.0-1.1)."""
    pa, pb, na, nb, _, _ = spans
    shifts = np.arange(-limit, limit + 1e-9, step)
    D = PZ.shape[1]
    crit = np.zeros(len(shifts))
    exp_pos = float((pb - pa).sum() * FPS)
    for k, s in enumerate(shifts):
        ia, ib = _frames(pa, s, N), _frames(pb, s, N)
        n1 = int((ib - ia).sum())
        ja, jb = _frames(na, s, N), _frames(nb, s, N)
        n0 = int((jb - ja).sum()) if len(na) else 0
        if n1 < 50 or n0 < 50:
            continue
        m1 = (PZ[ib] - PZ[ia]).sum(0) / n1
        m0 = (PZ[jb] - PZ[ja]).sum(0) / n0
        p = n1 / float(n1 + n0)
        crit[k] = p * (1 - p) * float(((m1 - m0) ** 2).sum()) * min(1.0, n1 / max(1.0, 0.7 * exp_pos)) ** 2
    if crit.max() <= 0:
        return {"shift": 0.0, "crit": 0.0, "z": 0.0, "ratio": 1.0, "shifts": shifts, "crits": crit}
    kb = int(crit.argmax())
    far = np.abs(shifts - shifts[kb]) > 1.5                            # compare with shifts that are clearly somewhere else
    rest = crit[far & (crit > 0)]
    z = float((crit[kb] - rest.mean()) / (rest.std() + 1e-9)) if len(rest) > 10 else 0.0
    ratio = float(crit[kb] / max(1e-9, rest.max())) if len(rest) else 1.0   # best peak / best peak somewhere else: ~1 = the lyrics fit anywhere equally (= nowhere)
    s = float(shifts[kb])
    if 0 < kb < len(shifts) - 1:                                       # parabola through the peak: finer than the 0.1 s grid
        y0, y1, y2 = crit[kb - 1], crit[kb], crit[kb + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            s += 0.5 * (y0 - y2) / den * step
    return {"shift": s, "crit": float(crit[kb]), "z": z, "ratio": ratio, "shifts": shifts, "crits": crit}


# ------------------------------------------------------------------ 4. the detector
def fit_lda(X, pos, neg, ridge=0.05):
    """Fisher discriminant: score = X @ w + b, higher = more like the sung frames. Returns None if a class is too small."""
    n1, n0 = int(pos.sum()), int(neg.sum())
    if n1 < 100 or n0 < 100:
        return None
    X1, X0 = X[pos], X[neg]
    m1, m0 = X1.mean(0), X0.mean(0)
    Sw = ((X1 - m1).T @ (X1 - m1) + (X0 - m0).T @ (X0 - m0)) / (n1 + n0) + ridge * np.eye(X.shape[1])
    try:
        w = np.linalg.solve(Sw, m1 - m0)
    except np.linalg.LinAlgError:
        return None
    return {"w": w, "b": float(-0.5 * w @ (m1 + m0))}


def to_curve(score, pos, neg, lo_q=50, hi_q=50):
    """Score along the song -> 0..1 vocal curve: 0 = typical silence, 1 = typical sung frame (medians), smoothed over 100 ms."""
    s0, s1 = float(np.percentile(score[neg], lo_q)), float(np.percentile(score[pos], hi_q))
    if s1 - s0 < 1e-6:
        return np.zeros(len(score))
    return np.clip((EA.smooth_np(score, 5) - s0) / (s1 - s0), 0, 1)


def auc(score, y):
    """Area under the ROC curve (rank statistic): 0.5 = chance, 1.0 = perfect separation. y is a boolean array."""
    y = np.asarray(y, dtype=bool)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return 0.5
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def heldout_auc(X, spans, offs, N, folds=4):
    """Train on all but one blocked quarter of the lines, test on that quarter (lines AND silences it contains). Mean AUC over the quarters, or None."""
    pa, pb, na, nb, po, no = spans
    offs = np.asarray(offs, dtype=np.float64)
    L = int(max(po.max() if len(po) else 0, no.max() if len(no) else 0)) + 1
    blk = np.minimum(folds - 1, (np.arange(L) * folds) // max(1, L))
    res = []

    def paint(a, b, o, flag):
        mk = np.zeros(N + 2)
        if flag.any():
            np.add.at(mk, _frames(a[flag], offs[o[flag]], N), 1)
            np.add.at(mk, _frames(b[flag], offs[o[flag]], N), -1)
        return np.cumsum(mk)[:N] > 0
    for f in range(folds):
        kp, kn = blk[po] == f, blk[no] == f
        tep, ten = paint(pa, pb, po, kp), paint(na, nb, no, kn)
        trp, trn = paint(pa, pb, po, ~kp) & ~(tep | ten), paint(na, nb, no, ~kn) & ~(tep | ten)
        m = fit_lda(X, trp, trn)
        if m is None or tep.sum() < 50 or ten.sum() < 50:
            continue
        ev = tep | ten
        res.append(auc((X @ m["w"])[ev], tep[ev]))
    return float(np.mean(res)) if res else None


# ------------------------------------------------------------------ 5. the whole learned fit of one lyric candidate
def learn_fit(F, sung, dur, limit, jumps_ok, solve, generic=None, stop=None):
    """Teach a detector on this song with the lyric lines as teacher and place the lines on it.
    F: numpy measurements (analysis.F).  solve(vocal_list, limit, jumps_ok) -> (line_offsets, info) places the lines on a vocal curve.
    generic: the generic vocal curve (to report how much better the learned one is).  Returns None when nothing consistent can be learned, else
    dict(curve, offs, info, learn, stats) with learn = {auc, z, ratio, shift0, gen_auc, mult, tag} (small, saved with the analysis) and stats = what
    remember() adds to the memory once this fit is the chosen one (big arrays, never saved)."""
    if np is None or F is None or "bands" not in F or len(sung) < 2:
        return None
    X = feature_matrix(F)
    N = len(X)
    Z, PZ = whiten(X)
    spans = label_spans(sung, dur)
    if len(spans[2]) == 0 or float((spans[3] - spans[2]).sum()) < 3.0:        # not enough certain silence to learn what 'no voice' sounds like
        return None
    sc = scan_shift(PZ, N, spans, limit)
    if sc["crit"] <= 0 or sc["z"] < MIN_PEAK_Z or (stop and stop()):
        return None
    offs = np.full(len(sung), sc["shift"])
    best = None
    for rnd in range(2):
        pos, neg = masks(spans, offs, N)
        m = fit_lda(X, pos, neg)
        if m is None:
            return None
        score = X @ m["w"] + m["b"]
        curve = to_curve(score, pos, neg)
        line_off, info = solve(curve.tolist(), limit, jumps_ok)
        best = (curve, line_off, info, pos, neg, m)
        offs = np.asarray(line_off, dtype=np.float64)
        if stop and stop():
            return None
    curve, line_off, info, pos, neg, m = best
    pos, neg = masks(spans, offs, N)                                   # labels at the final placement
    ho = heldout_auc(X, spans, offs, N)
    train_auc = auc((X @ m["w"])[pos | neg], pos[pos | neg])
    gen_auc = None
    if generic is not None and len(generic) == N:
        g = np.asarray(generic)
        ev = pos | neg
        gen_auc = auc(g[ev], pos[ev])
    # Proof, in three parts. The held-out AUC says the detector generalises (it is NOT proof of alignment: the solver may place any lyrics on a voice).
    # The proof of alignment is the scan: the lyric timing pattern must match the audio at ONE shift much better than at any other (z, ratio).
    a_term = EA.clamp(((ho if ho is not None else 0.5) - 0.65) / 0.25)
    z_term = EA.clamp((sc["z"] - MIN_PEAK_Z) / 3.0)
    r_term = EA.clamp((sc["ratio"] - 1.08) / 0.22)
    mult = 0.15 + 0.85 * min(a_term, z_term, r_term)
    learn = {"auc": round(ho, 3) if ho is not None else None, "train_auc": round(train_auc, 3), "z": round(sc["z"], 1), "ratio": round(sc["ratio"], 2),
             "shift0": round(sc["shift"], 2), "gen_auc": round(gen_auc, 3) if gen_auc is not None else None, "mult": round(mult, 3),
             "tag": "AUC %.2f, peak x%.2f" % (ho if ho is not None else 0.0, sc["ratio"])}
    stats = None
    if ho is not None and ho >= 0.7 and sc["z"] >= MIN_PEAK_Z + 1 and sc["ratio"] >= 1.2:           # only a convincing fit is worth remembering (the labels are noisy: AUC 0.7+ means a clearly learned voice)
        stats = {"X": X, "pos": pos, "neg": neg, "gen_auc": gen_auc}
    return {"curve": curve.tolist(), "offs": line_off, "info": info, "learn": learn, "stats": stats}


def remember(stats, sid=None):
    """Add what the CHOSEN fit of a song learned to the memory (once per song: fitting the same song again does not count twice). True if added."""
    if stats is None or MEM is None or np is None:
        return False
    try:
        if sid and MEM.seen(sid):
            return False
        X, pos, neg = stats["X"], stats["pos"], stats["neg"]
        gm = MEM.voice_model()                                          # judge the global detector on this song BEFORE it learns from it
        if gm is not None and stats.get("gen_auc") is not None:
            MEM.record_eval(stats["gen_auc"], auc((X @ gm[0] + gm[1])[pos | neg], pos[pos | neg]))
        ok = MEM.add_voice_stats(X, pos, neg, "learn")
        if ok and sid:
            MEM.mark_seen(sid)
        MEM.save()
        return ok
    except Exception:
        return False


# ------------------------------------------------------------------ 6. the detector taught on all songs (for songs without lyrics)
def global_curve(F):
    """0..1 vocal curve from the detector taught on every learned song, or None (not enough songs / not proven better than the generic one)."""
    if np is None or MEM is None or F is None or "bands" not in F or not MEM.use_global():
        return None
    gm = MEM.voice_model()
    if gm is None:
        return None
    w, b, c1, c0 = gm
    X = feature_matrix(F)
    if X.shape[1] != len(w):
        return None
    score = X @ w + b
    lo, hi = c0 + b, c1 + b                                             # where the class means of the tally sit on the score axis
    return np.clip((EA.smooth_np(score, 5) - lo) / max(1e-6, hi - lo), 0, 1).tolist()


def apply_global(A, blend=0.65):
    """Give a song WITHOUT usable lyric timing the detector taught on the user's own music (blended with the generic curve). True if applied."""
    if A is None or A.F is None or A.learn:
        return False
    g = global_curve(A.F)
    if g is None or len(g) != len(A.vocal):
        return False
    curve = [(1 - blend) * a + blend * b for a, b in zip(A.vocal, g)]
    A.use_curve(curve, {"tag": "own model", "auc": None})
    return True


# END-OF-FILE rofpalys_CyroKayAI_learn.py

