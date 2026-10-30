#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI view: the Spotify-style lyric screen (a Tk canvas that glides, fades, fills the sung words and pulses on the beat)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""LyricView is one Tk Canvas. It does not know the player: the host gives it a function that returns (position, playing, song id) and, if wanted, what to
do on a click on a line (seek) and on the +-0.1 s buttons (sync nudge). All timing maths is in rofpalys_CyroKayAI_clock.py; this file only draws.

  * the sheet glides to the next line with an ease-in-out curve (about 0.45 s) exactly when the line starts; the old line fades out, the new one fades in
  * the line being sung is filled word by word (smooth, character by character); melody rows (🎶 / 🎵) pulse on the beat and show how long until the voice returns
  * 30 frames per second while something moves, 4 while paused, nothing while hidden; the engine is asked for its position at most 20 times per second
  * click a line = jump there; mouse wheel = browse (the sheet returns to the song after 2 s); the buttons at the lower right move the lyrics 0.1 s earlier / later
Needs only tkinter. Tested on a virtual display; the speed on a phone depends on the phone (the frame rate lowers itself when drawing is slow)."""
import time

try:
    import tkinter as tk
    import tkinter.font as tkfont
except ImportError:                                  # no Tk on this machine: the module still imports (the host checks TK)
    tk = tkfont = None

import rofpalys_CyroKayAI_clock as CL

__version__ = "1.0"
TK = tk is not None
DEFAULT_PALETTE = {"bg": "#1a110b", "fg": "#ead9bd", "accent": "#d9a560", "dim": "#8a7660", "hint": "#a96f3a"}


def blend(c1, c2, t):
    """Colour between two '#rrggbb' colours (t = 0 -> c1, 1 -> c2)."""
    t = CL.clamp(t)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def wrap_words(text, measure, width):
    """Split a line into visual lines that fit `width` pixels. Words stay whole; a word wider than the width (or text without spaces: Chinese, Japanese,
    Thai) is cut between characters. -> list of (visual line text, start char index inside the original ' '.join(text.split()))."""
    words = text.split()
    out, cur, cur_start, pos = [], "", 0, 0
    for w in words:
        parts = [w]
        if measure(w) > width:
            parts, piece = [], ""
            for ch in w:
                if piece and measure(piece + ch) > width:
                    parts.append(piece)
                    piece = ch
                else:
                    piece += ch
            if piece:
                parts.append(piece)
        for k, part in enumerate(parts):
            glue = " " if (cur and k == 0) else ""
            if cur and measure(cur + glue + part) > width:
                out.append((cur, cur_start))
                cur, cur_start = part, pos
            else:
                if not cur:
                    cur_start = pos
                cur = cur + glue + part
            pos += len(part)
        pos += 1                                     # the space after the word
    if cur:
        out.append((cur, cur_start))
    return out or [("", 0)]


class LyricView(tk.Canvas if TK else object):
    NOTE_SIZES = 6                                   # font sizes used for the beat pulse of a melody row

    def __init__(self, master, getpos, palette=None, family=None, on_seek=None, on_nudge=None, emoji=True, **kw):
        if not TK:
            raise RuntimeError("tkinter is not available")
        pal = dict(DEFAULT_PALETTE)
        pal.update(palette or {})
        self.pal = pal
        kw.setdefault("bg", pal["bg"])
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)
        self.getpos, self.on_seek, self.on_nudge, self.emoji = getpos, on_seek, on_nudge, emoji
        self.family = family or tkfont.nametofont("TkDefaultFont").actual("family")
        self.clock = CL.PlayClock(mono=time.perf_counter)
        self.tl = self.sheet = None
        self.song = None
        self.message = ""
        self.W = self.H = 0
        self.focus_frac = 0.40
        self._fonts, self._items, self._shown = {}, [], set()
        self._after, self._running, self._last_wall, self._poll_at = None, False, None, 0.0
        self._pos = (0.0, False, None)
        self._frame_ms, self._slow = 33, 0
        self._last_sig = None
        self._hover = False
        self._nudge_total = 0.0
        self.msg_id = self.create_text(0, 0, text="", fill=pal["dim"], anchor="center", justify="center", state="hidden")
        self.hint_ids = []
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._wheel_px(70))
        self.bind("<Button-5>", lambda e: self._wheel_px(-70))
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Motion>", self._on_motion)

    # ------------------------------------------------------------------ the host's calls
    def set_lyrics(self, timeline, song_id=None, nudge=0.0):
        """timeline: rofpalys_CyroKayAI_clock.Timeline (or None: the view shows the message instead). Resets the clock for a new song."""
        self.song = song_id
        self.tl = timeline if timeline is not None and len(timeline) else None
        self.sheet = CL.Sheet(self.tl) if self.tl is not None else None
        self._nudge_total = nudge
        self.clock.lead = nudge
        self._items, self._shown, self._last_sig = [], set(), None
        self.delete("row")
        if self.sheet is not None and self.W > 50:
            self._build()
        self.itemconfigure(self.msg_id, state="hidden" if self.tl is not None else "normal")
        self._place_message()

    def set_message(self, text):
        self.message = text or ""
        self._place_message()

    def set_lead(self, seconds):
        self._nudge_total = seconds
        self.clock.lead = seconds
        self._last_sig = None

    def start(self):
        if not self._running:
            self._running = True
            self._last_wall = None
            self._tick()

    def stop(self):
        self._running = False
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    # ------------------------------------------------------------------ fonts and layout
    def _font(self, key, px, weight="bold"):
        k = (key, px, weight)
        f = self._fonts.get(k)
        if f is None:
            f = self._fonts[k] = tkfont.Font(family=self.family, size=-int(px), weight=weight)
        return f

    def _px(self):
        return int(CL.clamp(self.W / 22.0, 15, 34))

    def _on_configure(self, e):
        if abs(e.width - self.W) > 1 or abs(e.height - self.H) > 1:
            self.W, self.H = e.width, e.height
            self._fonts = {}
            if self.sheet is not None and self.W > 50:
                self._build()
            self._place_message()
            self._last_sig = None

    def _place_message(self):
        self.coords(self.msg_id, self.W / 2, self.H / 2)
        self.itemconfigure(self.msg_id, text=self.message, font=self._font("msg", max(12, self._px() * 0.7), "normal"), width=max(60, self.W * 0.8),
                           state="normal" if (self.tl is None and self.message) else "hidden")

    def _build(self):
        """Wrap every row for the current width, measure it and create its canvas items (they are only moved and recoloured per frame)."""
        self.delete("row")
        self._items, self._shown = [], set()
        px = self._px()
        f = self._font("line", px)
        fn = self._font("note", px * 1.5, "normal")
        lh = f.metrics("linespace")
        text_w = max(60.0, self.W * 0.84)
        heights = []
        for r in self.tl.rows:
            if r.kind == "note":
                heights.append(self._font("note", px * 1.5, "normal").metrics("linespace") * 1.25)
                sym = r.text
                if not self.emoji:
                    sym = {"🎶": "♫", "🎵": "♪"}.get(sym, sym)
                ids = [self.create_text(0, 0, text=sym, anchor="center", tags="row", state="hidden")]
                self._items.append({"kind": "note", "base": ids, "fill": [], "vis": [], "h": heights[-1], "sym": sym})
                self.itemconfigure(ids[0], fill=self.pal["dim"])
                continue
            vis = wrap_words(r.text, f.measure, text_w)
            h = len(vis) * lh * 1.08 + lh * 0.62
            heights.append(h)
            base, fill, widths = [], [], []
            for text, start in vis:
                base.append(self.create_text(0, 0, text=text, anchor="nw", font=f, fill=self.pal["dim"], tags="row", state="hidden"))
                fill.append(self.create_text(0, 0, text="", anchor="nw", font=f, fill=self.pal["accent"], tags="row", state="hidden"))
                widths.append(f.measure(text))
            self._items.append({"kind": "line", "base": base, "fill": fill, "vis": vis, "w": widths, "h": h, "lh": lh * 1.08})
        self.sheet.gap = lh * 0.45
        self.sheet.layout(heights)
        self.progress_id = self.create_line(0, 0, 0, 0, fill=self.pal["accent"], width=2, tags="row", state="hidden")
        self.progress_bg = self.create_line(0, 0, 0, 0, fill=blend(self.pal["bg"], self.pal["dim"], 0.45), width=2, tags="row", state="hidden")
        self._make_hints()

    def _make_hints(self):
        for i in self.hint_ids:
            self.delete(i)
        f = self._font("hint", max(11, self._px() * 0.6), "normal")
        col = self.pal["hint"]
        y = self.H - 14
        self.hint_ids = [self.create_text(self.W - 14, y, text="+0.1 s ▸", anchor="se", font=f, fill=col, tags="hint", state="hidden"),
                         self.create_text(self.W - 14 - f.measure("+0.1 s ▸") - 22, y, text="◂ −0.1 s", anchor="se", font=f, fill=col, tags="hint", state="hidden"),
                         self.create_text(14, y, text="", anchor="sw", font=f, fill=self.pal["dim"], tags="hint", state="hidden")]
        self._refresh_hints()

    def _refresh_hints(self):
        if not self.hint_ids:
            return
        st = "normal" if self._hover and self.tl is not None else "hidden"
        for i in self.hint_ids:
            self.itemconfigure(i, state=st)
        self.itemconfigure(self.hint_ids[2], text=("sync %+.1f s" % self._nudge_total) if abs(self._nudge_total) >= 0.05 else "")
        self.tag_raise("hint")

    # ------------------------------------------------------------------ the frame loop
    def _tick(self):
        if not self._running:
            return
        wall = time.perf_counter()
        t_start = wall
        try:
            if wall >= self._poll_at:                                   # ask the player at most 20 times per second
                self._pos = self.getpos()
                self._poll_at = wall + 0.05
                pos, playing, track = self._pos
                self.clock.update(pos, playing, now=wall, track=track)
            dt = (wall - self._last_wall) if self._last_wall is not None else 0.033
            self._last_wall = wall
            visible = self.winfo_viewable() and self.W > 50
            moving = False
            if visible and self.sheet is not None and self._items:
                if self.clock.take_jump():
                    self.sheet.jump(self.clock.time(wall), wall)
                t = self.clock.time(wall)
                f = self.sheet.frame(t, wall, min(dt, 0.1))
                sig = (round(f["offset"], 1), f["active"], int(t * 30) if (self.clock.playing and self._wants_motion(f, t)) else 0, self._hover)
                if sig != self._last_sig:
                    self._last_sig = sig
                    self._draw(f, t)
                moving = self.clock.playing or abs(self.sheet.res) > 0.01
            else:
                self.clock.take_jump()
        except tk.TclError:
            self._running = False
            return
        except Exception as e:                                           # drawing must never break the player
            self._slow = 0
            self._last_err = e
            moving = False
        took = (time.perf_counter() - t_start) * 1000.0
        if took > 22:                                                    # a slow phone: draw less often instead of falling behind
            self._frame_ms = min(80, self._frame_ms + 8)
        elif took < 10 and self._frame_ms > 33:
            self._frame_ms -= 4
        period = self._frame_ms if moving else 250 if not self.winfo_viewable() else 120
        self._after = self.after(int(period), self._tick)

    def _wants_motion(self, f, t):
        """True when something on screen changes with time even though the sheet stands still (the sung fill, the beat pulse)."""
        if not self.tl:
            return False
        i = self.tl.active(t)
        return 0 <= i < len(self.tl.rows)

    def _draw(self, f, t):
        P = self.pal
        H, W = self.H, self.W
        fy = H * self.focus_frac
        px = self._px()
        shown = set()
        act = f["active"]
        for (i, yc, focus, dist) in f["rows"]:
            it = self._items[i]
            top = fy + yc - it["h"] / 2.0
            if top > H + 20 or top + it["h"] < -20:
                continue
            shown.add(i)
            alpha = CL.clamp(0.64 - 0.17 * dist, 0.13, 0.64)
            base_col = blend(P["bg"], P["fg"], alpha + 0.2 * focus * (1.0 - alpha))
            row = self.tl.rows[i]
            if it["kind"] == "note":
                pulse = self.tl.pulse(t) if (focus > 0.5) else 0.0
                col = blend(P["bg"], P["accent"], alpha + 0.3 * focus + 0.15 * pulse)
                size = px * (1.4 + 0.22 * pulse * focus)
                bid = it["base"][0]
                self.coords(bid, W / 2, top + it["h"] / 2)
                self.itemconfigure(bid, fill=col, font=self._font("note", int(size), "normal"), state="normal")
                if focus > 0.5 and row.t0 < t < row.v1:                      # time until the voice returns
                    u = self.tl.row_progress(i, t)
                    y = top + it["h"] - 2
                    x0, x1 = W * 0.36, W * 0.64
                    self.coords(self.progress_bg, x0, y, x1, y)
                    self.coords(self.progress_id, x0, y, x0 + (x1 - x0) * u, y)
                    self.itemconfigure(self.progress_bg, state="normal")
                    self.itemconfigure(self.progress_id, state="normal")
                continue
            sung = row.sung_chars(t) if (focus > 0.02 or i == act) else 0.0
            y = top + it["lh"] * 0.31
            fill_col = blend(base_col, P["accent"], focus)
            for k, (text, start) in enumerate(it["vis"]):
                x0 = (W - it["w"][k]) / 2.0
                bid, fid = it["base"][k], it["fill"][k]
                self.coords(bid, x0, y)
                self.itemconfigure(bid, fill=base_col, state="normal")
                n = int(sung - start)
                if focus > 0.02 and n > 0:
                    self.coords(fid, x0, y)
                    self.itemconfigure(fid, text=text[:min(len(text), n)], fill=fill_col, state="normal")
                else:
                    self.itemconfigure(fid, state="hidden")
                y += it["lh"]
        for i in self._shown - shown:
            for iid in self._items[i]["base"] + self._items[i]["fill"]:
                self.itemconfigure(iid, state="hidden")
        if not any(self._items[i]["kind"] == "note" and self.tl.rows[i].t0 < t < self.tl.rows[i].v1 for i in shown):
            self.itemconfigure(self.progress_bg, state="hidden")
            self.itemconfigure(self.progress_id, state="hidden")
        self._shown = shown
        self.tag_raise("hint")

    # ------------------------------------------------------------------ the mouse
    def _row_at(self, y):
        """The row under the mouse (a click in the gap between two rows takes the nearer one), or -1 when the y is outside the sheet."""
        if self.sheet is None or not self._items:
            return -1
        best, bd = -1, 1e9
        for (i, yc, focus, dist) in self.sheet.frame(self.clock.time(), time.perf_counter(), 0.0)["rows"]:
            d = abs(self.H * self.focus_frac + yc - y)
            if d < bd and d <= self._items[i]["h"] / 2.0 + self.sheet.gap / 2.0 + 2:
                best, bd = i, d
        return best

    def _on_click(self, e):
        if self.tl is None:
            return
        for k, iid in enumerate(self.hint_ids[:2]):
            if self._hover:
                x0, y0, x1, y1 = self.bbox(iid) or (0, 0, 0, 0)
                if x0 - 6 <= e.x <= x1 + 6 and y0 - 6 <= e.y <= y1 + 6:
                    d = 0.1 if k == 0 else -0.1
                    self._nudge(d)
                    return
        i = self._row_at(e.y)
        if i >= 0 and self.on_seek is not None:
            try:
                self.on_seek(self.tl.rows[i].t0 + 0.02 - self.clock.lead)
            except Exception:
                pass

    def _nudge(self, d):
        """d > 0: show the lyrics LATER (the song time the lyrics see is d seconds earlier). The host stores it for the song."""
        self._nudge_total = round(self._nudge_total - d, 2)
        self.clock.lead = self._nudge_total
        self._last_sig = None
        self._refresh_hints()
        if self.on_nudge is not None:
            try:
                self.on_nudge(d)
            except Exception:
                pass

    def _on_wheel(self, e):
        self._wheel_px(70 if e.delta > 0 else -70)

    def _wheel_px(self, dy):
        if self.sheet is not None:
            self.sheet.wheel(dy, time.perf_counter())
            self._last_sig = None

    def _on_motion(self, e):
        self.configure(cursor="hand2" if self._row_at(e.y) >= 0 else "")

    def _set_hover(self, on):
        self._hover = on
        self._refresh_hints()
        self._last_sig = None


# END-OF-FILE rofpalys_CyroKayAI_view.py

