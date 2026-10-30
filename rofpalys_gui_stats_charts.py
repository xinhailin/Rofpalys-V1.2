#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - statistics window: drawing parts (cards, bars, rings, heat map, pills) on a Tk canvas
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Small drawing functions that know nothing about the player: every one takes the canvas, a palette dict P (the roles of rofpalys_theme.py: BLK SIDE PNL PNL2 CARD
CARD2 GRID TXT DIM GOLD BRN BRN2 OK WARN INFO ACC2 RED PALETTE ...) and the numbers, draws, and returns what it needs (a height, or hit areas for the mouse).
The window draws from the palette of the moment, so a theme switch only needs a redraw. The palette dict also carries P["STYLE"] (rofpalys_theme.STYLES: the shapes of the
look in use), so cards, pills, bars and cells are square in Classic, rounded in Modern and cut-cornered with neon lines in Cyberpunk. No Tk import here: the canvas that is handed in
does all the work."""
import math

HIT = 0   # kinds of hit areas: (x1, y1, x2, y2, kind, payload)


def mix(a, b, t):
    """Colour between two '#rrggbb' colours (t = 0 gives a, t = 1 gives b)."""
    try:
        pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
        pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    except (ValueError, TypeError, IndexError):
        return a
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * t)) for x, y in zip(pa, pb))


_CUR = {"track": "round", "glow": 0, "shape": "round", "r": 10, "chip": "pill"}      # the style of the page being drawn (use(P) sets it)


def use(P):
    """Call once at the start of a page: the functions that get no palette (hbar ...) draw in this style."""
    st = P.get("STYLE") if isinstance(P, dict) else None
    if st:
        _CUR.clear()
        _CUR.update(st)


def kind_shape(P, kind="card"):
    """flat | round | pill | cut for a kind of thing: card / cell (squares and panels), pill (the little tabs), bar (tops of the columns)."""
    st = (P.get("STYLE") if isinstance(P, dict) else None) or _CUR
    if kind == "pill":
        return {"flat": "flat", "pill": "pill", "round": "round", "cut": "cut"}.get(st.get("chip", "pill"), "pill")
    if kind == "bar":
        return "round" if st.get("shape") == "round" else "flat"
    return st.get("shape", "round")


def radius(P, base=12):
    st = (P.get("STYLE") if isinstance(P, dict) else None) or _CUR
    sh = st.get("shape", "round")
    return 0 if sh == "flat" else (min(base, st.get("r", 8) + 4) if sh == "cut" else base)


def rr(cv, x1, y1, x2, y2, r, fill="", outline="", width=1, tags=(), shape="round"):
    """A rectangle with the corners of `shape`: round (one smooth polygon), pill (fully round ends), cut (chamfered top-left and bottom-right) or flat."""
    w, h = x2 - x1, y2 - y1
    if shape == "pill":
        r = h / 2.0
    r = max(0, min(r, w / 2.0, h / 2.0))
    if shape == "flat" or r < 1:
        return cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tags)
    if shape == "cut":
        return cv.create_polygon([x1 + r, y1, x2, y1, x2, y2 - r, x2 - r, y2, x1, y2, x1, y1 + r], fill=fill, outline=outline, width=width, tags=tags)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=width, tags=tags)


def box(cv, x1, y1, x2, y2, P, base=12, kind="card", **kw):
    """rr() in the shape of the look in use."""
    return rr(cv, x1, y1, x2, y2, radius(P, base), shape=kind_shape(P, kind), **kw)


def card(cv, x, y, w, h, P, title="", font=None, hot=False, tags=()):
    """A card: raised surface, hairline border (a neon line when the look glows), small upper-case caption."""
    st = P.get("STYLE") or {}
    glow = st.get("glow", 0)
    line = P["GOLD"] if hot else (mix(P["GRID"], P["BRN2"], 0.55) if glow else P["GRID"])
    box(cv, x, y, x + w, y + h, P, 12, fill=P["CARD"], outline=line, tags=tags)
    if title:
        cv.create_text(x + 16, y + 16, text=title.upper(), fill=P["DIM"], font=font, anchor="w", tags=tags)
        if glow:
            cv.create_line(x + 16, y + 27, x + 40, y + 27, fill=P["BRN2"], width=2, tags=tags)


def pill(cv, x, y, label, active, font, P, h=28, pad=14, tags=()):
    """A pill button (round ends in Modern, cut corners in Cyberpunk, square in Classic); returns its width. The caller keeps the hit area."""
    w = font.measure(label) + pad * 2
    sh = kind_shape(P, "pill")
    r = 7 if sh == "cut" else h / 2.0
    glow = (P.get("STYLE") or {}).get("glow", 0)
    if active:
        rr(cv, x, y, x + w, y + h, r, fill=P["GOLD"], outline="", tags=tags, shape=sh)
        cv.create_text(x + w / 2.0, y + h / 2.0, text=label, fill=P["BLK"], font=font, tags=tags)
    else:
        rr(cv, x, y, x + w, y + h, r, fill=P["CARD2"], outline=mix(P["GRID"], P["BRN2"], 0.6) if glow else P["GRID"], tags=tags, shape=sh)
        cv.create_text(x + w / 2.0, y + h / 2.0, text=label, fill=P["TXT"], font=font, tags=tags)
    return w


def hbar(cv, x, y, w, h, frac, fill, track, tags=()):
    """A horizontal bar: a rounded track (Modern), a square one (Classic) or a row of slanted segments (Cyberpunk)."""
    kind = _CUR.get("track", "round")
    frac = max(0.0, min(1.0, frac))
    if kind == "seg":
        sw, gap = 6, 2
        n = max(3, int(w // (sw + gap)))
        lit = int(round(frac * n)) if frac > 0 else 0
        if frac > 0 and lit == 0:
            lit = 1
        for i in range(n):
            sx = x + i * (sw + gap)
            cv.create_polygon(sx, y + h, sx + 2, y, sx + sw + 2, y, sx + sw, y + h, fill=fill if i < lit else track, outline="", tags=tags)
        return
    if kind == "flat":
        cv.create_rectangle(x, y, x + w, y + h, fill=track, outline="", tags=tags)
        if frac * w >= 1:
            cv.create_rectangle(x, y, x + max(frac * w, 1), y + h, fill=fill, outline="", tags=tags)
        return
    rr(cv, x, y, x + w, y + h, h / 2.0, fill=track, outline="", tags=tags)
    fw = frac * w
    if fw >= 1:
        rr(cv, x, y, x + max(fw, h), y + h, h / 2.0, fill=fill, outline="", tags=tags)


def ring(cv, cx, cy, r, frac, color, track, thick=9, tags=()):
    """A ring gauge (frac 0..1) drawn clockwise from the top."""
    cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=track, width=thick, tags=tags)
    frac = max(0.0, min(1.0, frac))
    if frac >= 0.999:
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=thick, tags=tags)
    elif frac > 0.002:
        cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-360.0 * frac, style="arc", outline=color, width=thick, tags=tags)


def spark(cv, x, y, w, h, vals, color, fill=None, tags=()):
    """A tiny line chart with a soft area under it."""
    if len(vals) < 2:
        return
    hi = max(vals) or 1.0
    step = w / float(len(vals) - 1)
    pts = [(x + i * step, y + h - (v / hi) * (h - 3) - 1) for i, v in enumerate(vals)]
    if fill:
        cv.create_polygon([x, y + h] + [c for p in pts for c in p] + [x + w, y + h], fill=fill, outline="", tags=tags)
    cv.create_line([c for p in pts for c in p], fill=color, width=2, smooth=True, tags=tags)
    cv.create_oval(pts[-1][0] - 3, pts[-1][1] - 3, pts[-1][0] + 3, pts[-1][1] + 3, fill=color, outline="", tags=tags)


def bars(cv, x, y, w, h, series, P, font, label_every=1, hits=None, mark=None, tip=None, unit_fmt=None, back=None, tags=()):
    """Vertical bar chart. series = [(label, value)]; back = optional second list of values drawn wider and dimmer BEHIND the bars (e.g. app-open time);
    mark = index to outline (today / the current hour); tip(i) -> text for the hover area. Returns the maximum value."""
    n = len(series)
    if not n:
        return 0
    hi = max([v for _, v in series] + [b for b in (back or [])] + [1e-9])
    top = 18
    base = y + h - 20
    ph = base - (y + top)
    labs = [unit_fmt(hi * g) for g in (0.5, 1.0)] if unit_fmt else []
    gut = (max(font.measure(l) for l in labs) + 10) if labs else 0          # the room for the value labels on the left, so no bar ever covers one
    x, w = x + gut, w - gut
    gap = max(2.0, w / n * 0.22)
    bw = max(3.0, w / n - gap)
    for gi, g in enumerate((0.5, 1.0)):
        gy = base - ph * g
        cv.create_line(x, gy, x + w, gy, fill=P["GRID"], dash=(2, 4), tags=tags)
        if labs:
            cv.create_text(x - 6, gy, text=labs[gi], fill=P["DIM"], font=font, anchor="e", tags=tags)
    cv.create_line(x, base, x + w, base, fill=P["GRID"], tags=tags)
    for i, (lab, v) in enumerate(series):
        bx = x + i * (w / n) + gap / 2.0
        if back is not None and back[i] > 0:
            bh = max(2.0, back[i] / hi * ph)
            rr(cv, bx - 1, base - bh, bx + bw + 1, base, min(4, bw / 2.0), fill=P["CARD2"], outline="", tags=tags, shape=kind_shape(P, "bar"))
        if v > 0:
            bh = max(2.0, v / hi * ph)
            col = P["GOLD"] if (mark is not None and i == mark) else P["BRN2"]
            x0b, x1b = bx + (bw * 0.12 if back is not None else 0), bx + bw - (bw * 0.12 if back is not None else 0)
            rr(cv, x0b, base - bh, x1b, base, min(4, bw / 2.0), fill=col, outline="", tags=tags, shape=kind_shape(P, "bar"))
            if (P.get("STYLE") or {}).get("glow"):                                       # a bright cap on every column
                cv.create_line(x0b, base - bh, x1b, base - bh, fill=mix(col, P["TXT"], 0.55), width=2, tags=tags)
        if mark is not None and i == mark:
            cv.create_line(bx, base + 3, bx + bw, base + 3, fill=P["GOLD"], width=2, tags=tags)
        if label_every and (i % label_every == 0 or i == n - 1):
            cv.create_text(bx + bw / 2.0, base + 11, text=lab, fill=P["TXT"] if (mark is not None and i == mark) else P["DIM"], font=font, tags=tags)
        if hits is not None and tip is not None:
            hits.append((bx - gap / 2.0, y, bx + bw + gap / 2.0, base + 16, "tip", tip(i)))
    return hi


def heatmap(cv, x, y, w, matrix, counts, P, font, wd_labels, tip=None, hits=None, tags=()):
    """7 x 24 heat map of listening (average per calendar day of that weekday). Returns the height used."""
    lab_w = 36
    cw = (w - lab_w) / 24.0
    ch = min(26.0, max(14.0, cw * 0.9))
    avg = [[(matrix[d][h] / counts[d]) if counts[d] else 0.0 for h in range(24)] for d in range(7)]
    hi = max(max(r) for r in avg) or 1.0
    for h in range(0, 24, 3):
        cv.create_text(x + lab_w + h * cw + cw / 2.0, y + 6, text="%02d" % h, fill=P["DIM"], font=font, tags=tags)
    for d in range(7):
        yy = y + 16 + d * (ch + 3)
        cv.create_text(x, yy + ch / 2.0, text=wd_labels[d], fill=P["DIM"], font=font, anchor="w", tags=tags)
        for h in range(24):
            v = avg[d][h]
            t = (v / hi) ** 0.6 if v > 0 else 0.0
            col = P["CARD2"] if v <= 0 else mix(mix(P["CARD2"], P["BRN"], 0.35), P["GOLD"], t) if t > 0.35 else mix(P["CARD2"], P["BRN"], 0.35 + t)
            xx = x + lab_w + h * cw
            rr(cv, xx + 1, yy, xx + cw - 1, yy + ch, 3, fill=col, outline="", tags=tags, shape=kind_shape(P, "card"))
            if hits is not None and tip is not None:
                hits.append((xx, yy, xx + cw, yy + ch, "tip", tip(d, h, v)))
    return 16 + 7 * (ch + 3)


def donut_legend(cv, x, y, parts, P, font, tags=()):
    """parts = [(label, value 0..1, color)] drawn as one stacked bar with a legend below. Returns the height used."""
    w = parts[0][3] if len(parts[0]) > 3 else 300
    tot = sum(max(0.0, p[1]) for p in parts) or 1.0
    xx = x
    for lab, v, col, *_ in parts:
        sw = w * max(0.0, v) / tot
        if sw >= 1:
            cv.create_rectangle(xx, y, xx + sw, y + 12, fill=col, outline="", tags=tags)
        xx += sw
    return 12


def tooltip(cv, text, x, y, P, font, W):
    """A small floating label near the mouse (tag 'tip'); kept inside the canvas."""
    cv.delete("tip")
    if not text:
        return
    lines = text.split("\n")
    tw = max(font.measure(l) for l in lines) + 20
    th = len(lines) * (font.metrics("linespace") + 2) + 12
    x = min(max(6, x + 14), max(6, W - tw - 6))
    y = max(6, y - th - 10) if y > th + 20 else y + 18
    rr(cv, x, y, x + tw, y + th, radius(P, 6), fill=P["BLK"], outline=P["GOLD"], tags="tip", shape=kind_shape(P, "card"))
    for i, l in enumerate(lines):
        cv.create_text(x + 10, y + 8 + i * (font.metrics("linespace") + 2), text=l, fill=P["TXT"] if i == 0 else P["DIM"], font=font, anchor="nw", tags="tip")
    cv.tag_raise("tip")


def kind_color(k, P):
    return {"play": P["OK"], "resume": P["OK"], "fin": P["DIM"], "pause": P["WARN"], "seek": P["INFO"], "vol": P["ACC2"], "mode": P["ACC2"], "fav": P["RED"], "sleep": P["INFO"],
            "queue": P["INFO"], "fx": P["ACC2"], "lyrics": P["GOLD"], "ui": P["DIM"], "sess": P["BRN2"], "end": P["DIM"], "gap": P["WARN"], "clock": P["WARN"], "recover": P["WARN"]}.get(k, P["DIM"])


FEATURE = {"name": "stats_charts", "title": "Statistics: drawing parts (a helper of the Statistics window - nothing to switch)", "version": "1.1", "order": 90, "enabled": True}


class Mixin:                                         # the window loader may look for these two; this file brings nothing of its own into the window
    pass


def register(app):
    return None


# END-OF-FILE rofpalys_gui_stats_charts.py

