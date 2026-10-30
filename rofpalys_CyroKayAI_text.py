#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI text: the maths of the lyric TEXT (syllables, how long a line takes to sing, where the file says "nobody sings", word timing)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The 'reading' half of CyroKayAI. Nothing here listens to audio and nothing here talks to the network.

  syllables(text)         how many sung syllables a line has (any alphabet; Japanese / Chinese / Korean count one per character)
  est_sung(text)          about how long the line takes to sing (a GUESS: slow ballads and fast raps differ a lot)
  silence_after(...)      where the lyric file says the voice is silent. ONLY what the file is sure about counts:
                            - after an explicit break line (an empty [mm:ss] row = "the voice stops here"), and
                            - the part of a VERY long gap that even a slowly sung line could not fill.
                          A gap that is merely longer than the guess of the sung time is NOT silence: the line may simply be sung slowly.
                          (Version 1 treated every gap of 4 s as silence. A slow song then looked 'silent' while the singer was singing.)
  word_times(...)         the time of every word of a line, from the line's start and end: syllable-weighted, optionally pulled onto the
                          vocal onsets the ears found."""
import re

__version__ = "1.0"
_CJK = r"[぀-ヿ㐀-鿿가-힯]"
SYL_SEC = 0.27                                      # a sung syllable takes about this long (3.7 per second)
LONG_GAP = 14.0                                     # between two line starts this long, the middle part is believed silent even without a break line


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def syllables(text):
    cjk = len(re.findall(_CJK, text))
    words = re.findall(r"[^\W\d_]+", re.sub(_CJK, " ", text), flags=re.U)
    return cjk + sum(max(1, len(re.findall(r"[aeiouyàáâäãåāèéêëēìíîïīòóôöõōùúûüū]+", w.lower()))) for w in words)


def est_sung(text):
    """How long a line probably takes to sing, in seconds (a guess, kept between 1 and 9 s)."""
    return clamp(0.35 + SYL_SEC * syllables(text), 1.0, 9.0)


def silence_after(sung, x, cap=None):
    """(start, end) in LYRIC time of the silence that follows sung line x, or None when the file does not say that the voice is silent there.
    sung: items {t, text, dur, brk_after} (see rofpalys_CyroKayAI_lyric.make_items).  cap: the silence is cut to at most this many seconds."""
    it = sung[x]
    e = it["t"] + it["dur"]
    if x + 1 >= len(sung):
        a, b = (e + 0.3, e + 8.0) if it["brk_after"] else (None, None)
    else:
        st = sung[x + 1]["t"]
        if it["brk_after"] and st - e >= 1.2:
            a, b = e + 0.3, st - 0.3                                      # the file says: the voice stops at the break line
        elif st - it["t"] >= LONG_GAP:
            a, b = it["t"] + 2.2 * it["dur"] + 3.0, st - 0.5               # even a slowly sung line (twice the guess) is over by then
        else:
            a, b = None, None
    if a is None or b - a < 0.4:
        return None
    if cap is not None:
        b = min(b, a + cap)
    return (a, b)


def lead_silence(sung, cap=None):
    """The silence before the first line (an intro), or None."""
    t0 = sung[0]["t"]
    if t0 < 2.0:
        return None
    a, b = 0.3, t0 - 0.3
    if cap is not None:
        a = max(a, b - cap)
    return (a, b) if b - a >= 0.4 else None


def word_weights(words):
    """Relative sung length of each word: its syllables plus a little for the breath / consonants between words."""
    return [max(1, syllables(w)) + 0.25 for w in words]


def split_words(text):
    """The words of a line as they are shown (punctuation stays attached to its word)."""
    return text.split()


def word_times(text, t0, t1, onsets=None, snap=0.09):
    """[(word, start, end)] for a line that is sung from t0 to t1. The line is divided over its words by syllable weight. If vocal onsets are given
    ([(seconds, strength)]), a word start moves onto an onset within +-snap seconds (the voice really begins a word there) while the order and a
    minimum word length of 80 ms are kept. Honest limit: this is an estimate from syllable counts and onsets, not speech recognition."""
    words = split_words(text)
    if not words:
        return []
    t1 = max(t1, t0 + 0.2 * len(words))
    w = word_weights(words)
    tot = float(sum(w))
    edges, acc = [t0], 0.0
    for x in w:
        acc += x
        edges.append(t0 + (t1 - t0) * acc / tot)
    if onsets:
        near = [o for o, s in onsets if t0 - snap <= o <= t1 + snap and s >= 0.5]
        for k in range(1, len(words)):                                  # interior word starts only: the first starts with the line, the last ends with it
            c = [o for o in near if abs(o - edges[k]) <= snap]
            if c:
                best = min(c, key=lambda o: abs(o - edges[k]))
                lo, hi = edges[k - 1] + 0.08, edges[k + 1] - 0.08
                if lo <= hi:
                    edges[k] = clamp(best, lo, hi)
    return [(words[k], edges[k], edges[k + 1]) for k in range(len(words))]


# END-OF-FILE rofpalys_CyroKayAI_text.py

