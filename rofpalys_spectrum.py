#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - real spectrum for the visualizer (the bars follow the REAL song, not a simulation)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The song is decoded once by ffmpeg to low-rate mono samples (a few MB), then the loudness of each frequency band is measured
around the position that is playing (Goertzel algorithm, pure Python, no numpy). Needs ffmpeg; without it the callers keep the simulation."""
import array
import math
import shutil
import subprocess
import threading

SR = 11025                   # sample rate used for the analysis (covers up to ~5.5 kHz: where nearly all of the beat and melody is)
WIN = 256                    # samples per measurement (~23 ms)
MAX_SECONDS = 1500           # longer than 25 minutes: not analysed (memory), callers fall back to the simulation
BANDS = 20
BINS_PER_BAND = 5            # a band is measured at up to this many frequencies across its width, the loudest counts (a tone between two bands is not missed)
_data = {}                   # path -> array('h')
_loading = set()
_lock = threading.Lock()
_coef = None


def _band_freqs(n=BANDS, lo=45.0, hi=5000.0):
    r = (hi / lo) ** (1.0 / (n - 1))
    return [lo * r ** i for i in range(n)]


def _coefs():
    """For every band: the Goertzel coefficients of the frequency bins that lie inside it."""
    global _coef
    if _coef is None:
        fr = _band_freqs()
        r = fr[1] / fr[0]
        half = r ** 0.5
        res = SR / float(WIN)
        out = []
        for f in fr:
            k_lo, k_hi = max(1, int(round(f / half / res))), max(1, int(round(f * half / res)))
            k_hi = max(k_lo, min(k_hi, WIN // 2 - 1))
            n = min(BINS_PER_BAND, k_hi - k_lo + 1)
            ks = sorted({int(round(k_lo + (k_hi - k_lo) * i / float(max(1, n - 1)))) for i in range(n)})
            out.append([2.0 * math.cos(2.0 * math.pi * k / WIN) for k in ks])
        _coef = out
    return _coef


def available():
    return shutil.which("ffmpeg") is not None


def ready(path):
    return path in _data


def load(path):
    """Start decoding `path` in the background (only the last two songs are kept in memory)."""
    if not available() or path in _data:
        return
    with _lock:
        if path in _loading:
            return
        _loading.add(path)

    def work():
        try:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(MAX_SECONDS), "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                                 capture_output=True, timeout=120).stdout
            if len(raw) > 2000:
                a = array.array("h")
                a.frombytes(raw[:len(raw) // 2 * 2])
                with _lock:
                    while len(_data) >= 2:
                        _data.pop(next(iter(_data)))
                    _data[path] = a
        except Exception:
            pass
        finally:
            with _lock:
                _loading.discard(path)
    threading.Thread(target=work, daemon=True).start()


def forget():
    with _lock:
        _data.clear()


def _bands(samples, start):
    out = []
    seg = samples[start:start + WIN]
    if len(seg) < WIN:
        return None
    # a light window (raised cosine) keeps the bands from smearing into each other
    w = _window()
    x = [seg[i] * w[i] for i in range(WIN)]
    for band in _coefs():
        best = 0.0
        for c in band:
            s1 = s2 = 0.0
            for v in x:
                s1, s2 = v + c * s1 - s2, s1
            power = s1 * s1 + s2 * s2 - c * s1 * s2
            if power > best:
                best = power
        out.append(math.sqrt(best) / (WIN / 4.0 * 32768.0))             # 1.0 = a full-scale sine at this band
    return out


_win = None


def _window():
    global _win
    if _win is None:
        _win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (WIN - 1)) for i in range(WIN)]
    return _win


def levels(path, pos, n=32):
    """n values 0..1 for the bands around `pos` seconds, or None if the song is not analysed (yet)."""
    a = _data.get(path)
    if a is None:
        return None
    b = _bands(a, int(pos * SR) - WIN // 2 if pos * SR >= WIN // 2 else 0)
    if b is None:
        return [0.0] * n
    lv = []
    for i, m in enumerate(b):
        db = 20.0 * math.log10(m + 1e-7)
        v = (db + 62.0 + 4.0 * i / max(1, len(b) - 1) * 3.0) / 62.0       # -62 dB .. 0 dB, a gentle lift for the quieter high bands
        lv.append(max(0.0, min(1.0, v)))
    if n == len(lv):
        return lv
    return [lv[min(len(lv) - 1, int(i * len(lv) / float(n)))] for i in range(n)]


# END-OF-FILE rofpalys_spectrum.py

