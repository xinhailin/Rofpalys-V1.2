#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI memory: what CyroKayAI has learned from YOUR songs and YOUR corrections (kept on this device, never uploaded)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Three things are remembered, in one small JSON file (cyrokay_memory.json next to the cache):
  1. VOICE MODEL   every time lyrics with timestamps are fitted to a song, the sounds under the sung lines and the sounds in the silences are added
                   to a running tally. After a few songs this tally is a detector taught on YOUR music; it is used for songs without lyrics - but
                   only once it has proven (on songs it had not seen) that it beats the generic detector, and the proof is kept here too.
  2. NUDGES        when you move the lyrics of a song earlier / later (the +/- buttons) the amount is remembered for that song.
                   The typical nudge over several songs becomes this device's lead (Bluetooth speakers and slow screens delay things).
  3. COUNTS        how many songs were learned, so the status line can say it.
  4. PREFS         small CyroKayAI settings (the smooth lyric view on / off).
`rofpalys lyrics reset` keeps this memory (it is knowledge, not cache); `rofpalys lyrics forget` or `rofpalys reset` erases it."""
import hashlib
import json
import math
import os
import threading
import time

try:
    import numpy as np
except Exception:
    np = None
try:
    import rofpalys_library as lib
except Exception:
    lib = None

__version__ = "1.0"
CACHE_ROOT = getattr(lib, "CACHE_DIR", None) or os.path.join(os.path.expanduser("~"), ".cache", "rofpalys")
MEM_PATH = os.path.join(CACHE_ROOT, "cyrokay_memory.json")
_LOCK = threading.RLock()
_STATE = {"d": None}
MAX_NUDGES = 400


def _blank():
    return {"v": 1, "songs": 0, "voice": None, "eval": {"n": 0, "heur": 0.0, "glob": 0.0}, "nudge": {}, "lead": {"n": 0, "sum": 0.0}, "log": [], "prefs": {}, "seen": []}


def load():
    with _LOCK:
        if _STATE["d"] is not None:
            return _STATE["d"]
        d = None
        try:
            with open(MEM_PATH, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or d.get("v") != 1:
                d = None
        except (OSError, ValueError):
            d = None
        _STATE["d"] = d or _blank()
        return _STATE["d"]


def save():
    with _LOCK:
        d = _STATE["d"]
        if d is None:
            return False
        try:
            os.makedirs(os.path.dirname(MEM_PATH), exist_ok=True)
            with open(MEM_PATH + ".part", "w", encoding="utf-8") as f:
                json.dump(d, f, separators=(",", ":"))
            os.replace(MEM_PATH + ".part", MEM_PATH)
            return True
        except OSError:
            return False


def seen(sid):
    """Has this song already taught the voice model? (Fitting the same song again must not count it twice.)"""
    with _LOCK:
        return sid in load().get("seen", [])


def mark_seen(sid):
    with _LOCK:
        d = load()
        d["seen"] = (d.get("seen", []) + [sid])[-600:]


def forget():
    """Erase everything CyroKayAI learned. -> True if a memory file existed."""
    with _LOCK:
        _STATE["d"] = _blank()
        try:
            os.remove(MEM_PATH)
            return True
        except OSError:
            return False


def song_id(path):
    """Stable id of a song file (path + size; the same id for every CyroKayAI version)."""
    try:
        sz = os.stat(path).st_size
    except OSError:
        sz = 0
    return hashlib.sha1(("%s|%d" % (os.path.abspath(path), sz)).encode("utf-8", "replace")).hexdigest()[:16]


# ------------------------------------------------------------------ 1. the voice model: running class statistics (D = number of features)
def add_voice_stats(X, pos, neg, tag=""):
    """Add one song's labelled frames (X: frames x D, pos / neg: boolean masks) to the tally. Counts, sums and scatter matrices are kept, so the
    detector can be recomputed exactly at any time and no audio is ever stored."""
    if np is None or pos.sum() < 100 or neg.sum() < 100:
        return False
    with _LOCK:
        d = load()
        D = X.shape[1]
        v = d.get("voice")
        if not v or v.get("D") != D:
            v = {"D": D, "n1": 0, "n0": 0, "s1": [0.0] * D, "s0": [0.0] * D, "S1": [[0.0] * D for _ in range(D)], "S0": [[0.0] * D for _ in range(D)]}
        x1, x0 = X[pos].astype(np.float64), X[neg].astype(np.float64)
        decay = 0.98                                                        # old songs fade slowly: the tally follows a changing taste
        v["n1"], v["n0"] = v["n1"] * decay + len(x1), v["n0"] * decay + len(x0)
        v["s1"] = (np.asarray(v["s1"]) * decay + x1.sum(0)).tolist()
        v["s0"] = (np.asarray(v["s0"]) * decay + x0.sum(0)).tolist()
        v["S1"] = (np.asarray(v["S1"]) * decay + x1.T @ x1).tolist()
        v["S0"] = (np.asarray(v["S0"]) * decay + x0.T @ x0).tolist()
        d["voice"] = v
        d["songs"] = d.get("songs", 0) + 1
        d["log"] = (d.get("log", []) + [{"t": int(time.time()), "tag": tag, "n1": int(len(x1)), "n0": int(len(x0))}])[-30:]
    return True


def voice_model():
    """(w, b) of the detector taught on every learned song so far, or None (needs at least 2 songs). Score = X @ w + b, higher = more like singing."""
    if np is None:
        return None
    with _LOCK:
        d = load()
        v = d.get("voice")
        if not v or d.get("songs", 0) < 2 or v["n1"] < 500 or v["n0"] < 500:
            return None
        n1, n0 = v["n1"], v["n0"]
        s1, s0 = np.asarray(v["s1"]), np.asarray(v["s0"])
        m1, m0 = s1 / n1, s0 / n0
        S1, S0 = np.asarray(v["S1"]), np.asarray(v["S0"])
        Sw = ((S1 - n1 * np.outer(m1, m1)) + (S0 - n0 * np.outer(m0, m0))) / (n1 + n0) + 0.05 * np.eye(len(m1))
        try:
            w = np.linalg.solve(Sw, m1 - m0)
        except np.linalg.LinAlgError:
            return None
        return w, float(-0.5 * w @ (m1 + m0)), float(m1 @ w), float(m0 @ w)


def record_eval(heur_auc, glob_auc):
    """Keep score of how well the generic detector and the learned global detector separated a NEW song (held out) - the proof for use_global()."""
    with _LOCK:
        e = load().setdefault("eval", {"n": 0, "heur": 0.0, "glob": 0.0})
        e["n"] += 1
        e["heur"] += float(heur_auc)
        e["glob"] += float(glob_auc)


def use_global():
    """True when the taught detector has beaten the generic one on at least 3 songs it had not seen before (by 0.03 AUC or more on average)."""
    with _LOCK:
        e = load().get("eval", {})
        n = e.get("n", 0)
        return bool(n >= 3 and (e["glob"] - e["heur"]) / n >= 0.03 and e["glob"] / n >= 0.75 and voice_model() is not None)


# ------------------------------------------------------------------ 2. nudges and the device lead
def nudge(path, seconds):
    """The user moved the lyrics of this song by `seconds` (negative = earlier). Returns the total nudge now remembered for the song."""
    with _LOCK:
        d = load()
        sid = song_id(path)
        tot = round(float(d["nudge"].get(sid, 0.0)) + float(seconds), 3)
        tot = max(-10.0, min(10.0, tot))
        if abs(tot) < 0.005:
            d["nudge"].pop(sid, None)
        else:
            d["nudge"][sid] = tot
        if len(d["nudge"]) > MAX_NUDGES:
            for k in list(d["nudge"])[:len(d["nudge"]) - MAX_NUDGES]:
                d["nudge"].pop(k, None)
        return tot


def song_nudge(path):
    with _LOCK:
        return float(load()["nudge"].get(song_id(path), 0.0))


def has_nudge(path):
    with _LOCK:
        return song_id(path) in load()["nudge"]


def set_nudge(path, seconds):
    with _LOCK:
        d = load()
        sid = song_id(path)
        if abs(seconds) < 0.005:
            d["nudge"].pop(sid, None)
        else:
            d["nudge"][sid] = round(max(-10.0, min(10.0, float(seconds))), 3)


def shift_for(path):
    """Seconds the lyric view shows this song's lyrics later (negative = earlier): the user's own correction of THIS song if there is one, else the typical
    correction of this device (a slow Bluetooth speaker delays every song the same way)."""
    return song_nudge(path) if has_nudge(path) else device_lead()


def device_lead():
    """Typical nudge over the songs the user corrected (median), in seconds; 0 until at least 3 songs agree. Used for songs without a correction of their own."""
    with _LOCK:
        v = sorted(load()["nudge"].values())
        if len(v) < 3:
            return 0.0
        med = v[len(v) // 2]
        spread = sum(abs(x - med) for x in v) / len(v)
        return med if spread <= 0.25 + 0.5 * abs(med) else 0.0           # only when the corrections agree with each other


def get_pref(name, default=None):
    """A small setting that belongs to CyroKayAI (for example whether the smooth lyric view is on)."""
    with _LOCK:
        return load().get("prefs", {}).get(name, default)


def set_pref(name, value):
    with _LOCK:
        load().setdefault("prefs", {})[name] = value
    return save()


def summary(lang="en"):
    with _LOCK:
        d = load()
        e = d.get("eval", {})
        n = e.get("n", 0)
        id_ = lang == "id"
        parts = ["%s: %d" % ("lagu dipelajari" if id_ else "songs learned", d.get("songs", 0))]
        if n:
            parts.append("%s %.2f / %s %.2f (AUC, %d %s)" % ("model sendiri" if id_ else "own model", e["glob"] / n, "umum" if id_ else "generic", e["heur"] / n, n,
                                                          "lagu uji" if id_ else "test songs"))
        parts.append(("model sendiri dipakai untuk lagu tanpa lirik" if id_ else "own model used for songs without lyrics") if use_global() else
                     ("model sendiri belum terbukti lebih baik" if id_ else "own model not proven better yet"))
        lead = device_lead()
        if lead:
            parts.append("%s %+.2f s" % ("geser perangkat" if id_ else "device shift", lead))
        parts.append("%s: %d" % ("koreksi tersimpan" if id_ else "saved corrections", len(d["nudge"])))
        return "  ·  ".join(parts)


# END-OF-FILE rofpalys_CyroKayAI_memory.py

