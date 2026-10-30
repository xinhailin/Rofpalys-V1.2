#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI ears: decode a song and measure it (loudness, voice band, pitch, notes, onsets, tempo) -> melody / singing curves
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The 'listening' half of CyroKayAI. Nothing here knows about lyrics.

  ffmpeg decodes the song -> every 20 ms (50 frames per second) it measures: loudness, how much of the sound sits in the voice band (250-3800 Hz),
  the pitch (f0 -> notes) and how clear it is, how flat the spectrum is, how centred the voice band is in the stereo picture, 24 band energies and the
  onset flux. From that come: a 'vocal activity' curve (0..1), SING / MELODY spans, onsets, tempo + beats and note events.

  v2: the Fourier work is split over all cores (rofpalys_CyroKayAI_turbo.py), the curves are computed vectorised, the 24 band energies are kept so
  the learning module (rofpalys_CyroKayAI_learn.py) can teach a detector what THIS song's voice sounds like.
Honest limits: this generic detector is a measurement heuristic (no neural network). It is good on clear vocals and weak on dense mixes - which is
exactly why the learning module exists. Without numpy a simpler detector (loudness + voice band) is used."""
import array
import base64
import bisect
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import zlib
from operator import mul

try:
    import numpy as np
except Exception:                                   # numpy is optional (Termux: pkg install python-numpy)
    np = None
try:
    import rofpalys_CyroKayAI_turbo as TB
except Exception:                                   # the turbo file is optional: single core then
    TB = None
try:
    import rofpalys_library as lib
except Exception:
    lib = None

__version__ = "3.0"
ALGO_N = 3
ALGO = "CyroKayAI/%d" % ALGO_N                      # written into the cache: an older cache (CyroKayAI/1 or none) is re-made once = the automatic deep reset
BRAND = "CyroKayAI %d" % ALGO_N                     # shown as the source of lyrics: "CyroKayAI 3 · syncedlyrics"
CACHE_ROOT = getattr(lib, "CACHE_DIR", None) or os.path.join(os.path.expanduser("~"), ".cache", "rofpalys")
CK_DIR = os.path.join(CACHE_ROOT, "cyrokay")
FPS = 50                                            # every curve has one value per 20 ms
STEP = 1.0 / FPS
MAX_SEC = 600                                       # longer files (DJ mixes) are analysed up to here (memory on a phone)
SR_NP, N_FFT, HOP_NP = 16000, 1024, 320             # numpy detector: 64 ms window, 20 ms step
SR_BASIC, HOP_BASIC = 8000, 160                     # basic detector (no numpy)
NBANDS = 24
ONSET_BIAS = -0.03                                  # a threshold crossing comes a little after the real start of a voice


def _envf(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def log(msg):
    if os.environ.get("ROFPALYS_DEBUG"):
        try:
            os.makedirs(CACHE_ROOT, exist_ok=True)
            with open(os.path.join(CACHE_ROOT, "cyrokay.log"), "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
        except OSError:
            pass


# ------------------------------------------------------------------ small maths helpers (plain Python; numpy makes the big ones fast)
def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def smoothstep(x, a, b):
    if b == a:
        return 1.0 if x >= b else 0.0
    t = clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def percentile(xs, p):
    if len(xs) == 0:
        return 0.0
    if np is not None and isinstance(xs, np.ndarray):
        return float(np.percentile(xs, p))
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def smooth(xs, w):
    """Zero-phase moving average over w frames (w odd): it does not move anything in time. (list in -> list out)"""
    n = len(xs)
    if w <= 1 or n == 0:
        return list(xs)
    if np is not None and n > 64:
        return smooth_np(np.asarray(xs, dtype=np.float64), w).tolist()
    h, pre = w // 2, [0.0]
    for x in xs:
        pre.append(pre[-1] + x)
    return [(pre[min(n, i + h + 1)] - pre[max(0, i - h)]) / float(min(n, i + h + 1) - max(0, i - h)) for i in range(n)]


def smooth_np(x, w):
    """numpy twin of smooth(): same edge handling (the window shrinks at the ends)."""
    n = len(x)
    if w <= 1 or n == 0:
        return x.copy()
    h = w // 2
    pre = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    i = np.arange(n)
    hi, lo = np.minimum(n, i + h + 1), np.maximum(0, i - h)
    return (pre[hi] - pre[lo]) / (hi - lo)


def median(xs):
    s = sorted(xs)
    return s[len(s) // 2] if s else 0.0


def fmt_t(t):
    t = max(0.0, t)
    return "%d:%05.2f" % (int(t // 60), t % 60)


def pack_curve(v):
    """list of floats 0..1 -> short text (1 byte per frame, deflated, base64). A 5 minute curve takes about 6 KB instead of 100 KB."""
    raw = bytes(int(round(clamp(x) * 255)) for x in v)
    return base64.b64encode(zlib.compress(raw, 6)).decode("ascii")


def unpack_curve(s):
    raw = zlib.decompress(base64.b64decode(s))
    return [b / 255.0 for b in raw]


# ------------------------------------------------------------------ listening: decode + per-frame measurements
def _pcm(path, sr, channels, filt=None, timeout=300):
    """Decode with ffmpeg to signed 16 bit little endian samples (array('h')), or None."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    cmd = [exe, "-v", "error", "-nostdin", "-threads", "0", "-i", path, "-vn", "-t", str(MAX_SEC), "-ac", str(channels), "-ar", str(sr)]
    if filt:
        cmd += ["-af", filt]
    cmd += ["-f", "s16le", "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL).stdout
    except Exception:
        return None
    if len(out) < sr * channels * 2:                # less than a second: nothing to measure
        return None
    a = array.array("h")
    a.frombytes(out[:len(out) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return a


def _windows(x, n, hop):
    if hasattr(np.lib.stride_tricks, "sliding_window_view"):
        return np.lib.stride_tricks.sliding_window_view(x, n)[::hop]
    st = x.strides[0]
    return np.lib.stride_tricks.as_strided(x, shape=((len(x) - n) // hop + 1, n), strides=(hop * st, st))


def _khz(hz):
    return int(round(hz * N_FFT / float(SR_NP)))


def _consts():
    v0, v1, p0, p1 = _khz(250), _khz(3800), _khz(60), _khz(3000)
    edges = np.unique(np.round(np.geomspace(_khz(60), _khz(7000), NBANDS + 1)).astype(int))
    return {"v0": v0, "v1": v1, "p0": p0, "p1": p1, "edges": edges, "minlag": int(SR_NP / 800.0), "maxlag": int(SR_NP / 80.0),
            "win": np.hanning(N_FFT).astype(np.float32)}


def _block(mv, sv, s, e, C):
    """All measurements for frames s..e-1 (independent of every other frame, so blocks can run on different cores)."""
    win, v0, v1, p0, p1, edges, minlag, maxlag = C["win"], C["v0"], C["v1"], C["p0"], C["p1"], C["edges"], C["minlag"], C["maxlag"]
    wsum = float((win * win).sum())
    m = e - s
    fr, sf = mv[s:e] * win, sv[s:e] * win
    X = np.fft.rfft(fr, axis=1)
    P = X.real * X.real + X.imag * X.imag
    tot = P.sum(1) + 1e-12
    out = {}
    out["rms"] = np.sqrt((fr * fr).sum(1) / wsum + 1e-14)
    XS = np.fft.rfft(sf, axis=1)
    pm, psd = P[:, v0:v1].sum(1), (XS.real * XS.real + XS.imag * XS.imag)[:, v0:v1].sum(1)
    out["center"] = pm / (pm + psd + 1e-12)                       # how centred the VOICE BAND is (voices sit in the middle of the stereo picture)
    out["voice"] = pm / tot
    vb = P[:, v0:v1] + 1e-12
    out["flat"] = np.exp(np.log(vb).mean(1)) / vb.mean(1)
    out["venv"] = np.log10(pm + 1e-9)
    out["bands"] = np.add.reduceat(P[:, :edges[-1]], edges[:-1], axis=1)
    pc = np.sqrt(P) ** 0.67                                        # compressed spectrum -> autocorrelation = pitch
    pc[:, :p0] = 0
    pc[:, p1:] = 0
    ac = np.fft.irfft(pc, n=N_FFT, axis=1)[:, :maxlag + 2]
    ac = ac / (ac[:, :1] + 1e-12)
    seg = ac[:, minlag:maxlag + 1]
    mx = seg.max(1)
    loc = np.zeros(seg.shape, dtype=bool)
    loc[:, 1:-1] = (seg[:, 1:-1] >= seg[:, :-2]) & (seg[:, 1:-1] >= seg[:, 2:])
    cand = loc & (seg >= 0.85 * mx[:, None])                       # the first strong peak: avoids octave-down mistakes
    idx = np.where(cand.any(1), cand.argmax(1), seg.argmax(1))
    rows, last = np.arange(m), seg.shape[1] - 1
    y1, y0, y2 = seg[rows, idx], seg[rows, np.clip(idx - 1, 0, last)], seg[rows, np.clip(idx + 1, 0, last)]
    den = y0 - 2 * y1 + y2
    sh = np.where(np.abs(den) > 1e-9, 0.5 * (y0 - y2) / np.where(np.abs(den) > 1e-9, den, 1.0), 0.0)
    out["pitch"] = np.clip(y1, 0, 1)
    out["f0"] = SR_NP / (minlag + idx + np.clip(sh, -1, 1))
    return out


def extract_np(a, stop=None, nworkers=None):
    """Full detector. -> dict of numpy arrays, one value per 20 ms frame: rms, voice, flat, pitch, f0, center, venv, flux, bands (frames x 24, power)."""
    x = np.frombuffer(a, dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
    n2 = len(x) // 2
    left, right = x[0:2 * n2:2], x[1:2 * n2:2]
    mid, side = (left + right) * 0.5, (left - right) * 0.5
    nfr, pad = len(mid) // HOP_NP + 1, N_FFT // 2
    mv = _windows(np.pad(mid, (pad, N_FFT + HOP_NP)), N_FFT, HOP_NP)[:nfr]
    sv = _windows(np.pad(side, (pad, N_FFT + HOP_NP)), N_FFT, HOP_NP)[:nfr]
    C = _consts()
    blocks = [(s, min(nfr, s + 512)) for s in range(0, nfr, 512)]
    nw = nworkers or (TB.workers() if TB is not None else 1)

    def run(b):
        if stop and stop():
            return None
        return _block(mv, sv, b[0], b[1], C)
    parts = TB.parallel_map(run, blocks, "thread", nw, stop) if (TB is not None and nw > 1 and len(blocks) > 1) else [run(b) for b in blocks]
    if any(p is None for p in parts) or (stop and stop()):
        return None
    res = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    lb = np.log10(res["bands"] + 1e-9)
    lb = np.maximum(lb, lb.max() - 8.0)
    res["flux"] = np.maximum(np.diff(lb, axis=0, prepend=lb[:1]), 0).sum(1) / lb.shape[1]
    res["bands"] = lb.astype(np.float32)                           # log10 power per band: the learning module's raw material
    res["n_samples"] = len(mid)
    return res


def _features_basic(path, stop=None):
    """Simple detector without numpy: loudness and the voice band (250-3800 Hz) through ffmpeg filters."""
    full = _pcm(path, SR_BASIC, 1)
    if full is None or (stop and stop()):
        return None
    voice = _pcm(path, SR_BASIC, 1, "highpass=f=250,lowpass=f=3800")
    if voice is None:
        return None

    def frame_rms(a):
        out, h = [], HOP_BASIC // 2
        for i in range(len(a) // HOP_BASIC + 1):
            seg = a[max(0, i * HOP_BASIC - h):i * HOP_BASIC + h]
            out.append(math.sqrt(sum(map(mul, seg, seg)) / max(1, len(seg))) / 32768.0 if len(seg) else 0.0)
        return out
    rf, rv = frame_rms(full), frame_rms(voice)
    n = min(len(rf), len(rv))
    rf, rv = rf[:n], rv[:n]
    vshare = [clamp((rv[i] * rv[i]) / (rf[i] * rf[i] + 1e-12)) for i in range(n)]
    db = [20 * math.log10(r + 1e-6) for r in rf]
    flux = [0.0] + [max(0.0, db[i] - db[i - 1]) for i in range(1, n)]
    return {"rms": rf, "voice": vshare, "flux": flux, "flat": None, "pitch": None, "f0": None, "center": None, "n_samples": len(full)}


# ------------------------------------------------------------------ from measurements to meaning: voice curve, SING / MELODY spans, onsets, tempo, notes
def _sstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def vocal_curve(F, energy):
    """0..1 per frame: how much this moment sounds like a voice that sings (pitched + voice band + moving pitch + centred in the stereo image).
    This is the GENERIC detector; the learning module replaces it by one taught on the song itself."""
    ce = F.get("center")
    ps = F.get("pitch")
    n = len(F["rms"])
    if np is not None and ps is not None and isinstance(F["rms"], np.ndarray):
        voice, fl, f0 = F["voice"], F["flat"], F["f0"]
        use_center = ce is not None and np.percentile(ce, 50) < 0.97 and np.percentile(ce, 90) - np.percentile(ce, 10) > 0.06
        valid = (ps > 0.4) & (f0 > 70) & (f0 < 1100)
        cur = np.where(valid, 69 + 12 * np.log2(np.maximum(f0, 1.0) / 440.0), 0.0)
        motion = np.zeros(n)
        both = valid[1:] & valid[:-1]
        motion[1:] = np.where(both, np.minimum(np.abs(cur[1:] - cur[:-1]), 1.5) / 1.5, 0.0)       # a voice glides and vibrates; a synth or a piano key does not
        motion = smooth_np(motion, 15)
        en = np.asarray(energy, dtype=np.float64)
        x = (_sstep(ps, 0.28, 0.58) * (0.5 + 0.5 * _sstep(voice, 0.4, 0.75)) * (0.7 + 0.3 * (1 - _sstep(fl, 0.12, 0.5))) * (0.65 + 0.35 * _sstep(motion, 0.02, 0.15)))
        if use_center:
            x = x * (0.7 + 0.3 * _sstep(ce, 0.5, 0.9))
        x = x * _sstep(en, 0.02, 0.15)
        sm = smooth_np(x, 9)
        lo, hi = np.percentile(sm, 20), np.percentile(sm, 93)
        rel = np.clip((sm - lo) / (hi - lo), 0, 1) if hi - lo > 0.05 else np.zeros(n)
        return (0.5 * rel + 0.5 * np.clip((sm - 0.10) / 0.40, 0, 1)).tolist()
    voice, fl, f0 = F["voice"], F.get("flat"), F.get("f0")
    use_center = bool(ce) and percentile(ce, 50) < 0.97 and percentile(ce, 90) - percentile(ce, 10) > 0.06
    motion = [0.0] * n
    if ps:
        prev = None
        for i in range(n):
            cur = 69 + 12 * math.log2(f0[i] / 440.0) if (ps[i] > 0.4 and 70 < f0[i] < 1100) else None
            if cur is not None and prev is not None:
                motion[i] = min(abs(cur - prev), 1.5) / 1.5
            prev = cur
        motion = smooth(motion, 15)
    s = []
    for i in range(n):
        if ps:
            x = (smoothstep(ps[i], 0.28, 0.58) * (0.5 + 0.5 * smoothstep(voice[i], 0.4, 0.75)) * (0.7 + 0.3 * (1 - smoothstep(fl[i], 0.12, 0.5)))
                 * (0.65 + 0.35 * smoothstep(motion[i], 0.02, 0.15)))
            if use_center:
                x *= 0.7 + 0.3 * smoothstep(ce[i], 0.5, 0.9)
        else:
            x = smoothstep(voice[i], 0.3, 0.75)
        s.append(x * smoothstep(energy[i], 0.02, 0.15))
    sm = smooth(s, 9)
    lo, hi = percentile(sm, 20), percentile(sm, 93)
    rel = [clamp((x - lo) / (hi - lo)) for x in sm] if hi - lo > 0.05 else [0.0] * n
    return [0.5 * r + 0.5 * clamp((x - 0.10) / 0.40) for r, x in zip(rel, sm)]


def sing_segments(v, on=0.6, off=0.4, min_len=0.5, fill=0.45):
    """Hysteresis: a span starts when the curve passes `on`, but its start is moved back to where it first rose above `off`."""
    n, segs, state, start = len(v), [], False, 0
    for i, x in enumerate(v):
        if not state and x >= on:
            j = i
            while j > 0 and v[j - 1] >= off:
                j -= 1
            state, start = True, j
        elif state and x < off:
            segs.append([start * STEP, i * STEP])
            state = False
    if state:
        segs.append([start * STEP, n * STEP])
    merged = []
    for a, b in segs:                                                    # a breath between two words is not the end of a phrase
        if merged and a - merged[-1][1] < fill:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= min_len]


def onset_list(flux):
    """[(seconds, strength)] where something new starts (a note, a syllable, a drum hit)."""
    n = len(flux)
    if n < 5:
        return []
    p95 = percentile(flux, 95) or 1e-9
    f = [min(2.0, x / p95) for x in flux]
    loc = smooth(f, 51)
    out = []
    for i in range(2, n - 2):
        x = f[i]
        if x >= f[i - 1] and x >= f[i + 1] and x > f[i - 2] and x >= f[i + 2] and x > loc[i] * 1.4 + 0.12:
            if out and i * STEP - out[-1][0] < 0.06:
                if x > out[-1][1]:
                    out[-1] = (i * STEP, x)
                continue
            out.append((i * STEP, x))
    return out


def tempo_beats(flux):
    """(bpm, [beat seconds], strength). A beat grid from autocorrelation of the onset curve, followed by a small tracker that stays on the real hits."""
    n = len(flux)
    if n < FPS * 8:
        return 0.0, [], 0.0
    mu = sum(flux) / n
    f = smooth([x - mu for x in flux], 3)
    best, best_l, acs = -1e9, 0, {}
    if np is not None:
        fa = np.asarray(f)
        for lag in range(15, 51):                                        # 200 .. 60 bpm
            acs[lag] = float(np.dot(fa[:n - lag], fa[lag:]) / (n - lag))
    else:
        for lag in range(15, 51):
            acs[lag] = sum(map(mul, f[:n - lag], f[lag:])) / (n - lag)
    for lag in range(15, 51):
        bpm = 60.0 * FPS / lag
        w = math.exp(-0.5 * (math.log2(bpm / 115.0) / 0.9) ** 2)
        if acs[lag] * w > best:
            best, best_l = acs[lag] * w, lag
    if best <= 0:
        return 0.0, [], 0.0
    a0, a1, a2 = acs.get(best_l - 1, acs[best_l]), acs[best_l], acs.get(best_l + 1, acs[best_l])
    den = a0 - 2 * a1 + a2
    period = best_l + (0.5 * (a0 - a2) / den if abs(den) > 1e-12 else 0.0)
    fl = [max(0.0, x) for x in flux]

    def at(pos):
        i = int(pos)
        return fl[i] + (fl[min(n - 1, i + 1)] - fl[i]) * (pos - i) if 0 <= i < n - 1 else 0.0
    phase = max((sum(at(ph + k * period) for k in range(int((n - ph) / period))), ph) for ph in [x * 0.5 for x in range(int(period * 2))])[1]
    beats, pos, w = [], phase, max(1.0, period * 0.15)
    mean_fl = sum(fl) / n
    while pos < n - 1:
        lo, hi = int(max(0, pos - w)), int(min(n - 1, pos + w))
        j = max(range(lo, hi + 1), key=lambda k: fl[k]) if hi >= lo else int(pos)
        pos = 0.6 * pos + 0.4 * j if fl[j] > 0.3 * mean_fl else pos
        beats.append(pos * STEP)
        pos += period
    strength = (sum(at(b * FPS) for b in beats) / len(beats)) / (mean_fl + 1e-9) if beats else 0.0
    if strength < 1.25:                                                  # no clear beat (ambient, rubato): do not pretend
        return 0.0, [], strength
    return 60.0 * FPS / period, beats, strength


def note_events(F):
    """[(start, end, midi)] sung / played notes: a stable pitch for at least 100 ms (numpy detector only)."""
    ps, f0 = F.get("pitch"), F.get("f0")
    if ps is None or len(ps) == 0 or f0 is None:
        return []
    ps, f0 = (ps.tolist() if hasattr(ps, "tolist") else ps), (f0.tolist() if hasattr(f0, "tolist") else f0)
    n, notes, cur = len(ps), [], None

    def close(c):
        if c and c[1] - c[0] + 1 >= 5:
            notes.append((c[0] * STEP, (c[1] + 1) * STEP, int(round(median(c[2])))))
    for i in range(n):
        if ps[i] > 0.45 and 75 < f0[i] < 1000:
            x = 69 + 12 * math.log2(f0[i] / 440.0)
            if cur is None:
                cur = [i, i, [x]]
            elif abs(x - median(cur[2][-8:])) > 0.8:
                close(cur)
                cur = [i, i, [x]]
            else:
                cur[1] = i
                cur[2].append(x)
        elif cur is not None and i - cur[1] > 3:
            close(cur)
            cur = None
    close(cur)
    return notes


NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_name(m):
    return "%s%d" % (NOTE_NAMES[m % 12], m // 12 - 1)


class Analysis:
    """Everything CyroKayAI measured about one recording. Curves have one value per 20 ms."""

    def __init__(self):
        self.duration, self.engine, self.bpm, self.beat_strength, self.coverage = 0.0, "none", 0.0, 0.0, 0.0
        self.vocal, self.energy = [], []                                 # 0..1 per frame: singing-likeness / loudness relative to the song
        self.sing, self.onsets, self.beats, self.notes = [], [], [], []   # [(a, b)], [(t, strength)], [t], [(a, b, midi)]
        self.vocal0 = None                                               # the generic curve, kept when the learned one replaced `vocal`
        self.learn = None                                                # what the learning module found (dict) or None
        self.F = None                                                    # numpy measurements of this run (not saved; recomputed on demand by features())
        self.path = ""

    def frame(self, t):
        return int(clamp(int(round(t * FPS)), 0, max(0, len(self.vocal) - 1)))

    def mean_vocal(self, a, b):
        i, j = self.frame(a), max(self.frame(a) + 1, self.frame(b))
        seg = self.vocal[i:j]
        return sum(seg) / len(seg) if seg else 0.0

    def mean_energy(self, a, b):
        i, j = self.frame(a), max(self.frame(a) + 1, self.frame(b))
        seg = self.energy[i:j]
        return sum(seg) / len(seg) if seg else 0.0

    def onset_density(self, a, b):
        i, j = bisect.bisect_left(self.onsets, (a, -1)), bisect.bisect_left(self.onsets, (b, -1))
        return (j - i) / max(0.5, b - a)

    def melody_spans(self, min_len=0.0):
        """The complement of SING inside the song: [(a, b)]."""
        out, t = [], 0.0
        for a, b in self.sing:
            if a - t > min_len:
                out.append((t, a))
            t = b
        if self.duration - t > min_len:
            out.append((t, self.duration))
        return out

    def snap_beat(self, t, tol=0.12):
        if not self.beats:
            return t
        i = bisect.bisect_left(self.beats, t)
        c = [self.beats[k] for k in (i - 1, i) if 0 <= k < len(self.beats)]
        b = min(c, key=lambda x: abs(x - t)) if c else t
        return b if abs(b - t) <= tol else t

    def use_curve(self, curve, info=None):
        """Replace the generic voice curve by a better one (the learned one) and redo the SING / MELODY spans from it."""
        if self.vocal0 is None:
            self.vocal0 = self.vocal
        self.vocal = list(curve)
        self.sing = sing_segments(self.vocal)
        self.coverage = sum(b - a for a, b in self.sing) / max(1.0, self.duration)
        self.learn = info
        self._ref = None

    def use_generic(self):
        """Go back to the generic voice curve (undo use_curve): every new fit starts from the same ground."""
        if self.vocal0 is not None:
            self.vocal, self.vocal0 = self.vocal0, None
            self.sing = sing_segments(self.vocal)
            self.coverage = sum(b - a for a, b in self.sing) / max(1.0, self.duration)
        self.learn = None
        self._ref = None

    def features(self, stop=None):
        """The numpy measurements of this recording (bands etc.), listening again if this analysis came from the cache. None without numpy / ffmpeg."""
        if self.F is None and self.engine == "full" and self.path and np is not None:
            try:
                engine, F = _decode_features(self.path, stop)
                if engine == "full" and F is not None and len(F["rms"]) == len(self.vocal):
                    self.F = F
            except Exception as e:
                log("features failed: %r" % (e,))
        return self.F

    def to_dict(self):
        d = {"algo": ALGO, "duration": round(self.duration, 3), "engine": self.engine, "bpm": round(self.bpm, 2), "beat_strength": round(self.beat_strength, 2),
             "coverage": round(self.coverage, 3), "vocal_z": pack_curve(self.vocal), "energy_z": pack_curve(self.energy),
             "sing": [[round(a, 3), round(b, 3)] for a, b in self.sing], "onsets": [[round(t, 3), round(s, 2)] for t, s in self.onsets],
             "beats": [round(b, 3) for b in self.beats], "notes": [[round(a, 3), round(b, 3), m] for a, b, m in self.notes]}
        if self.vocal0 is not None:
            d["vocal0_z"] = pack_curve(self.vocal0)
        if self.learn:
            d["learn"] = self.learn
        return d

    @classmethod
    def from_dict(cls, d):
        A = cls()
        A.duration, A.engine, A.bpm, A.beat_strength, A.coverage = d["duration"], d["engine"], d["bpm"], d.get("beat_strength", 0.0), d["coverage"]
        A.vocal, A.energy = unpack_curve(d["vocal_z"]), unpack_curve(d["energy_z"])
        A.sing, A.onsets, A.beats = [tuple(x) for x in d["sing"]], [tuple(x) for x in d["onsets"]], list(d["beats"])
        A.notes = [tuple(x) for x in d["notes"]]
        if d.get("vocal0_z"):
            A.vocal0 = unpack_curve(d["vocal0_z"])
        A.learn = d.get("learn")
        return A

    def summary(self):
        mel = self.melody_spans(2.0)
        s = ("engine=%s  length=%s  singing=%d%%  tempo=%s  sing spans=%d  melody spans=%d  notes=%d" %
             (self.engine, fmt_t(self.duration), round(self.coverage * 100), ("%.0f bpm" % self.bpm) if self.bpm else "n/a", len(self.sing), len(mel), len(self.notes)))
        if self.learn:
            s += "  learned: %s" % self.learn.get("tag", "yes")
        return s


def akey(path):
    try:
        st = os.stat(path)
        raw = "%s|%d|%d|%s" % (os.path.abspath(path), st.st_size, int(st.st_mtime), ALGO)
    except OSError:
        raw = "%s|%s" % (os.path.abspath(path), ALGO)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:20]


def apath(key):
    return os.path.join(CK_DIR, "an_%s.json" % key)


def save_analysis(path, A):
    """Write (or rewrite, after learning) the analysis cache of this file."""
    try:
        os.makedirs(CK_DIR, exist_ok=True)
        p = apath(akey(path))
        with open(p + ".part", "w", encoding="utf-8") as f:
            json.dump(A.to_dict(), f, separators=(",", ":"))
        os.replace(p + ".part", p)
        return True
    except OSError:
        return False


def _decode_features(path, stop=None):
    """(engine, F, sample rate) - the measurements of this file, or (None, None, 0)."""
    F, engine = None, "none"
    if np is not None:
        a = _pcm(path, SR_NP, 2)
        if a is not None:
            F = extract_np(a, stop)
            engine = "full"
    if F is None and not (stop and stop()):
        F = _features_basic(path, stop)
        engine = "basic"
    return engine, F


def analyze(path, stop=None, use_cache=True, keep_features=False):
    """Listen to the song. Returns an Analysis, or None when it cannot be decoded (no ffmpeg, unreadable file). Cached per file.
    keep_features=True: a freshly made analysis keeps the numpy measurements in A.F (the learning module needs them; A.features() listens again
    when the analysis came from the cache)."""
    key = akey(path)
    if use_cache and os.path.isfile(apath(key)):
        try:
            with open(apath(key), encoding="utf-8") as f:
                d = json.load(f)
            if d.get("algo") == ALGO:
                A = Analysis.from_dict(d)
                A.path = path
                return A
        except (OSError, ValueError, KeyError, zlib.error):
            pass
    t0 = time.time()
    try:
        engine, F = _decode_features(path, stop)
    except Exception as e:                                               # a broken file must never take the player down
        log("analyze failed: %r" % (e,))
        engine, F = "none", None
    if not F or (stop and stop()):
        return None
    A = Analysis()
    A.path = path
    A.engine, A.duration = engine, F["n_samples"] / float(SR_NP if engine == "full" else SR_BASIC)
    if np is not None and engine == "full":
        db = 20 * np.log10(np.asarray(F["rms"], dtype=np.float64) + 1e-6)
        top = float(np.percentile(db, 99))
        A.energy = smooth_np(np.clip((db - (top - 40.0)) / 30.0, 0, 1), 5).tolist()
    else:
        db = [20 * math.log10(r + 1e-6) for r in F["rms"]]
        top = percentile(db, 99)
        A.energy = smooth([clamp((d - (top - 40.0)) / 30.0) for d in db], 5)
    A.vocal = vocal_curve(F, A.energy)
    A.sing = sing_segments(A.vocal)
    flux = F["flux"].tolist() if hasattr(F["flux"], "tolist") else F["flux"]
    A.onsets = onset_list(flux)
    A.bpm, A.beats, A.beat_strength = tempo_beats(flux)
    A.notes = note_events(F)
    A.coverage = sum(b - a for a, b in A.sing) / max(1.0, A.duration)
    if keep_features and engine == "full":
        A.F = F
    log("analyze %s: %s in %.1fs (workers %s)" % (os.path.basename(path), A.summary(), time.time() - t0, TB.workers() if TB else 1))
    if use_cache:
        save_analysis(path, A)
    return A


def has_ears(A):
    """True when A can really tell a voice from other sound (the numpy detector). The basic detector only knows loud / quiet."""
    return A is not None and A.engine in ("full", "selftest") and len(A.vocal) >= FPS * 5


# END-OF-FILE rofpalys_CyroKayAI_ears.py

