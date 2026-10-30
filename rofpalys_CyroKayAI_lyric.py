#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI: the brain of the lyrics (the maths: melody / note / singing measurement, creator detection, exact lyric timing, learning)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""CyroKayAI 3 - the brain of the lyrics. This file is the CONDUCTOR of the CyroKayAI files; the maths lives in the others:
  rofpalys_CyroKayAI_ears.py    listening: decode, 50 measurements per second, voice / melody curves, SING / MELODY spans, onsets, tempo, notes
  rofpalys_CyroKayAI_text.py    reading: syllables, how long a line takes to sing, which silences the lyric file is sure about, word times
  rofpalys_CyroKayAI_learn.py   learning: the lyric timestamps teach a detector what THIS song's voice sounds like (rescues dense mixes)
  rofpalys_CyroKayAI_memory.py  remembering: a voice model taught on your songs, your corrections (+/- 0.1 s), this device's delay
  rofpalys_CyroKayAI_turbo.py   speed: all processor cores, priority, benchmark
  rofpalys_CyroKayAI_clock.py   the song clock, the lyric timeline with word times, the Spotify-style scroll maths
  rofpalys_CyroKayAI_view.py    the Tk screen that draws it (rofpalys_gui_lyricview.py plugs it into the window)
  rofpalys_CyroKayAI_providers.py  fetching: syncedlyrics (first) -> lrcdl -> lyriq -> librelyrics, each judged by how well its lyrics fit the recording
Here: who made the song (tags, file name, folder -> iTunes / MusicBrainz), is the internet there, fetch lyrics, fit every line to the real voice
(Viterbi over time shifts, jumps for extra / missing sections, snapping to the voice onsets), melody markers (strong 🎶 / soft 🎵 on the beat),
the cut plan, the cache, the terminal commands (rofpalys lyrics ...).
Honest limits: no speech recognition and no neural network; the voice detector is a measurement heuristic that is taught per song from the lyric
timestamps. Confidence says how well the lines sit on the voice, not that the words are right."""
import bisect
import difflib
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import rofpalys_CyroKayAI_ears as EA                # the listening (decode, measure, melody / singing curves) - required
import rofpalys_CyroKayAI_text as TX                # the reading (syllables, sung length, where the file says the voice is silent, word times) - required
from rofpalys_CyroKayAI_text import syllables, est_sung, SYL_SEC
from rofpalys_CyroKayAI_ears import (FPS, STEP, MAX_SEC, ONSET_BIAS, ALGO, ALGO_N, BRAND, CACHE_ROOT, CK_DIR, np, clamp, smoothstep, percentile, smooth,
                                     median, fmt_t, log, Analysis, analyze, has_ears, midi_name, save_analysis, _envf)
try:
    import rofpalys_CyroKayAI_turbo as TB           # all cores
except Exception:
    TB = None
try:
    import rofpalys_CyroKayAI_learn as LRN          # the detector that learns the song
except Exception:
    LRN = None
try:
    import rofpalys_CyroKayAI_memory as MEM         # what was learned from your songs and corrections
except Exception:
    MEM = None
try:
    import rofpalys_CyroKayAI_providers as PV       # where lyrics come from: syncedlyrics -> lrcdl -> lyriq -> librelyrics
except Exception:
    PV = None
try:
    import rofpalys_library as lib
except Exception:
    lib = None

__version__ = "3.0"
OK_FIT = PV.OK if PV is not None else 0.35          # a fit below this = the lyrics do not belong to the recording
UA = "Rofpalys-CyroKayAI/" + __version__
MAX_SHIFT = 20.0                                    # lyric version may differ from the recording by up to +-20 s
LEAD_SEC = _envf("ROFPALYS_LYRIC_LEAD", 0.12)       # a line is shown this much EARLIER than the voice starts (reading takes time, like Spotify)
GAP_MIN = _envf("ROFPALYS_LYRIC_GAP", 3.0)          # a silence between two lines at least this long gets a melody marker


def _ly():
    import rofpalys_lyrics as LY                    # imported late: rofpalys_lyrics imports this file too
    return LY


# ------------------------------------------------------------------ who made this song? (tags + file name + folder, then the internet)
_GENERIC_DIRS = {"music", "musik", "download", "downloads", "songs", "song", "lagu", "audio", "media", "storage", "shared", "sdcard", "emulated", "0",
                 "rofpalys", "documents", "home", "root", "tmp", "mp3", "playlist", "playlists", "favorites", "favourites", "new folder", "termux"}
_JUNK = re.compile(r"[\(\[][^)\]]*(official|video|lyric|lyrics|audio|mv|hd|4k|visuali[sz]er|remaster(ed)?|karaoke|full song|music video)[^)\]]*[\)\]]", re.I)


def clean_artist(a):
    a = re.sub(r"\s*-\s*topic\s*$", "", a or "", flags=re.I)
    a = re.sub(r"(?i)\b(vevo|official( channel)?)\s*$", "", a)
    return re.sub(r"\s+", " ", a).strip(" -_")


def clean_title(t):
    t = _JUNK.sub("", t or "")
    t = re.sub(r"\s*[\(\[]\s*(feat\.?|ft\.?|featuring|with)\s[^)\]]*[\)\]]", "", t, flags=re.I)    # the featured artist is not part of the title
    t = re.sub(r"\s*\|.*$", "", t)
    return re.sub(r"\s+", " ", t).strip(" -_")


def _sim(a, b):
    return _ly()._sim(a, b)


def read_tags(path):
    """Embedded tags and length through ffprobe: {'artist', 'title', 'album', 'albumartist', 'duration'} (empty values when unknown)."""
    out = {"artist": "", "title": "", "album": "", "albumartist": "", "duration": 0.0}
    exe = shutil.which("ffprobe")
    if not exe or not os.path.isfile(path):
        return out
    try:
        r = subprocess.run([exe, "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
        fmt = json.loads(r.stdout.decode("utf-8", "replace")).get("format", {})
    except Exception:
        return out
    tags = {str(k).lower().replace("_", ""): str(v) for k, v in (fmt.get("tags") or {}).items()}
    for k in ("artist", "title", "album", "albumartist"):
        out[k] = tags.get(k, "").strip()
    try:
        out["duration"] = float(fmt.get("duration") or 0)
    except ValueError:
        pass
    return out


def name_candidates(path, tags=None):
    """[(artist, title, where it came from, trust 0..1)], best first. Tags are trusted most, the file name next, the folder name least."""
    tags = tags if tags is not None else read_tags(path)
    fa, ft = _ly().guess(path)
    ta, tt = clean_artist(tags.get("artist") or tags.get("albumartist") or ""), clean_title(tags.get("title") or "")
    fa, ft = clean_artist(fa), clean_title(ft)
    folder = clean_artist(os.path.basename(os.path.dirname(os.path.abspath(path))))
    out = []
    if ta and tt:
        out.append((ta, tt, "tags", 0.9))
    if ft:
        out.append((fa, ft, "file name", 0.6 if fa else 0.4))
    if fa and tt and not ta:
        out.append((fa, tt, "file artist + tag title", 0.55))
    if fa and ft:
        out.append((ft, fa, "file name (title - artist)", 0.3))             # many files are named the other way round
    if folder and folder.lower() not in _GENERIC_DIRS and (tt or ft):
        out.append((folder, tt or ft, "folder name", 0.25))
    seen, uniq = set(), []
    for a, t, src, w in sorted(out, key=lambda x: -x[3]):
        k = (re.sub(r"\W+", "", a.lower()), re.sub(r"\W+", "", t.lower()))
        if t and k not in seen:
            seen.add(k)
            uniq.append((a, t, src, w))
    return uniq


_NET = {"t": 0.0, "ok": False}


def internet_ok(force=False, timeout=4.0):
    """True when the lyric servers answer. Any answer counts (even 'not found'): the question is only whether the network is there."""
    if os.environ.get("ROFPALYS_OFFLINE"):
        return False
    now = time.time()
    if not force and now - _NET["t"] < 20:
        return _NET["ok"]
    ok = False
    for url in ("https://lrclib.net/", "https://itunes.apple.com/"):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD"), timeout=timeout):
                ok = True
        except urllib.error.HTTPError:
            ok = True
        except Exception:
            ok = False
        if ok:
            break
    _NET["t"], _NET["ok"] = now, ok
    return ok


def _itunes(artist, title):
    q = urllib.parse.urlencode({"term": ("%s %s" % (artist, title)).strip(), "media": "music", "entity": "song", "limit": 8})
    return [{"artist": x.get("artistName", ""), "title": x.get("trackName", ""), "album": x.get("collectionName", ""),
             "duration": (x.get("trackTimeMillis") or 0) / 1000.0, "source": "iTunes"} for x in _ly()._http("https://itunes.apple.com/search?" + q).get("results", [])]


def _musicbrainz(artist, title):
    query = 'recording:"%s"' % title.replace('"', "") + (' AND artist:"%s"' % artist.replace('"', "") if artist else "")
    q = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 6})
    out = []
    for r in _ly()._http("https://musicbrainz.org/ws/2/recording/?" + q).get("recording", []):
        credit = (r.get("artist-credit") or [{}])[0]
        out.append({"artist": credit.get("name") or (credit.get("artist") or {}).get("name", ""), "title": r.get("title", ""), "album": "",
                    "duration": (r.get("length") or 0) / 1000.0, "source": "MusicBrainz"})
    return out


def _rank(c, artist, title, duration):
    """0..1: how well an online record fits what we know. The song LENGTH is the strongest proof that it is the same recording."""
    s = 0.55 * _sim(title, c["title"]) + (0.30 * _sim(artist, c["artist"]) if artist else 0.15)
    if duration and duration > 0 and c.get("duration"):
        d = abs(duration - c["duration"])
        s += 0.15 if d <= 3 else 0.08 if d <= 8 else 0.0
    else:
        s += 0.05
    return s


def identify(path, duration=None, online=None, stop=None, hint=None):
    """Find out which artist made the song. -> dict(artist, title, album, source, verified, confidence, online, alts, duration).
    verified=True: an online record agrees on title + artist (+ length). Offline the best name from tags / file name is used and verified stays False."""
    tags = read_tags(path) if path and os.path.isfile(path) else {"duration": 0.0}
    duration = duration if duration and duration > 0 else tags.get("duration") or 0.0
    cands = name_candidates(path, tags) if path else []
    if hint and hint[1] and not any(_sim(hint[1], c[1]) > 0.85 for c in cands):          # what the caller already knows
        cands.insert(0, (clean_artist(hint[0]), clean_title(hint[1]), "caller", 0.7))
    res = {"artist": "", "title": "", "album": "", "source": "none", "verified": False, "confidence": 0.0, "online": False, "alts": [], "duration": duration}
    if not cands:
        return res
    a0, t0, src0, w0 = cands[0]
    res.update(artist=a0, title=t0, source=src0, confidence=round(w0 * 0.7, 2), alts=[(a, t) for a, t, _, _ in cands[1:]])
    online = internet_ok() if online is None else online
    res["online"] = online
    if not online:
        return res
    best = None
    for a, t, src, w in cands[:3]:
        if stop and stop():
            break
        for fn in (_itunes, _musicbrainz):
            try:
                found = fn(a, t)
            except Exception:
                found = []
            for c in found:
                sc = _rank(c, a, t, duration) + 0.05 * w
                if best is None or sc > best[0]:
                    best = (sc, c, src)
            if best and best[0] >= 0.85:
                break
        if best and best[0] >= 0.85:
            break
    if best and best[0] >= 0.72:
        sc, c, src = best
        res.update(artist=clean_artist(c["artist"]) or res["artist"], title=clean_title(c["title"]) or res["title"], album=c.get("album", ""),
                   source="%s (%s)" % (c["source"], src), verified=True, confidence=round(min(1.0, 0.55 + 0.45 * sc), 2))
        res["alts"] = [(a, t) for a, t, _, _ in cands if (a, t) != (res["artist"], res["title"])]
    return res


# ------------------------------------------------------------------ lyric text maths: syllables, sung length, line items
def is_break(text):
    return _ly().is_break_text(text or "")


def make_items(pairs):
    """[(start, text)] -> items {t, text, brk, dur}. A sung line ends where the next break starts (the file says the voice stops there)
    or after its estimated singing time, whichever comes first."""
    items = []
    for i, (t, text) in enumerate(pairs):
        brk = is_break(text)
        it = {"t": float(t), "text": "" if brk else text.strip(), "brk": brk, "dur": 0.0, "brk_after": False}
        if not brk:
            est = est_sung(text)
            nxt = pairs[i + 1] if i + 1 < len(pairs) else None
            if nxt is None:
                it["dur"] = est
            elif is_break(nxt[1]):
                it["brk_after"] = True
                it["dur"] = clamp(nxt[0] - t, 0.6, max(5.0, est * 2.5))
            else:
                it["dur"] = min(est, max(0.6, nxt[0] - t - 0.05))
        items.append(it)
    return items


# ------------------------------------------------------------------ melody markers: 🎶 strong music, 🎵 soft music, changing on the beat
def syms():
    LY = _ly()
    return LY.NOTE_HI, LY.NOTE_LO


def _ref_energy(A):
    if getattr(A, "_ref", None) is None:
        live = [x for x in A.energy if x > 0.05]
        A._ref = percentile(live, 50) if live else 0.5
        A._dens = len(A.onsets) / max(1.0, A.duration)
    return A._ref, A._dens


def _pick(A, a, b):
    hi, lo = syms()
    if A is None or not A.energy:
        return hi
    ref, dens = _ref_energy(A)
    e = A.mean_energy(a, b) + 0.04 * clamp(A.onset_density(a, b) - dens, -2.0, 2.0)      # busy rhythm counts a little as 'stronger'
    return hi if e >= ref else lo


def markers(A, a, b, force=False):
    """Melody lines [(time, symbol)] for the instrumental time a..b. A long span is cut into phrases of 8 beats and the symbol follows the
    loudness of each phrase; every boundary is moved onto the nearest beat."""
    if b - a < 0.4:
        return []
    if A is None or not A.energy or (b - a < 14.0 and not force):
        return [(a, _pick(A, a, b))]
    step = clamp(8 * 60.0 / A.bpm if A.bpm else 6.4, 4.0, 9.0)
    cuts, t = [a], a + step
    while b - t >= 3.0:
        cuts.append(A.snap_beat(t))
        t += step
    out = []
    for x, y in zip(cuts, cuts[1:] + [b]):
        s = _pick(A, x, y)
        if not out or out[-1][1] != s:
            out.append((x, s))
    return out


def _own_model(A):
    """A song without usable lyric timing: the detector taught on the user's own songs (rofpalys_CyroKayAI_memory), blended with the generic one - but
    only once it has proven on songs it had not seen that it is better. True if it was applied."""
    try:
        if LRN is None or MEM is None or A is None or A.engine != "full" or not LRN.available() or not MEM.use_global():
            return False
        return bool(A.features() is not None and LRN.apply_global(A))
    except Exception as e:
        log("own model failed: %r" % (e,))
        return False


def melody_track(A):
    """A song without lyrics: a melody-only track that follows the music. Where the ears hear a SINGING voice (no words known) the soft 🎵 shows; where only
    the music plays (intro, solo, instrumental) a phrase-by-phrase 🎶 / 🎵 follows the loudness and the beat. The marker changes at the moment the voice enters or
    leaves; a breath between two phrases (< 3 s) does not. Without the numpy ears the whole song is one phrase-by-phrase track."""
    if A is None or not A.energy:
        return [(0.0, syms()[0])]
    _own_model(A)
    if not has_ears(A) or not A.sing:
        return markers(A, 0.0, A.duration, force=True)
    voiced = []
    for a, b in A.sing:
        if voiced and a - voiced[-1][1] < 3.0:
            voiced[-1] = (voiced[-1][0], b)
        else:
            voiced.append((a, b))
    voiced = [(a, b) for a, b in voiced if b - a >= 1.5]
    segs, t = [], 0.0
    for a, b in voiced:
        if a - t >= 0.4:
            segs.append((t, a, False))
        segs.append((a, b, True))
        t = b
    if A.duration - t >= 0.4:
        segs.append((t, A.duration, False))
    out = []
    for a, b, sing in segs:
        for item in ([(a, syms()[1])] if sing else markers(A, a, b, force=True)):
            if not out or out[-1][1] != item[1]:
                out.append(item)
    return out or [(0.0, syms()[0])]


# ------------------------------------------------------------------ fitting lyric lines to the recording
def _prefix(v):
    p, acc = [0.0], 0.0
    for x in v:
        acc += x
        p.append(acc)
    return p


def _gscore(P, n, ivs, gaps, gm):
    """Evidence for one lyric group at one shift (-1..1): the voice that is there UNDER its lines minus the voice that is there where the lyrics say
    nobody sings (a real gap between lines, the silence before / after the group). Without such a gap the average voice of the song is the baseline."""
    def at(i):
        return P[0 if i < 0 else n if i > n else i]
    si = li = sg = lg = 0.0
    for a, b in ivs:
        ia, ib = int(round(a * FPS)), int(round(b * FPS))
        si += at(ib) - at(ia)
        li += ib - ia
    if li < 10:
        return 0.0
    for a, b in gaps:
        ia, ib = int(round(a * FPS)), int(round(b * FPS))
        if ib > ia:
            sg += at(ib) - at(ia)
            lg += ib - ia
    return si / li - (sg / lg if lg >= 20 else gm)


def _gscore_vec(P, n, ivs, gaps, gm, offs):
    """_gscore for MANY shifts at once (numpy; P a numpy prefix-sum array, offs an array of shifts in seconds) -> array. Same numbers, ~50x faster."""
    offs = np.asarray(offs, dtype=np.float64)

    def span_sums(spans):
        if not spans:
            return np.zeros(len(offs)), np.zeros(len(offs))
        a = np.asarray([x[0] for x in spans])
        b = np.asarray([x[1] for x in spans])
        ia = np.clip(np.round((a[None, :] + offs[:, None]) * FPS), 0, n).astype(int)
        ib = np.clip(np.round((b[None, :] + offs[:, None]) * FPS), 0, n).astype(int)
        keep = (np.round(b * FPS) > np.round(a * FPS))[None, :]            # a span of no length does not count (same as the scalar version)
        return ((P[ib] - P[ia]) * keep).sum(1), ((ib - ia) * keep).sum(1).astype(np.float64)
    si, li = span_sums(ivs)
    sg, lg = span_sums(gaps)
    base = np.where(lg >= 20, sg / np.maximum(lg, 1.0), gm)
    return np.where(li < 10, 0.0, si / np.maximum(li, 1.0) - base)


def _group_gaps(sung, groups):
    """Per group: the spans (in lyric time) where the lyrics say the voice is silent. Only gaps the file is sure about count (rofpalys_CyroKayAI_text.silence_after:
    after an explicit break line, or the middle of a very long gap) plus the silence before the first line. A gap that is only longer than the GUESS of the
    sung time is not silence - the line may be sung slowly. Only the part next to the group is used (2 s): the rest is far from the lines it must judge."""
    out = []
    for idxs in groups:
        gaps = []
        for x in idxs:
            g = TX.silence_after(sung, x, cap=2.0)
            if g:
                gaps.append(g)
        first = idxs[0]
        if first == 0:
            g = TX.lead_silence(sung, cap=1.2)
            if g:
                gaps.append(g)
        else:
            g = TX.silence_after(sung, first - 1)
            if g:
                gaps.append((max(g[0], g[1] - 1.2), g[1]))
        out.append(gaps)
    return out


def _groups(sung, min_span=2.5, max_gap=8.0):
    """Small groups (one or two lines, about 2.5 s of singing) so a jump of the shift can happen between ANY two lines."""
    groups, cur = [], []
    for i, it in enumerate(sung):
        if cur and it["t"] - (sung[cur[-1]]["t"] + sung[cur[-1]]["dur"]) > max_gap:
            groups.append(cur)
            cur = []
        cur.append(i)
        if len(cur) >= 2 and it["t"] + it["dur"] - sung[cur[0]]["t"] >= min_span:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


JUMP_COST = 3.0                                     # a jump of the shift between two groups must be worth this much evidence (seconds x contrast)


def _solve_offsets(sung, vocal, limit=MAX_SHIFT, jumps_ok=True):
    """Per sung line: how many seconds to add to its lyric time to get the time in THIS recording.
    1) coarse search of +-20 s per group, 2) Viterbi over the groups (one shift for the whole song unless the evidence for a jump is strong:
    that is how a version with an extra / missing section is handled), 3) fine search +-0.3 s per group (20 ms steps).
    limit / jumps_ok: when the lyric version has the same length as the recording (metadata agrees) it is the same edit, so a big shift or a jump in the
    middle is not believable - the search stays small and a noisy detector cannot pull lines somewhere wrong."""
    n = len(vocal)
    P = np.concatenate(([0.0], np.cumsum(np.asarray(vocal, dtype=np.float64)))) if np is not None else _prefix(vocal)
    gm = P[-1] / max(1, n)
    groups = _groups(sung)
    gaps_l = _group_gaps(sung, groups)
    K = int(limit / 0.2)
    jump_cost = JUMP_COST if jumps_ok else 1e9
    offs = [(k - K) * 0.2 for k in range(2 * K + 1)]

    def sc_many(g, os_):
        """Evidence of group g for each shift in os_ (a list)."""
        ivs = [(sung[i]["t"], sung[i]["t"] + sung[i]["dur"]) for i in groups[g]]
        if np is not None:
            return _gscore_vec(P, n, ivs, gaps_l[g], gm, os_).tolist()
        return [_gscore(P, n, [(a + o, b + o) for a, b in ivs], [(a + o, b + o) for a, b in gaps_l[g]], gm) for o in os_]

    def sc_at(g, o):
        return sc_many(g, [o])[0]
    prev, back, table = None, [], []
    for g, idxs in enumerate(groups):
        W = sum(sung[i]["dur"] for i in idxs)
        scs = sc_many(g, offs)
        table.append(scs)
        row = [(-sc + 0.05 * abs(o) / limit) * W for sc, o in zip(scs, offs)]
        if prev is None:
            tot, bk = row, [0] * len(offs)
        else:
            mn = min(prev)
            kmn = prev.index(mn)
            tot, bk = [], []
            for k, c in enumerate(row):
                if prev[k] <= mn + jump_cost:
                    tot.append(c + prev[k])
                    bk.append(k)
                else:
                    tot.append(c + mn + jump_cost)
                    bk.append(kmn)
        back.append(bk)
        prev = tot
    k = prev.index(min(prev))
    path = [0] * len(groups)
    for g in range(len(groups) - 1, -1, -1):
        path[g] = k
        k = back[g][k]
    DS = range(-15, 16)                                      # fine search: +-0.3 s in 20 ms steps, judged on a window of 5 neighbouring groups with the same shift
    W_g = [sum(sung[i]["dur"] for i in idxs) for idxs in groups]
    fs = [[x * W_g[g] for x in sc_many(g, [offs[path[g]] + d * 0.02 for d in DS])] for g in range(len(groups))]
    sm = []
    for g in range(len(groups)):
        win = [h for h in range(max(0, g - 2), min(len(groups), g + 3)) if path[h] == path[g]]
        tot = [sum(fs[h][k] for h in win) for k in range(len(DS))]
        k0 = DS.index(0)
        kb = max(range(len(DS)), key=lambda k: tot[k])
        sm.append(offs[path[g]] + (DS[kb] * 0.02 if tot[kb] > tot[k0] + 0.01 * sum(W_g[h] for h in win) else 0.0))
    line_off = [0.0] * len(sung)
    tot_w = good_w = acc = 0.0
    for g, idxs in enumerate(groups):
        for i in idxs:
            line_off[i] = sm[g]
        W = sum(sung[i]["dur"] for i in idxs)
        sc = sc_at(g, sm[g])
        acc, tot_w, good_w = acc + sc * W, tot_w + W, good_w + (W if sc >= 0.12 else 0.0)
    jumps = []
    for g in range(1, len(groups)):
        if path[g] != path[g - 1]:
            a_prev, a_next = groups[g - 1][-1], groups[g][0]
            jumps.append({"line": a_next, "t_lyric": sung[a_next]["t"], "delta": sm[g] - sm[g - 1],
                          "prev_end": sung[a_prev]["t"] + sung[a_prev]["dur"] + sm[g - 1], "next_start": sung[a_next]["t"] + sm[g]})
    conf = 0.0
    if tot_w:
        # Two judgements. PATH: how well the lines sit on the voice with the shifts found (a flexible model can place ANY lyrics on a voice, so this alone
        # proves nothing). SINGLE: how well they sit with ONE shift for the whole song - lyrics of the right song do, unrelated lyrics do not.
        Wg = [sum(sung[i]["dur"] for i in idxs) for idxs in groups]
        k1 = max(range(len(offs)), key=lambda k: sum(table[g][k] * Wg[g] for g in range(len(groups))))
        acc1 = sum(table[g][k1] * Wg[g] for g in range(len(groups)))
        good1 = sum(Wg[g] for g in range(len(groups)) if table[g][k1] >= 0.12)
        c_path = clamp((acc / tot_w) / 0.30) * (0.4 + 0.6 * good_w / tot_w) * (1.0 - min(0.5, 0.08 * len(jumps)))
        c_single = clamp((acc1 / tot_w) / 0.30) * (0.4 + 0.6 * good1 / tot_w)
        conf = 0.5 * c_path + 0.5 * c_single
    wmed = sorted((sm[g], sum(sung[i]["dur"] for i in idxs)) for g, idxs in enumerate(groups))
    half, run, main_off = sum(w for _, w in wmed) / 2.0, 0.0, 0.0
    for o, w in wmed:
        run += w
        if run >= half:
            main_off = o
            break
    return line_off, {"conf": round(clamp(conf), 3), "jumps": jumps, "offset": round(main_off, 2), "groups": len(groups), "gscores": acc / tot_w if tot_w else 0.0}


def snap_start(A, t, win=0.35):
    """Move a line start onto the moment the voice really begins: the start of a singing span (+-0.35 s), else a vocal onset (+-0.15 s)."""
    best = None
    for a, b in A.sing:
        if a > t + win:
            break
        if abs(a - t) <= win and (best is None or abs(a - t) < abs(best - t)):
            best = a
    if best is not None:
        return max(0.0, best + ONSET_BIAS), "span"
    cand, i = None, bisect.bisect_left(A.onsets, (t - 0.15, -1))
    while i < len(A.onsets) and A.onsets[i][0] <= t + 0.15:
        ot, st = A.onsets[i]
        if st >= 0.5 and A.mean_vocal(ot + 0.05, ot + 0.3) - A.mean_vocal(ot - 0.3, ot - 0.05) > 0.15 and (cand is None or abs(ot - t) < abs(cand - t)):
            cand = ot
        i += 1
    return (cand, "onset") if cand is not None else (t, None)


def _voice_end(A, s, dur):
    """Where the voice of a line that starts at s really stops: the end of its singing span if that is plausible, else start + estimate."""
    guess = s + dur
    if has_ears(A):
        for a, b in A.sing:
            if a <= s + 0.4 < b:
                return b if s + 0.6 <= b <= guess + 3.0 else guess
            if a > s + 0.4:
                break
    return guess


def _place(items, sung, offs, A, snap=True):
    """Final lines: shifted, snapped to the voice, shown LEAD_SEC early, with melody markers for intro / instrumental gaps / outro."""
    hi, lo = syms()
    starts, base, kinds, snapped = [], [], [], 0
    for it, o in zip(sung, offs):
        t = it["t"] + o
        base.append(max(0.0, t))
        kind = None
        if snap and has_ears(A):
            t, kind = snap_start(A, t)
            snapped += bool(kind)
        starts.append(max(0.0, t))
        kinds.append(kind)
    if snap and has_ears(A):                                # lines in the middle of a phrase have no onset to snap to: they take over the error that the snapped lines around them showed
        res = [(starts[i] - base[i]) if kinds[i] == "span" else None for i in range(len(starts))]
        for i in range(len(starts)):
            if kinds[i] is None:
                near = [res[j] for j in range(max(0, i - 3), min(len(starts), i + 4)) if res[j] is not None and abs(offs[j] - offs[i]) < 0.01 and abs(res[j]) <= 0.35]
                if near:
                    starts[i] = max(0.0, base[i] + clamp(median(near), -0.25, 0.25))
    for i in range(1, len(starts)):
        if starts[i] < starts[i - 1] + 0.3:
            starts[i] = starts[i - 1] + 0.3
    out, n = [], len(sung)
    if starts[0] >= 2.0:
        out += markers(A, 0.0, starts[0] - LEAD_SEC)
    ends = []
    for i, it in enumerate(sung):
        s = starts[i]
        out.append((max(0.0, s - LEAD_SEC), it["text"]))
        end = _voice_end(A, s, it["dur"])
        ends.append(end)
        if i + 1 < n:
            if starts[i + 1] - end >= GAP_MIN:
                out += markers(A, end + 0.1, starts[i + 1] - LEAD_SEC)
        elif A is not None and A.duration - end >= 4.0:
            out += markers(A, end + 0.15, A.duration)
        elif A is None:
            out.append((end + 0.5, hi))
    return out, {"snapped": snapped, "lines": n, "starts": starts, "ends": ends}


def _keep_times(items, sung, A):
    """The audio gives no clear answer: keep the file's own times (markers still follow the music). Nothing is moved, nothing is invented."""
    out, pl = _place(items, sung, [0.0] * len(sung), A, snap=False)
    return {"pairs": out, "conf": None, "offset": 0.0, "jumps": [], "snapped": 0, "lines": pl["lines"], "starts": pl["starts"], "ends": pl["ends"], "A": A,
            "learn": None}


def fit_synced(pairs, A, cand_dur=None, stop=None):
    """Time-synced lyrics [(t, text)] -> fitted lyrics for THIS recording. Returns dict(pairs, conf, offset, jumps, snapped, lines, starts, ends, A, learn) or None.
    Two ways are tried and the more convincing one wins:
      GENERIC  the generic voice detector says where the voice is; the lines are placed on it.
      LEARNED  the lyric timestamps teach a detector what THIS song's voice sounds like (rofpalys_CyroKayAI_learn.py), the lines are placed on that.
               It rescues dense mixes where the generic detector hears nothing, and it carries its own proof (held-out AUC, scan peak).
    cand_dur: the length of the recording the lyrics were made for (LRCLIB knows it). Within 3 s of ours: same edit -> small shift, no jumps."""
    items = make_items(pairs)
    sung = [it for it in items if not it["brk"]]
    if not sung:
        return None
    if A is None or A.engine not in ("full", "selftest"):                 # no ears at all (no ffmpeg / no numpy): keep the file's times
        return _keep_times(items, sung, A)
    A.use_generic()                                                        # every fit starts from the generic curve (a cached analysis may carry an older learned one)
    gap = abs(A.duration - cand_dur) if cand_dur and cand_dur > 0 else None
    limit = MAX_SHIFT if gap is None or gap > 8.0 else (5.0 if gap <= 3.0 else 10.0)
    jumps_ok = gap is None or gap > 3.0
    g = None
    if has_ears(A) and A.coverage >= 0.03:
        offs, info = _solve_offsets(sung, A.vocal, limit, jumps_ok)
        g = (offs, info, A)
    lr = None
    if LRN is not None and LRN.available() and not (stop and stop()) and A.features(stop) is not None:
        try:
            lr = LRN.learn_fit(A.F, sung, A.duration, limit, jumps_ok, lambda curve, lim, jo: _solve_offsets(sung, curve, lim, jo), generic=A.vocal, stop=stop)
        except Exception as e:                                             # learning must never break the lyrics
            log("learn_fit failed: %r" % (e,))
            lr = None
    pick = g
    learn = None
    if lr is not None:
        conf_l = lr["info"]["conf"] * lr["learn"]["mult"]
        conf_g = g[1]["conf"] if g else 0.0
        if conf_l >= 0.25 and (g is None or conf_g < 0.5 or conf_l >= conf_g + 0.1):          # the generic detector wins when it is confident itself
            import copy
            A2 = copy.copy(A)
            A2.use_curve(lr["curve"], dict(lr["learn"]))
            info = dict(lr["info"])
            info["conf"] = round(clamp(conf_l), 3)
            info["stats"] = lr.get("stats")
            pick = (lr["offs"], info, A2)
            learn = A2.learn
        elif g is not None:
            g[1]["conf_learned"] = round(conf_l, 3)
    if pick is None:
        return _keep_times(items, sung, A)
    offs, info, Au = pick
    if info["conf"] < 0.2:                                                 # the audio gives no clear answer: do not invent precision, keep the file's own times
        res = _keep_times(items, sung, A)
        res["learn"] = None
        return res
    out, pl = _place(items, sung, offs, Au)
    info.update(pairs=out, snapped=pl["snapped"], lines=pl["lines"], starts=pl["starts"], ends=pl["ends"], A=Au, learn=learn)
    return info


def sync_plain(text, A):
    """Plain (unsynced) lyrics -> synced lyrics by spreading the syllables over the SING spans (a melody gap is skipped), then snapping
    every line start to the nearest vocal onset. The confidence compares the sung time found in the audio with the time the text needs."""
    if not has_ears(A) or not A.sing:
        return None
    lines, gap = [], False
    for ln in text.replace("\r\n", "\n").split("\n"):
        s = ln.strip()
        if not s or re.match(r"^\[[^\]]*\]$", s):                           # an empty line or [Chorus] marks a new stanza
            gap = gap or bool(lines)
            continue
        lines.append((s, gap))
        gap = False
    if len(lines) < 2:
        return None
    syl = [max(1, syllables(s)) for s, _ in lines]
    wts = [w + (1.2 if g else 0.0) for w, (_, g) in zip(syl, lines)]
    W, spans = sum(wts), A.sing
    T = sum(b - a for a, b in spans)
    if T < 8.0:
        return None
    ratio = T / max(1.0, sum(syl) * SYL_SEC)
    conf = 0.55 * (1 - clamp(abs(math.log2(max(ratio, 1e-3))) / 1.5)) * smoothstep(T, 8.0, 40.0)
    if conf < 0.12:
        return None

    def to_t(u):
        for a, b in spans:
            if u < max(0.1, b - a - 0.6):                       # nobody starts a line in the last 0.6 s of a phrase: it begins in the next one
                return a + u
            u -= b - a
        return spans[-1][1] - 0.2
    acc, cum = 0.0, []
    for w in wts:
        cum.append(acc)
        acc += w
    items = [{"t": to_t(c / W * T), "text": s, "brk": False, "dur": est_sung(s)} for c, (s, _) in zip(cum, lines)]
    sn = 0
    for it in items:
        it["t"], kind = snap_start(A, it["t"], 0.3)
        sn += bool(kind)
    out, pl = _place(items, items, [0.0] * len(items), A, snap=False)
    return {"pairs": out, "conf": round(conf, 3), "offset": 0.0, "jumps": [], "snapped": sn, "lines": pl["lines"], "starts": pl["starts"]}


# ------------------------------------------------------------------ cutting (last resort, optional): the recording has a section the lyrics do not know
def plan_cuts(A, jumps):
    """[(from, to)] seconds of the RECORDING to cut so the lyrics fit: only where the audio is clearly longer (>= 3 s) than the lyric version."""
    cuts = []
    for j in jumps:
        d = j["delta"]
        if d < 3.0 or A is None:
            continue
        room = j["next_start"] - j["prev_end"]
        margin = clamp((room - d) / 2.0, 0.0, 0.3)
        lo_t, hi_t = j["prev_end"] + margin, j["next_start"] - margin
        c0 = A.snap_beat(lo_t + max(0.0, hi_t - lo_t - d) * 0.5, 0.3)
        c0 = clamp(c0, lo_t, max(lo_t, hi_t - d))
        cuts.append((round(c0, 3), round(c0 + d, 3)))
    return cuts


def retime(pairs, cuts):
    """Lyric times of the original recording -> times of the trimmed copy. A line shown up to 0.5 s before the end of a cut belongs to what comes
    after it; a marker that would only last a moment (its music was cut away) is dropped."""
    out = []
    for t, text in pairs:
        gone = 0.0
        for c0, c1 in cuts:
            if t >= c1 - (0.5 if not _ly().is_note(text) else 0.0):
                gone += c1 - c0
            elif t > c0:
                gone += t - c0
        out.append((max(0.0, t - gone), text))
    keep = []
    for i, (t, text) in enumerate(out):
        if _ly().is_note(text) and i + 1 < len(out) and out[i + 1][0] - t < 0.4:
            continue
        keep.append((t, text))
    return keep


def export_trimmed(path, cuts, out_dir=None):
    """Write a trimmed COPY of the song (the original is never touched; 30 ms fades hide the joins, so the timing stays exact). -> path or ''."""
    exe = shutil.which("ffmpeg")
    if not exe or not cuts:
        return ""
    out_dir = out_dir or os.path.join(CK_DIR, "trimmed")
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r'[\\/:*?"<>|]', "_", os.path.splitext(os.path.basename(path))[0])
    dest = os.path.join(out_dir, base + ".cut.mp3")
    segs, t = [], 0.0
    for c0, c1 in sorted(cuts):
        segs.append((t, c0))
        t = c1
    segs.append((t, None))
    parts = []
    for i, (a, b) in enumerate(segs):
        f = "atrim=start=%.3f%s,asetpts=PTS-STARTPTS" % (a, (":end=%.3f" % b) if b is not None else "")
        if i > 0:
            f += ",afade=t=in:st=0:d=0.03"
        if b is not None:
            f += ",afade=t=out:st=%.3f:d=0.03" % max(0.0, b - a - 0.03)
        parts.append("[0:a]%s[s%d]" % (f, i))
    fc = ";".join(parts) + ";" + "".join("[s%d]" % i for i in range(len(segs))) + "concat=n=%d:v=0:a=1[o]" % len(segs)
    try:
        r = subprocess.run([exe, "-y", "-v", "error", "-nostdin", "-i", path, "-filter_complex", fc, "-map", "[o]", "-c:a", "libmp3lame", "-q:a", "2", dest],
                           capture_output=True, timeout=600, stdin=subprocess.DEVNULL)
    except Exception:
        return ""
    return dest if r.returncode == 0 and os.path.isfile(dest) else ""


# ------------------------------------------------------------------ the whole job: creator -> internet -> listen -> fetch -> fit -> melody markers -> cache
_LAST = {}                                          # path -> last result (the GUI shows it)


def last(path=None):
    return _LAST.get(path) if path else (list(_LAST.values())[-1] if _LAST else None)


def playing_path(artist="", title=""):
    """The file the player is playing now - but only when it is plausibly the song that is asked for (the user may have skipped meanwhile)."""
    E = sys.modules.get("rofpalys_engine")
    p = getattr(E, "playing_song_name", "") if E is not None else ""
    if not p or not os.path.isfile(p):
        return ""
    if title:
        base = os.path.splitext(os.path.basename(p))[0]
        names = [n for n in (_ly().guess(p)[1], base) if n]
        if names and max(_sim(title, n) for n in names) < 0.55:
            tt = read_tags(p).get("title", "")
            if not tt or _sim(title, tt) < 0.55:
                return ""
    return p


def _blank():
    return {"raw": "", "source": "", "synced": False, "mode": "none", "artist": "", "title": "", "verified": False, "online": False, "confidence": None,
            "offset": 0.0, "jumps": [], "cuts": [], "snapped": 0, "lines": 0, "analysis": "", "cands": 0, "stopped": False, "online_done": False, "path": "",
            "ident": {}, "pairs": [], "from_cache": False, "learn": None, "starts": [], "ends": [], "chain": [], "provider": ""}


def _finish(R, pairs, source, synced, mode, fit=None):
    LY = _ly()
    R.update(raw=LY.to_lrc(pairs), pairs=pairs, source=source, synced=synced, mode=mode)
    if fit:
        R.update(confidence=fit.get("conf"), offset=fit.get("offset", 0.0), jumps=fit.get("jumps", []), snapped=fit.get("snapped", 0), lines=fit.get("lines", 0),
                 learn=fit.get("learn"), starts=fit.get("starts", []), ends=fit.get("ends", []))
    return R


def fit_raw(raw, path, stop=None, progress=None, source="user", A=None):
    """Fit lyrics we already have (picked by hand, from a file, from an older cache) to the recording. No network."""
    LY = _ly()
    R = _blank()
    R["path"] = path or ""
    if A is None and path and os.path.isfile(path):
        A = analyze(path, stop)
    R["analysis"] = A.summary() if A else ""
    lines, synced = LY.parse(raw)
    fit = None
    if synced and len(lines) >= 2:
        fit = fit_synced(lines, A, None, stop)
    elif A is not None:
        fit = sync_plain(raw, A)
    if fit and not (stop and stop()):
        mode = "synced" if (synced and fit["conf"] is not None and fit["conf"] >= 0.2) else "plain-synced" if not synced else "synced-source"
        _finish(R, fit["pairs"], BRAND + " · " + source, True, mode, fit)
        _keep_analysis(path, fit, A)
        _remember(path, fit)
        R["analysis"] = (fit.get("A") or A).summary()
    else:
        R.update(raw=raw, source=source, synced=synced, mode="plain" if not synced else "synced-source")
    return R


def _remember(path, fit):
    """The fit that was CHOSEN teaches the memory (the voice model of your own music); fits that were not chosen do not."""
    try:
        st = (fit or {}).get("stats")
        if st and LRN is not None and MEM is not None and (fit.get("conf") or 0) >= 0.4:
            LRN.remember(st, MEM.song_id(path) if path else None)
    except Exception as e:
        log("remember failed: %r" % (e,))


def _keep_analysis(path, fit, A):
    """Save the analysis the winning fit used (it may carry the learned curve), so the lyric view, the melody markers and the word timing of this song
    use the same SING / MELODY spans next time."""
    try:
        Au = (fit or {}).get("A") or A
        if path and Au is not None and Au.engine == "full":
            save_analysis(path, Au)
    except Exception as e:
        log("keep analysis failed: %r" % (e,))


def is_current(source):
    """True when lyrics were made by this version of CyroKayAI (older ones - CyroKayAI 1 or none - are made again once: the automatic deep reset)."""
    return _ly().is_current(source)


def too_long(lines, A, dur):
    """True when the lyric file has a sung line that starts after the recording has ended, even with the largest shift the fit allows: these lyrics
    belong to another (longer) song or version, no fitting can save them. `lines` = [(t, text)], A = the analysis (or None), dur = the length we know."""
    D = (getattr(A, "duration", 0.0) if A is not None else 0.0) or dur or 0.0
    last = max((t for t, tx in lines if tx.strip() and not is_break(tx)), default=0.0)
    return bool(D > 0 and last > D + MAX_SHIFT + 5.0)


def _fc(fit):
    """The confidence of a fit for comparing: a fit the audio could not judge (None) counts as weak."""
    return 0.15 if fit.get("conf") is None else fit["conf"]


def _analyze_bg(path, stop, box):
    box["A"] = analyze(path, stop, True, keep_features=np is not None) if path and os.path.isfile(path) else None
    box["done"] = True


def auto_lyrics(path, artist="", title="", duration=-1.0, allow_youtube=True, langs=("en",), stop=None, progress=None):
    """The whole job for one song. Returns a dict (see _blank): raw / source / synced / mode / confidence ...  raw == '' means nothing could be made.
    Order: who made it -> is the internet there -> (while waiting for the servers) listen to the song -> fetch lyrics -> fit the best candidate
    to the real voice -> melody markers; no lyrics anywhere -> a melody-only track."""
    import threading
    LY = _ly()
    stop = stop or (lambda: False)
    say = progress or (lambda m: None)
    R = _blank()
    R["path"] = path or ""
    box = {"A": None, "done": False}
    th = None
    if path and os.path.isfile(path):                                      # listening runs in parallel with the network questions
        th = threading.Thread(target=_analyze_bg, args=(path, stop, box), daemon=True)
        th.start()
    say("creator")
    ident = identify(path or "", duration, hint=(artist, title), stop=stop) if (path or title) else {"artist": artist, "title": title, "alts": [], "verified": False,
                                                                                                 "online": internet_ok(), "duration": duration, "source": "caller", "confidence": 0.3}
    R.update(ident=ident, artist=ident["artist"], title=ident["title"], verified=ident["verified"], online=ident["online"])
    dur = ident.get("duration") or (duration if duration and duration > 0 else 0.0)
    say("internet")
    cands, chain, queries = [], None, []
    names = [(ident["artist"], ident["title"])] + list(ident["alts"])
    st = {"A": None, "got": False}

    def hear():
        """The recording as the ears heard it (the first call waits for the listening thread, which ran while the network was asked)."""
        if not st["got"]:
            if th is not None:
                while not box["done"] and not stop():
                    th.join(0.2)
            if th is None or box["done"]:
                st["A"], st["got"] = box["A"], True
        return st["A"]

    def verify(c):
        """The audio fit of one provider's lyrics: the judge of the provider chain (fit < 35 % = that provider failed, the next one is asked)."""
        lines, ok = LY.parse(c["raw"])
        if not ok or len(lines) < 3:
            return {"conf": 0.0}
        Ah = hear()
        if stop():
            return {"conf": None, "final": True}
        if too_long(lines, Ah, dur):
            return {"conf": 0.0, "why": "longer than the recording"}
        fit = fit_synced(lines, Ah, c.get("duration"), stop)
        if not fit:
            return {"conf": 0.0}
        return {"conf": fit["conf"], "final": Ah is None or Ah.engine not in ("full", "selftest"), "fit": fit}
    if ident["online"] and ident["title"] and not stop():
        for k, (a, t) in enumerate(names[:2]):
            queries.append({"artist": a, "title": t, "album": (ident.get("album") or "") if k == 0 else "", "duration": dur, "path": path or ""})
        if PV is not None and PV.order():
            say("providers")                                                # 1. syncedlyrics -> lrcdl -> lyriq -> librelyrics (order: rofpalys lyrics providers)
            chain = PV.run_chain(queries, verify, stop)
            R["chain"] = chain["trace"]
        cb = chain["best"] if chain else None
        if not (cb is not None and cb["conf"] is not None and cb["conf"] >= OK_FIT) and not stop():
            say("fetch")                                                    # 2. the safety net that needs no package: LRCLIB, YouTube captions, lyrics.ovh
            seen = set()
            for a, t in names[:4]:
                if stop():
                    break
                batch = []
                ex = LY.lrclib_exact(a, t, dur)
                if ex:
                    ex["score"] = LY.score(ex, a, t, dur)
                    batch.append(ex)
                batch += LY.lrclib_search(a, t, dur) if not stop() else []
                for c in batch:
                    k = (LY.lib.norm(c["artist"]), LY.lib.norm(c["title"]), int(c["duration"]), c["synced"])
                    if k not in seen and c["raw"]:
                        seen.add(k)
                        cands.append(c)
                if any(c["synced"] and c["score"] >= 0.7 for c in cands):
                    break
            if allow_youtube and not stop() and not any(c["synced"] and c["score"] >= 0.62 for c in cands):
                raw = LY.youtube_captions(ident["artist"], ident["title"], langs, stop)
                if raw:
                    cands.append({"source": "YouTube captions", "artist": ident["artist"], "title": ident["title"], "duration": 0.0, "synced": True, "raw": raw, "score": 0.5})
            if not cands and not stop():
                o = LY.lyrics_ovh(ident["artist"], ident["title"])
                if o:
                    o["score"] = 0.5
                    cands.append(o)
        R["online_done"] = True
    R["cands"] = len(cands) + sum(1 for t in R["chain"] if t.get("result") in ("ok", "low-fit", "duplicate"))
    say("listen")
    A = hear()
    if stop():
        R["stopped"] = True
        return R
    R["analysis"] = A.summary() if A else ""
    say("fit")
    best = None                                                            # (rank, candidate, fit)
    cb = chain["best"] if chain else None
    if cb is not None and cb["check"].get("fit"):
        best = (cb["rank"], cb["cand"], cb["check"]["fit"])
    skip = chain["seen"] if chain else set()
    bb = None                                                              # the best candidate of the safety net
    for c in sorted([x for x in cands if x["synced"]], key=lambda x: -x["score"])[:4]:
        if PV is not None and PV.text_key(c["raw"]) in skip:
            continue                                                       # a provider already gave exactly this text and it was fitted
        lines, ok = LY.parse(c["raw"])
        if not ok or len(lines) < 3 or too_long(lines, A, dur):
            continue
        fit = fit_synced(lines, A, c.get("duration"), stop)
        if not fit:
            continue
        rank = (0.6 * fit["conf"] + 0.4 * min(1.0, c["score"])) if fit["conf"] is not None else 0.5 * min(1.0, c["score"])
        if bb is None or rank > bb[0]:
            bb = (rank, c, fit)
    if bb is not None and (best is None or _fc(bb[2]) > _fc(best[2]) + 0.05):
        best = bb                                                          # the priority order holds unless the safety net fits clearly better
    if best is None or (best[2]["conf"] is not None and best[2]["conf"] < OK_FIT):
        if ident["online"] and PV is not None and PV.order() and queries and not any(not x["synced"] for x in cands) and not stop():
            txt, who = PV.plain_text(queries, chain["plains"] if chain else (), stop)      # text without timestamps from the same providers
            if txt:
                cands.append({"source": who, "artist": ident["artist"], "title": ident["title"], "duration": 0.0, "synced": False, "raw": txt, "score": 0.6})
        for c in [x for x in cands if not x["synced"]][:2]:                 # plain text: spread over the SING spans if there is enough evidence
            fit = sync_plain(c["raw"], A)
            if fit and (best is None or fit["conf"] > (best[2]["conf"] or 0)):
                best = (fit["conf"], c, fit)
    if best is not None:
        rank, c, fit = best
        synced_src = c["synced"]
        mode = ("synced" if fit["conf"] is not None and fit["conf"] >= 0.2 else "synced-source") if synced_src else "plain-synced"
        _finish(R, fit["pairs"], BRAND + " · " + c["source"], True, mode, fit)
        R["provider"] = c["source"]
        Au = fit.get("A") or A
        R["cuts"] = plan_cuts(Au, fit.get("jumps", [])) if (fit.get("conf") or 0) >= 0.2 else []
        R["analysis"] = Au.summary() if Au else R["analysis"]
        _keep_analysis(path, fit, A)
        _remember(path, fit)
    else:
        plain = next((c for c in cands if c["raw"]), None)
        old_raw, old_src = LY.read_cache(path) if path else ("", "")
        if plain:                                                          # text exists but cannot be timed (no ffmpeg / no clear singing)
            R.update(raw=plain["raw"], source=BRAND + " · " + plain["source"], synced=False, mode="plain")
        elif old_raw and "melody" not in old_src and _ly().is_current(old_src):   # fitted by this CyroKayAI already: kept (offline), redone when the internet is back
            lines_old, ok_old = _ly().parse(old_raw)
            R.update(raw=old_raw, source=old_src, synced=ok_old, mode="synced" if ok_old else "plain", from_cache=True, pairs=lines_old if ok_old else [])
        elif old_raw and "melody" not in old_src:                          # an older download (before CyroKayAI) or CyroKayAI 1 lyrics: fitted again now, offline
            r2 = fit_raw(old_raw, path, stop, source=old_src or "cache", A=A)
            R.update({k: r2[k] for k in ("raw", "source", "synced", "mode", "confidence", "offset", "jumps", "snapped", "lines", "pairs", "learn", "starts", "ends")})
            R["from_cache"] = True
        elif A is not None or path:                                        # no lyrics anywhere: only the melody, on the beat
            _finish(R, melody_track(A), "CyroKayAI melody" if R["online_done"] else "CyroKayAI melody (offline)", True, "melody")
    if R["raw"] and path and not stop():
        LY.write_cache(path, R["raw"], R["source"])
    if path:
        _LAST[path] = R
    return R


def describe(R, lang="en"):
    """Human text for the GUI / terminal (lang 'en' or 'id')."""
    id_ = lang == "id"
    i = R.get("ident") or {}
    out = []
    if i.get("artist") or i.get("title"):
        how = (("terverifikasi online: " if id_ else "verified online: ") + i.get("source", "")) if R.get("verified") else (("dari " if id_ else "from ") + i.get("source", "?"))
        out.append("%s: %s - %s  (%s)" % ("Pembuat" if id_ else "Creator", i.get("artist") or "?", i.get("title") or "?", how))
    out.append("%s: %s" % ("Internet", ("tersambung" if R.get("online") else "tidak ada - memakai data lokal") if id_ else ("connected" if R.get("online") else "not available - using local data")))
    out.append("%s: %s" % ("Mendengar" if id_ else "Listening", R.get("analysis") or ("tidak bisa (ffmpeg?)" if id_ else "not possible (ffmpeg?)")))
    m, c = R.get("mode"), R.get("confidence")
    nt = "%s/%s" % syms()
    if m == "melody":
        out.append(("Lirik: tidak ada - hanya %s yang mengikuti melodi" if id_ else "Lyrics: none - only %s following the melody") % nt)
    elif R.get("raw"):
        out.append("%s: %s%s" % ("Lirik" if id_ else "Lyrics", R.get("source", ""), (" (%d %s)" % (R["cands"], "kandidat" if id_ else "candidates")) if R.get("cands") else ""))
        if R.get("chain"):
            out.append(("Rantai provider: " if id_ else "Provider chain: ") + PV.trace_line(R["chain"], lang))
            if any(t.get("provider") == "syncedlyrics" and t.get("result") == "not-installed" for t in R["chain"]):
                out.append("Pasang syncedlyrics (provider utama):  rofpalys lyrics providers install" if id_ else "Install syncedlyrics (the main provider):  rofpalys lyrics providers install")
        if c is not None:
            out.append("%s: %d%%  ·  %s %+.2f s  ·  %d/%d %s%s" % ("Cocok dengan suara" if id_ else "Fit to the voice", round(c * 100), "geser" if id_ else "shift", R.get("offset", 0.0),
                                                                    R.get("snapped", 0), R.get("lines", 0), "baris menempel ke suara" if id_ else "lines snapped to the voice",
                                                                    ("  ·  %d %s" % (len(R["jumps"]), "loncatan bagian" if id_ else "section jump(s)")) if R.get("jumps") else ""))
        elif m == "plain":
            out.append("Sinkron: teks polos (tidak bisa dihitung waktunya)" if id_ else "Sync: plain text (timing could not be measured)")
        if m == "synced-source":
            out.append("Sinkron: waktu dari file lirik (suara tidak bisa diukur dengan yakin, jadi tidak digeser)" if id_ else
                       "Sync: times from the lyric file (the voice could not be measured reliably, so nothing was moved)")
    else:
        out.append("Lirik: tidak ditemukan" if id_ else "Lyrics: nothing found")
    L = R.get("learn")
    if L:
        g = L.get("gen_auc")
        out.append(("Belajar: detektor suara dilatih dari waktu lirik lagu ini (uji lagu tak dilihat: AUC %s, puncak sinkron x%s; detektor umum: %s)" if id_ else
                    "Learning: a voice detector was taught on this song from the lyric timestamps (held-out AUC %s, sync peak x%s; generic detector: %s)") %
                   (L.get("auc"), L.get("ratio"), ("AUC %s" % g) if g is not None else "-"))
    if R.get("cuts"):
        out.append(("Rencana potong: %d bagian (rofpalys lyrics cut FILE)" if id_ else "Cut plan: %d section(s) (rofpalys lyrics cut FILE)") % len(R["cuts"]))
    if MEM is not None:
        try:
            out.append(("Memori CyroKayAI: " if id_ else "CyroKayAI memory: ") + MEM.summary(lang))
        except Exception:
            pass
    return "\n".join(out)


def short_status(R, lang="en"):
    """One line for a status label."""
    if not R:
        return ""
    i = R.get("ident") or {}
    c = R.get("confidence")
    return "%s  ·  %s  ·  %s" % (i.get("artist") or "?", ("online" if R.get("online") else "offline"), ("%d%%" % round(c * 100)) if c is not None else
                                  (("%s/%s" % syms()) if R.get("mode") == "melody" else "-"))


# ------------------------------------------------------------------ cache housekeeping (deep reset of the lyric side) and batch
def reset_cache(lyrics=True, analysis=True):
    """Delete the saved lyrics and CyroKayAI's measurements, so everything is made again with the current logic. Never touches songs or your own .lrc files."""
    LY, n = _ly(), 0
    for d, flag in ((LY.LYRICS_DIR, lyrics), (CK_DIR, analysis)):
        if flag and os.path.isdir(d):
            for root, _, files in os.walk(d):
                n += len(files)
            shutil.rmtree(d, ignore_errors=True)
    _LAST.clear()
    return n


def process_many(paths, redo=False, progress=None, stop=None, jobs=1):
    """Make lyrics for many songs (skips songs that already have CyroKayAI-3 lyrics unless redo). jobs > 1 works on several songs at the same time
    (all cores; the network questions of one song overlap with the listening of another). Returns (done, skipped, failed)."""
    LY = _ly()
    cnt = {"done": 0, "skipped": 0, "failed": 0, "k": 0}
    lock = threading.Lock()

    def one(p):
        if stop and stop():
            return
        raw, src = LY.read_cache(p)
        if raw and LY.is_current(src) and "melody" not in src and not redo:
            with lock:
                cnt["skipped"] += 1
            return
        try:
            r = auto_lyrics(p, "", "", -1.0, True, ("en",), stop)
            ok = bool(r.get("raw"))
        except Exception as e:
            log("process_many %s: %r" % (p, e))
            r, ok = None, False
        with lock:
            cnt["done" if ok else "failed"] += 1
            cnt["k"] += 1
            if progress and r is not None:
                progress(cnt["k"], len(paths), p, r)
    jobs = max(1, int(jobs or 1))
    if jobs == 1 or len(paths) < 2:
        for p in paths:
            one(p)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            list(ex.map(one, paths))
    return cnt["done"], cnt["skipped"], cnt["failed"]


# ------------------------------------------------------------------ the running player (GUI / terminal UI / daemon / ctl)
SKIP = {"on": False, "last": 0.0}                   # play-time skipping of the cut plan (off by default)


def sync_playing(E, melody=False, stop=None, progress=None, apply=True):
    """Run the whole job for the song the player plays now and, by default, hand the result to the player. Returns the result dict or None."""
    path = getattr(E, "playing_song_name", "") or ""
    if not path or not os.path.isfile(path):
        return None
    song = path
    base = stop or (lambda: False)

    def halt():
        return base() or getattr(E, "playing_song_name", "") != song           # the user skipped to another song: stop working on this one
    if melody:
        A = analyze(path, halt)
        R = _finish(_blank(), melody_track(A), "CyroKayAI melody", True, "melody")
        R["path"], R["analysis"] = path, A.summary() if A else ""
        _ly().write_cache(path, R["raw"], R["source"])
        _LAST[path] = R
    else:
        a, t = _ly().guess(path)
        dur = E.total_time_seconds if getattr(E, "duration_known", False) else -1.0
        R = auto_lyrics(path, a, t, dur, True, (getattr(E, "current_lang", "en"),), halt, progress)
    if apply and R and R.get("raw") and not R.get("stopped") and getattr(E, "playing_song_name", "") == song:
        E.use_lyrics(R["raw"], R["source"])
    return R


def maybe_skip(E):
    """Call this about once a second from the player's loop: when skipping is on and the playback position is inside a cut section, jump past it."""
    if not SKIP["on"]:
        return False
    R = _LAST.get(getattr(E, "playing_song_name", "") or "")
    if not R or not R.get("cuts"):
        return False
    pos = getattr(E, "current_time_seconds", 0.0)
    for c0, c1 in R["cuts"]:
        if c0 <= pos < c1 - 0.3 and time.time() - SKIP["last"] > 1.0:
            SKIP["last"] = time.time()
            E.seek(c1)
            return True
    return False


# ------------------------------------------------------------------ self-test (no audio file and no internet needed) and the terminal commands
def selftest(verbose=True):
    """Builds a fake recording (a vocal curve with known singing spans), gives the lyric lines a WRONG shift and a missing section,
    and checks that CyroKayAI finds the real times again. True when everything agrees."""
    A = Analysis()
    A.engine, A.duration = "selftest", 80.0
    truth = [(8.0, 14.0), (16.0, 22.0), (24.0, 30.0), (42.0, 48.0), (50.0, 56.0), (58.0, 64.0)]          # singing; 30..42 is an instrumental solo
    n = int(A.duration * FPS)
    A.vocal = [1.0 if any(a <= i * STEP < b for a, b in truth) else 0.05 for i in range(n)]
    A.energy = [0.7 if v > 0.5 else 0.5 for v in A.vocal]
    A.sing = [tuple(x) for x in truth]
    A.coverage = sum(b - a for a, b in truth) / A.duration
    A.onsets = [(a, 1.0) for a, _ in truth]
    # the lyric version: line starts every 3 s inside each span; it was timed 1.7 s too early and lacks the 12 s solo (the later lines are 12 s too early)
    real = [a + 3.0 * k for a, b in truth for k in range(int((b - a) / 3.0))]
    texts = ["line number %d of the test song" % k for k in range(len(real))]
    pairs = [(t - 1.7 - (12.0 if t > 40 else 0.0), tx) for t, tx in zip(real, texts)]
    fit = fit_synced(pairs, A)
    got = [t for t, tx in fit["pairs"] if tx in texts]
    exp = [t - LEAD_SEC for t in real]
    err = [abs(g - e) for g, e in zip(got, exp)] if len(got) == len(exp) else [99.0]
    markers_ok = any(syms()[0] == s or syms()[1] == s for _, s in fit["pairs"])
    ok = max(err) <= 0.15 and len(fit["jumps"]) == 1 and abs(fit["jumps"][0]["delta"] - 12.0) <= 0.5 and markers_ok and (fit["conf"] or 0) > 0.5
    cuts = plan_cuts(A, fit["jumps"])
    if verbose:
        print("selftest: max error %.3f s (limit 0.15)  jumps found: %d (want 1, size %s)  confidence %s  melody markers: %s  cut plan: %s  -> %s" %
              (max(err), len(fit["jumps"]), ("%.1f s" % fit["jumps"][0]["delta"]) if fit["jumps"] else "-", fit["conf"], "yes" if markers_ok else "NO", cuts, "OK" if ok else "FAILED"))
    plain = sync_plain("\n".join(texts), A)
    pg = [t for t, tx in plain["pairs"] if tx in texts] if plain else []
    pok = len(pg) == len(exp) and max(abs(g - e) for g, e in zip(pg, exp)) <= 0.15
    if verbose:
        print("selftest: plain text spread over the singing spans: %s (confidence %s)" % ("OK" if pok else "FAILED", plain["conf"] if plain else None))
    cok = selftest_clock(verbose)
    vok = PV.selftest(False) if PV is not None else True
    if verbose:
        print("selftest: provider chain (failover, fit check, resting, time limit; no packages and no internet needed): %s" % ("OK" if vok else "FAILED" if PV is not None else "skipped (rofpalys_CyroKayAI_providers.py missing)"))
    return bool(ok and pok and cok and vok)


def selftest_clock(verbose=True):
    """The song clock and the scroll maths without a screen: the player reports the position in WHOLE seconds, ten times a second, a little late and
    early; the clock must stay within 50 ms of the truth and never jump from one frame to the next; the sheet must glide, not jump."""
    import random
    import rofpalys_CyroKayAI_clock as CL
    rng = random.Random(3)
    wall = [0.0]
    clk = CL.PlayClock(mono=lambda: wall[0])
    worst = step = 0.0
    prev, nxt = None, 0.0
    pairs = [(8.0 + 3.1 * i, "Selftest line number %d of the song" % i) for i in range(12)]
    tl = CL.Timeline(pairs, None, lead=LEAD_SEC, duration=60.0)
    sh = CL.Sheet(tl)
    sh.layout([80.0] * len(tl))
    off_prev, move = None, 0.0
    while wall[0] < 40.0:
        w = wall[0]
        truth = 4.0 + w
        if w >= nxt:
            clk.update(math.floor(truth), True, now=w)
            nxt = w + 0.1 + rng.uniform(-0.02, 0.02)
        t = clk.time(w)
        if w > 3.0:
            worst = max(worst, abs(t - truth))
            if prev is not None:
                step = max(step, abs(t - prev - 1 / 60.0))
            f = sh.frame(t, w, 1 / 60.0)
            if off_prev is not None:
                move = max(move, abs(f["offset"] - off_prev))
            off_prev = f["offset"]
        prev = t
        wall[0] += 1 / 60.0
    pitch = 80.0 + sh.gap
    ok = worst <= 0.05 and step <= 0.03 and move <= 0.13 * pitch and abs(clk.q - 1.0) < 0.05
    if verbose:
        print("selftest clock: whole-second reports -> clock error max %.3f s (limit 0.05)  frame-to-frame jump max %.4f s (limit 0.03)  learned report step %.2f s  "
              "sheet movement max %.1f px per frame (limit %.1f)  -> %s" % (worst, step, clk.q, move, 0.13 * pitch, "OK" if ok else "FAILED"))
    return ok


def _bench(files, lang="en"):
    """rofpalys lyrics bench [FILE ...]: how fast is CyroKayAI on this device?"""
    if TB is not None:
        TB.bench()
    else:
        print("rofpalys_CyroKayAI_turbo.py is missing: single core")
    for p in files:
        p = os.path.expanduser(p)
        if not os.path.isfile(p):
            print("not found: " + p)
            continue
        t0 = time.time()
        A = analyze(p, use_cache=False, keep_features=np is not None)
        dt = time.time() - t0
        if A is None:
            print("%s: cannot listen (ffmpeg missing or file unreadable)" % os.path.basename(p))
            continue
        print("%s: listened to %s of music in %.2f s = x%.0f faster than real time  (%s)" % (os.path.basename(p), fmt_t(A.duration), dt, A.duration / max(dt, 1e-6), A.engine))
    return 0


def _timeline_rows(p, lang="en"):
    """rofpalys lyrics timeline FILE: the rows, line times and word times exactly as the live lyric view uses them."""
    import rofpalys_CyroKayAI_clock as CL
    LY = _ly()
    raw, src = LY.read_cache(p)
    if not raw:
        side = LY.sidecar(p)
        raw, src = (open(side, encoding="utf-8", errors="replace").read(), "file") if side else ("", "")
    if not raw:
        print("  no lyrics saved for this song yet (rofpalys lyrics FILE)")
        return 1
    A = analyze(p)
    tl = CL.Timeline.from_raw(raw, A, LEAD_SEC if is_current(src) or "CyroKayAI" in src else 0.0, A.duration if A else None)
    if tl is None:
        print("  these lyrics have no timing (plain text): they cannot scroll with the song")
        return 1
    print("  source: %s   rows: %d   beats: %d" % (src, len(tl), len(tl.beats)))
    for r in tl.rows:
        if r.kind == "note":
            print("  %s  %s - %s  %s  (melody, until the voice returns)" % (fmt_t(r.t0), fmt_t(r.t0), fmt_t(r.v1), r.text))
        else:
            print("  %s  voice %s - %s  %s" % (fmt_t(r.t0), fmt_t(r.v0), fmt_t(r.v1), r.text))
            print("        words: " + "  ".join("%s@%s" % (w, fmt_t(a)[2:]) for w, a, b in r.words[:8]) + (" ..." if len(r.words) > 8 else ""))
    return 0


def _timeline(A):
    """Printable timeline: melody and sing spans with their symbols."""
    ev = [(a, b, "sing") for a, b in A.sing] + [(a, b, "melody") for a, b in A.melody_spans(0.3)]
    rows = []
    for a, b, kind in sorted(ev):
        rows.append("  %s - %s  %-6s %s" % (fmt_t(a), fmt_t(b), "SING" if kind == "sing" else "MELODY", "" if kind == "sing" else _pick(A, a, b)))
    return rows


def _providers_cli(args, lang):
    """rofpalys lyrics providers [status | install | order | test]"""
    if PV is None:
        print("rofpalys_CyroKayAI_providers.py is missing.  Put it next to rofpalys.py and run:  python ~/rofpalys.py install")
        return 1
    id_ = lang == "id"
    act = args[0] if args else "status"
    flags = [a for a in args[1:] if a.startswith("--")]
    rest = [a for a in args[1:] if not a.startswith("--")]
    if act in ("status", "list"):
        print(PV.format_status(lang))
        if os.environ.get("ROFPALYS_LYRIC_PROVIDERS"):
            print(("(urutan dari ROFPALYS_LYRIC_PROVIDERS)" if id_ else "(order taken from ROFPALYS_LYRIC_PROVIDERS)"))
        missing = [r["name"] for r in PV.status() if not r["installed"] and r["python_ok"]]
        if missing:
            print(("\nPasang yang belum ada:  rofpalys lyrics providers install" if id_ else "\nInstall what is missing:  rofpalys lyrics providers install"))
        return 0
    if act == "install":
        names = [n for n in rest if n in PV.DEFAULT_ORDER] or None
        res = PV.install(names, flags, lambda m: print("  " + m))
        for n, (ok, msg) in res.items():
            print("  %-13s %s  %s" % (n, "ok" if ok else "FAILED", msg))
        print("\n" + PV.format_status(lang))
        if res.get("librelyrics", (False,))[0]:
            print(("\nlibrelyrics tidak punya sumber sendiri: pasang plugin pencari, lihat  librelyrics plugin list" if id_ else
                   "\nlibrelyrics has no sources of its own: install a search plugin, see  librelyrics plugin list"))
        return 0 if all(ok for ok, _ in res.values()) else 1
    if act == "order":
        if not rest:
            print(" → ".join(PV.order()) or "off")
            return 0
        arg = " ".join(rest)
        if arg.lower() in ("default", "reset"):
            o = PV.set_order(None)
        elif PV.parse_order(arg) is None:
            print("unknown provider in: %s   (known: %s)" % (arg, ", ".join(PV.DEFAULT_ORDER)))
            return 1
        else:
            o = PV.set_order(arg)
        print("order: " + (" → ".join(o) or "off (only LRCLIB / YouTube captions / lyrics.ovh)"))
        if os.environ.get("ROFPALYS_LYRIC_PROVIDERS"):
            print("note: the environment variable ROFPALYS_LYRIC_PROVIDERS is set and wins over this choice")
        return 0
    if act == "test":
        path = ""
        if rest and os.path.isfile(os.path.expanduser(rest[0])):
            path = os.path.expanduser(rest[0])
            nc = name_candidates(path)
            if not nc:
                print("cannot tell who made it: " + path)
                return 1
            artist, title = nc[0][0], nc[0][1]
        elif len(rest) >= 2:
            artist, title = rest[0], rest[1]
            path = os.path.expanduser(rest[2]) if len(rest) > 2 and os.path.isfile(os.path.expanduser(rest[2])) else ""
        else:
            print('usage: rofpalys lyrics providers test "Artist" "Title" [FILE]    or    ... test FILE')
            return 1
        if not internet_ok(force=True):
            print("no internet: the providers cannot be asked")
            return 1
        PV.reset()
        q = {"artist": artist, "title": title, "album": "", "duration": read_tags(path).get("duration", 0.0) if path else 0.0, "path": path}
        print("%s - %s%s" % (artist, title, "" if path else "   (no audio file given: lrcdl needs one)"))
        for r in PV.live_test(q, PV.order() or None):
            print("  %-13s %-26s %s%s   %.1f s" % (r["provider"], (PV.NOTE_ID if id_ else PV.NOTE_HELP).get(r["note"], r["note"]),
                                                  ("%d lines" % r["lines"]) if r["lines"] else "-", " (timed)" if r["synced"] else "", r["secs"]))
        return 0
    print('usage: rofpalys lyrics providers [status|install [NAME ...]|order LIST|test "Artist" "Title"]')
    return 1


def cli(argv):
    """rofpalys lyrics ...   (called by rofpalys.py)"""
    LY = _ly()
    sub = argv[0] if argv else ""
    rest = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    lang = "id" if os.environ.get("LANG", "").lower().startswith("id") else "en"
    if sub in ("", "help", "-h", "--help"):
        print("""rofpalys lyrics FILE ...          creator check -> internet check -> listen -> fetch -> fit the lyrics to the voice (saved in the lyric cache)
rofpalys lyrics melody FILE ...   make a melody-only track (🎶 / 🎵 on the beat) instead of lyrics
rofpalys lyrics analyze FILE      show what CyroKayAI hears: sing / melody spans, tempo, notes
rofpalys lyrics timeline FILE     the rows, line times and word times exactly as the live lyric view uses them
rofpalys lyrics cut FILE          lyrics fit only if part of the recording is cut: write a trimmed COPY + its .lrc (the original stays)
rofpalys lyrics all [--redo] [--jobs N]   make lyrics for the whole library, N songs at the same time (songs that already have CyroKayAI 3 lyrics are skipped)
rofpalys lyrics bench [FILE ...]  how fast is CyroKayAI on this device (cores, Fourier speed, minutes of music per second)
rofpalys lyrics learn             what CyroKayAI learned from your songs and corrections
rofpalys lyrics forget [-y]       erase what it learned (the saved lyrics stay)
rofpalys lyrics view on|off       the smooth Spotify-style lyric view in the window (default: on)
rofpalys lyrics providers         where the lyrics come from, in which order (syncedlyrics -> lrcdl -> lyriq -> librelyrics) and which are installed
rofpalys lyrics providers install [NAME ...] [--break-system-packages]   pip install the missing ones
rofpalys lyrics providers order LIST|default|off   for example  lyriq,syncedlyrics   (environment ROFPALYS_LYRIC_PROVIDERS wins)
rofpalys lyrics providers test "Artist" "Title" [FILE]   ask every provider the same question and show what each one answers
rofpalys lyrics reset [-y]        deep reset of the lyric side: delete saved lyrics + CyroKayAI measurements (songs, your own .lrc files and what it learned stay)
rofpalys lyrics selftest          check the fitting maths and the clock without a song and without internet
Options: --force (fit even if you have your own .lrc next to the song)   --text-notes (♫ / ♪ instead of emoji)""")
        return 0
    if "--text-notes" in flags:
        LY.set_note_style("text")
    if sub == "selftest":
        return 0 if selftest() else 1
    if sub == "bench":
        return _bench(rest, lang)
    if sub == "learn":
        print(MEM.summary(lang) if MEM is not None else "rofpalys_CyroKayAI_memory.py is missing")
        return 0
    if sub == "forget":
        if MEM is None:
            print("rofpalys_CyroKayAI_memory.py is missing")
            return 1
        if "-y" not in argv and "--yes" not in argv:
            try:
                if input("Erase what CyroKayAI learned (voice model, your corrections)? Type FORGET: ").strip() != "FORGET":
                    print("Cancelled.")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return 1
        print("Erased." if MEM.forget() else "Nothing was stored.")
        return 0
    if sub == "providers":
        return _providers_cli(argv[1:], lang)
    if sub == "view":
        if MEM is None or not rest or rest[0] not in ("on", "off"):
            print("usage: rofpalys lyrics view on|off   (now: %s)" % (("on" if MEM.get_pref("view", True) else "off") if MEM is not None else "?"))
            return 1
        MEM.set_pref("view", rest[0] == "on")
        print("smooth lyric view: " + rest[0] + "  (takes effect within a second in a running window)")
        return 0
    if sub == "reset":
        if "-y" not in argv and "--yes" not in argv:
            try:
                if input("Delete saved lyrics and CyroKayAI measurements? Type RESET: ").strip() != "RESET":
                    print("Cancelled.")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return 1
        print("Deleted %d file(s). Lyrics are made again, with the current logic, the next time a song is played (or: rofpalys lyrics all)." % reset_cache())
        return 0
    if sub == "all":
        E = __import__("rofpalys_engine")
        E.load_settings()
        songs = sorted(E.scan_library_sync())
        print("%d songs" % len(songs))

        def prog(k, n, p, r):
            print("  [%d/%d] %s -> %s" % (k, n, os.path.basename(p), (r.get("source") + (" %d%%" % round(r["confidence"] * 100) if r.get("confidence") is not None else "")) if r.get("raw") else "nothing"))
        jobs = 1
        for i, a in enumerate(argv):
            if a == "--jobs" and i + 1 < len(argv) and argv[i + 1].isdigit():
                jobs = int(argv[i + 1])
            elif a.startswith("--jobs="):
                jobs = int(a.split("=", 1)[1] or 1)
        rest = [x for x in rest if not x.isdigit()]
        d, s, f = process_many(songs, "--redo" in flags, prog, None, jobs)
        print("done: %d   skipped (already CyroKayAI): %d   no lyrics: %d" % (d, s, f))
        return 0
    if sub in ("melody", "analyze", "cut", "timeline"):
        files = rest
    else:
        sub, files = "auto", [a for a in argv if not a.startswith("--")]
    if not files:
        print("usage: rofpalys lyrics [melody|analyze|cut] FILE ...")
        return 1
    rc = 0
    for p in files:
        p = os.path.expanduser(p)
        if not os.path.isfile(p):
            print("not found: " + p)
            rc = 1
            continue
        print("== " + os.path.basename(p))
        if sub == "analyze":
            A = analyze(p, use_cache=False)
            if A is None:
                print("  cannot listen (ffmpeg missing or file unreadable)")
                rc = 1
                continue
            print("  " + A.summary())
            print("\n".join(_timeline(A)))
            if A.learn:
                print("  learned detector: %s" % A.learn.get("tag"))
            if A.notes:
                print("  first notes: " + " ".join("%s@%s" % (midi_name(m), fmt_t(a)) for a, b, m in A.notes[:16]))
            continue
        if sub == "timeline":
            rc = max(rc, _timeline_rows(p, lang))
            continue
        if sub == "melody":
            A = analyze(p, None, True, keep_features=np is not None)
            r = _finish(_blank(), melody_track(A), "CyroKayAI melody", True, "melody")
            LY.write_cache(p, r["raw"], r["source"])
            print("  melody-only track saved (%d markers)" % len(r["pairs"]))
            continue
        own = LY.sidecar(p)
        if own and "--force" not in flags and sub == "auto":
            print("  you have your own lyrics file next to the song (%s) - not touched (use --force to fit it anyway)" % os.path.basename(own))
            continue
        r = auto_lyrics(p, "", "", -1.0, True, ("en",), None, (lambda m: print("  ... " + m)))
        print("  " + describe(r, lang).replace("\n", "\n  "))
        if sub == "cut":
            if not r.get("cuts"):
                print("  no cut needed: the lyrics fit this recording without cutting")
            else:
                out = export_trimmed(p, r["cuts"])
                if out:
                    open(os.path.splitext(out)[0] + ".lrc", "w", encoding="utf-8").write(LY.to_lrc(retime(r["pairs"], r["cuts"])) + "\n")
                    print("  trimmed copy: %s\n  cut out (seconds): %s" % (out, ", ".join("%s-%s" % (fmt_t(a), fmt_t(b)) for a, b in r["cuts"])))
                else:
                    print("  could not write the trimmed copy (ffmpeg with mp3 support needed)")
                    rc = 1
        elif not r.get("raw"):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))

# END-OF-FILE rofpalys_CyroKayAI_lyric.py

