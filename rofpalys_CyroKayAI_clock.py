#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI clock: the lyric timeline, a steady play clock and the Spotify-style scroll maths (no Tk in here: it is all numbers)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Three parts, all pure maths so they can be tested without a screen:

  Timeline   the lyric sheet as rows (a sung line, or a melody row with 🎶 / 🎵): when each row becomes active, when the voice really starts and stops,
             the time of every WORD (syllable-weighted, pulled onto the vocal onsets the ears found), the beat pulse for melody rows.
  PlayClock  a smooth, steady song time. The player reports its position a few times per second (maybe in whole seconds); the screen is drawn 30-60 times
             per second. The clock fills the gaps by following the monotonic clock and is corrected gently (a phase-locked loop with a slew limit), so the
             lyrics never jitter and never jump - but a real seek or a new song is followed at once. It learns the report quantum (whole-second
             reports), the playback speed (slowed / sped-up effects) and applies the per-device lead (rofpalys_CyroKayAI_memory).
  Sheet      the scroll: a pure function of the song time. A row becomes active, the sheet glides to it with an ease-in-out curve (about 0.45 s, shorter
             when lines follow each other quickly), the old row fades out while the new one fades in. A seek or the mouse wheel adds an offset that decays
             smoothly. Row brightness, karaoke fill of the line that is being sung and the beat pulse of melody rows are returned per frame.
Honest limit: word times are an ESTIMATE (syllables + onsets), not speech recognition; they are as good as the line times they come from."""
import bisect
import math
import time

import rofpalys_CyroKayAI_text as TX

__version__ = "1.0"
ANTICIPATE = 0.10                                   # the glide to a row starts this long before the row's time
GLIDE_MIN, GLIDE_MAX = 0.28, 0.55                   # seconds a glide takes (shorter when the lines come quickly)
MIN_NOTE_ROW = 2.5                                  # an empty lyric row shorter than this shows nothing; longer ones show a melody marker


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ease(u):
    """Ease-in-out (smoother than a cubic): 0 -> 1 with zero speed at both ends."""
    u = clamp(u)
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


# ------------------------------------------------------------------ the sheet as rows
class Row:
    __slots__ = ("i", "kind", "text", "t0", "v0", "v1", "words", "chars")

    def __init__(self, i, kind, text, t0, v0, v1, words):
        self.i, self.kind, self.text, self.t0, self.v0, self.v1, self.words = i, kind, text, t0, v0, v1, words
        self.chars = []                              # [(char start, char end)] of every word inside " ".join(words)
        if words:
            pos = 0
            for w, _, _ in words:
                self.chars.append((pos, pos + len(w)))
                pos += len(w) + 1

    def sung_chars(self, t):
        """How many characters of the line are 'already sung' at time t (a float: it grows smoothly inside a word)."""
        if not self.words or t <= self.v0:
            return 0.0
        for (w, a, b), (c0, c1) in zip(self.words, self.chars):
            if t < a:
                return float(c0)
            if t < b:
                return c0 + (c1 - c0) * (t - a) / max(1e-6, b - a)
        return float(self.chars[-1][1])


def _voice_end(A, s, guess):
    """Where the voice of a line that starts at s really stops: the end of its singing span if that is plausible, else the guess."""
    if A is not None and getattr(A, "engine", "") in ("full", "selftest") and A.sing:
        for a, b in A.sing:
            if a <= s + 0.4 < b:
                return b if s + 0.6 <= b <= guess + 3.0 else guess
            if a > s + 0.4:
                break
    return guess


class Timeline:
    """rows + lookups. pairs: [(time the row becomes active, text)] as the player shows them (a fitted line is already LEAD seconds early; an empty or
    a note text is a melody row). A: the Analysis of the song (optional: word times snap to vocal onsets, line ends follow the singing spans, melody
    rows pulse on the beat). lead: how much earlier than the voice the rows are shown (CyroKayAI lyrics: its LEAD_SEC; other lyrics: 0)."""

    def __init__(self, pairs, A=None, lead=0.0, duration=None, note_hi="🎶", note_lo="🎵", is_note=None):
        self.A, self.lead = A, lead
        self.duration = duration or (getattr(A, "duration", 0.0) if A is not None else 0.0)
        self.note_hi, self.note_lo = note_hi, note_lo
        is_note = is_note or (lambda s: s.strip() in (note_hi, note_lo, "♫", "♪"))
        pairs = sorted([(float(t), x) for t, x in pairs], key=lambda p: p[0])
        raw = []
        for t, x in pairs:
            x = (x or "").strip()
            raw.append((t, "note" if (not x or is_note(x)) else "line", x))
        rows = []
        for k, (t, kind, x) in enumerate(raw):
            nxt = raw[k + 1][0] if k + 1 < len(raw) else (self.duration if self.duration > t else t + 8.0)
            if kind == "note":
                if nxt - t < MIN_NOTE_ROW and (k + 1 < len(raw)):
                    continue                                              # a short blank between two lines: nothing to show
                sym = x if x else note_hi
                rows.append(Row(len(rows), "note", sym, t, t, nxt, []))
                continue
            v0 = t + lead
            guess = v0 + TX.est_sung(x)
            v1 = _voice_end(A, v0, guess)
            v1 = max(v0 + 0.4, min(v1, nxt + lead - 0.05 if k + 1 < len(raw) else v1))
            ons = A.onsets if (A is not None and getattr(A, "engine", "") in ("full", "selftest")) else None
            rows.append(Row(len(rows), "line", x, t, v0, v1, TX.word_times(x, v0, v1, ons)))
        self.rows = rows
        self.t0s = [r.t0 for r in rows]
        self.beats = list(getattr(A, "beats", []) or []) if A is not None else []

    @classmethod
    def from_raw(cls, raw, A=None, lead=0.0, duration=None):
        import rofpalys_lyrics as LY
        pairs, synced = LY.parse(raw)
        if not synced:
            return None
        return cls(pairs, A, lead, duration, LY.NOTE_HI, LY.NOTE_LO, LY.is_note)

    def __len__(self):
        return len(self.rows)

    def active(self, t):
        """Index of the row that is active at time t (-1 before the first row)."""
        return bisect.bisect_right(self.t0s, t) - 1

    def row_progress(self, i, t):
        """0..1: how far through its time span the row is (for a note row: until the next row starts)."""
        r = self.rows[i]
        a, b = (r.t0, r.v1) if r.kind == "note" else (r.v0, r.v1)
        return clamp((t - a) / max(0.2, b - a))

    def pulse(self, t):
        """0..1 beat pulse for melody rows: 1 on a beat, fading out in about 0.3 s. Without a beat grid a slow breathing."""
        if self.beats:
            i = bisect.bisect_right(self.beats, t) - 1
            if i < 0:
                return 0.0
            d = t - self.beats[i]
            return math.exp(-d * 7.0) if d < 0.6 else 0.0
        return 0.5 + 0.5 * math.sin(2 * math.pi * t / 2.4)


# ------------------------------------------------------------------ the steady play clock
class PlayClock:
    """Steady song time from a coarse, jittery position report. update(pos, playing) whenever the player's position is read (any rate), time() every frame.
    ok = how many seconds the last report was trusted; jumped = True once after a seek / new song (the sheet then animates the catch-up)."""
    SEEK_TOL = 0.6                                  # a report this far from the prediction is a real seek, not jitter
    GAIN = 0.2                                      # how fast the clock is pulled toward a report (per report)
    SLEW_RATE = 0.08                                # the clock is pulled at most this many seconds per second toward the reports: no visible jump from jitter

    def __init__(self, mono=time.monotonic, lead=0.0):
        self.mono = mono
        self.lead = lead                            # seconds added to the song time (device delay: Bluetooth, slow screen; the user's nudge)
        self.reset()

    def reset(self, track=None):
        self.track = track
        self.a_now, self.a_pos = None, 0.0           # anchor: at monotonic time a_now the song time was a_pos (the line continues with slope `rate`)
        self.rate = 1.0
        self.playing = False
        self.frozen = 0.0
        self.q = 0.0                                # report quantum (0.0 = fine reports)
        self.jumped = False
        self._raw, self._deltas, self._polls, self._same = None, [], 0, 0
        self._hist = []                             # (mono, raw) of fresh reports, for the playback speed
        self.last_update = None
        self._last_fresh = None

    def _pred(self, now):
        return self.a_pos + self.rate * (now - self.a_now)

    def _move(self, now, pos=None, rate=None):
        """Re-anchor at `now` without a jump (unless a new position is given): the song time stays continuous when the speed estimate changes."""
        self.a_pos = self._pred(now) if pos is None else pos
        self.a_now = now
        if rate is not None:
            self.rate = rate

    def _learn_quantum(self, raw):
        """Whole-second (or 0.25 s ...) reports: most polls repeat the last value and the changes are all the same size."""
        self._polls += 1
        if self._raw is not None and abs(raw - self._raw) < 1e-9:
            self._same += 1
            return False
        if self._raw is not None:
            d = raw - self._raw
            if 0 < d < 5.0:
                self._deltas = (self._deltas + [d])[-8:]
        if self._polls >= 12 and len(self._deltas) >= 4 and self._same >= 0.5 * self._polls:
            s = sorted(self._deltas)
            med = s[len(s) // 2]
            if med >= 0.05 and all(abs(x - med) <= 0.03 * med + 0.004 for x in s[1:-1]):
                self.q = med
        elif self._polls >= 30 and self._same < 0.3 * self._polls:
            self.q = 0.0
        return True

    def _learn_rate(self, now, raw):
        """Playback speed (slowed / sped-up effects): the slope of the reports over the last ~2 s, trusted only when the points sit on a line."""
        h = self._hist
        h.append((now, raw))
        while h and now - h[0][0] > 2.5:
            h.pop(0)
        if self.q > 0 or len(h) < 8 or h[-1][0] - h[0][0] < 1.2:
            if self.q > 0 and self.rate != 1.0:
                self._move(now, rate=1.0)
            return
        n = len(h)
        mx, my = sum(x for x, _ in h) / n, sum(y for _, y in h) / n
        sxx = sum((x - mx) ** 2 for x, _ in h)
        if sxx < 1e-9:
            return
        slope = sum((x - mx) * (y - my) for x, y in h) / sxx
        res = max(abs(y - (my + slope * (x - mx))) for x, y in h)
        if 0.4 <= slope <= 2.5 and res < 0.02:
            self._move(now, rate=self.rate + 0.3 * (slope - self.rate))

    def update(self, raw, playing=True, now=None, track=None):
        """Feed one position report (seconds in the song)."""
        now = self.mono() if now is None else now
        raw = float(raw)
        if track is not None and track != self.track:
            self.reset(track)
            self.jumped = True
        self.last_update = now
        if not playing:
            self.playing, self.frozen, self.a_now = False, raw, None
            self._raw = raw
            return
        fresh = self._learn_quantum(raw)
        if self.a_now is None or not self.playing:
            self.a_now, self.a_pos, self.playing, self.jumped = now, raw, True, True
            self._hist = [(now, raw)]
            self._raw = raw
            return
        if fresh:
            pred = self._pred(now)
            lo, hi = raw, raw + (self.q if self.q > 0 else 0.0)                    # a floor-quantised report: the true time is somewhere in [raw, raw + q)
            err = 0.0 if lo <= pred <= hi else (lo - pred if pred < lo else hi - pred)
            if abs(err) > self.SEEK_TOL + self.q:
                self._move(now, pos=raw)
                self._hist = [(now, raw)]
                self.jumped = True
            else:
                lim = self.SLEW_RATE * clamp(now - self._last_fresh, 0.02, 0.5) if self._last_fresh is not None else 0.01
                self._move(now, pos=pred + clamp(self.GAIN * err, -lim, lim))
            self._last_fresh = now
            if self.q == 0:
                self._learn_rate(now, raw)
        self._raw = raw

    def time(self, now=None):
        """The song time right now (seconds), steady between reports; includes the device lead."""
        if not self.playing or self.a_now is None:
            return self.frozen + self.lead
        now = self.mono() if now is None else now
        return self._pred(now) + self.lead

    def take_jump(self):
        """True once after a seek / new song / resume (the sheet uses it to animate the catch-up instead of teleporting)."""
        j, self.jumped = self.jumped, False
        return j


# ------------------------------------------------------------------ the scroll
class Sheet:
    """Pixel maths of the lyric sheet. layout(heights) once per size change, then frame(t, ...) for every drawn frame (a pure function of the song time
    plus a decaying offset after seeks / mouse wheel)."""
    TAU = 0.14                                      # the offset after a seek / wheel decays with this time constant (seconds)
    HOLD = 2.2                                      # the sheet waits this long after the last mouse wheel move before it returns to the song

    def __init__(self, timeline, gap_px=18.0):
        self.tl, self.gap = timeline, gap_px
        self.heights, self.centers, self.total = [], [], 0.0
        self.res, self.res_hold_until = 0.0, 0.0
        self._last_off = None
        n = len(timeline)
        self.tstart, self.dur = [], []
        end_prev = -1e9
        for i, r in enumerate(timeline.rows):
            gap_t = r.t0 - timeline.rows[i - 1].t0 if i else 1.0
            d = clamp(gap_t * 0.8, GLIDE_MIN, GLIDE_MAX)
            s = max(r.t0 - ANTICIPATE, end_prev)
            self.tstart.append(s)
            self.dur.append(d)
            end_prev = s + d
        self.n = n

    def layout(self, heights):
        """heights: pixel height of every row (wrapped text). -> centers of the rows from the top of the sheet."""
        self.heights = list(heights)
        self.centers, y = [], 0.0
        for h in self.heights:
            self.centers.append(y + h / 2.0)
            y += h + self.gap
        self.total = y
        self._last_off = None
        return self.centers

    def cont_index(self, t):
        """Continuous 'reading position': i (the active row) + how far the glide to the next row has gone. a(t) in [-1, n-1]."""
        if not self.n:
            return -1.0
        k = bisect.bisect_right(self.tstart, t) - 1
        if k < 0:
            return -1.0
        u = (t - self.tstart[k]) / self.dur[k]
        return (k - 1) + ease(u)

    def center_at(self, a):
        """Pixel position (in the sheet) of the continuous index a."""
        if not self.centers:
            return 0.0
        if a <= 0:
            return self.centers[0]
        i = min(int(a), len(self.centers) - 1)
        if i >= len(self.centers) - 1:
            return self.centers[-1]
        f = a - i
        return self.centers[i] + (self.centers[i + 1] - self.centers[i]) * f

    def jump(self, t_new, wall):
        """The song time jumped (seek, new song, resume): keep what is on screen and let the difference fade out smoothly."""
        if self._last_off is not None and self.centers:
            new_off = self.center_at(self.cont_index(t_new))
            self.res += self._last_off - new_off
            self.res_hold_until = 0.0

    def wheel(self, dy, wall):
        """The user scrolls with the mouse wheel: dy pixels (positive = the sheet moves up). The sheet returns to the song after HOLD seconds."""
        self.res += dy
        self.res_hold_until = wall + self.HOLD

    def frame(self, t, wall, dt):
        """-> dict(offset, a, active, rows=[(i, y_center_from_focus, focus, dist)]). offset = sheet position of the focus line (pixels);
        a row's screen y = focus_y + y_center_from_focus. focus: 1 = the active row, 0 = not (cross-fades during the glide); dist: distance in rows from the
        reading position (for dimming)."""
        a = self.cont_index(t)
        off = self.center_at(a)
        if wall >= self.res_hold_until and abs(self.res) > 0.01:
            self.res *= math.exp(-dt / self.TAU)
        elif abs(self.res) <= 0.01:
            self.res = 0.0
        disp = off - self.res
        self._last_off = off - self.res
        i_act = self.tl.active(t)
        k = bisect.bisect_right(self.tstart, t) - 1
        u = ease((t - self.tstart[k]) / self.dur[k]) if k >= 0 else 0.0
        rows = []
        for i, c in enumerate(self.centers):
            if i == k:
                f = u
            elif i == k - 1:
                f = 1.0 - u
            else:
                f = 0.0
            rows.append((i, c - disp, f, abs(i - a if a > 0 else i)))
        return {"offset": disp, "a": a, "active": i_act, "k": k, "rows": rows}


# END-OF-FILE rofpalys_CyroKayAI_clock.py

