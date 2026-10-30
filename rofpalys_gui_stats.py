#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: Statistics (live listening time, rankings, every activity, records, data quality)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""A statistics PAGE in the look of the big music apps: cards, big numbers, bar charts, rings, a weekday x hour heat map, rankings and a live feed of everything
you do in Rofpalys. The numbers come from rofpalys_analytics.py (the recorder + the tamper-evident log); this file only draws. It follows the theme
(Classic / Modern / Cyberpunk): the shapes, fonts and colours of the page are those of the look in use.

  open        the menu item "Statistik" in the sidebar (right under Visual), the chart button in the toolbar, the key F7, or the old menu entry (open_stats / show_stats)
  tabs        Overview | Today (live) | Songs | Artists | Days | Time | Activity | Records
  real time   the numbers on Overview / Today / Activity tick every second while the page is open
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
import threading
import time

from rofpalys_gui_base import *   # noqa: F401,F403

try:
    import rofpalys_analytics as AN
    import rofpalys_analytics_calc as C
    import rofpalys_analytics_text as X
    import rofpalys_gui_stats_charts as CH
except Exception:                                    # the window then says what is missing instead of failing at start
    AN = C = X = CH = None
try:
    import rofpalys_theme as TH2
except Exception:
    TH2 = None

FEATURE = {"name": "stats", "title": "Statistics: live listening time, rankings, activity, records", "version": "1.1", "order": 14, "enabled": True}
TABS = ("overview", "live", "songs", "artists", "days", "time", "activity", "records")
PERIODS = (("today", "today"), ("7d", "w7"), ("30d", "d30"), ("year", "year"), ("all", "all"))
RULES = (("lastfm", "r_lastfm"), ("spotify", "r_spotify"), ("starts", "r_starts"), ("finished", "r_finished"))
FILTERS = (("all", None, "filter_all"), ("play", ("play", "fin"), "k_play"), ("pause", ("pause", "resume"), "k_pause"), ("seek", ("seek",), "k_seek"), ("vol", ("vol",), "k_vol"),
           ("mode", ("mode",), "k_mode"), ("fav", ("fav",), "k_fav"), ("sleep", ("sleep",), "k_sleep"), ("queue", ("queue",), "k_queue"), ("fx", ("fx",), "k_fx"),
           ("lyrics", ("lyrics",), "k_lyrics"), ("ui", ("ui",), "k_ui"), ("sess", ("sess", "end", "gap", "clock", "recover"), "k_sess"))
LIVE_TABS = ("overview", "live", "activity")
M, G = 18, 12                                        # margin and gap of the layout


def palette():
    if TH2 is not None:
        try:
            return TH2.palette()
        except Exception:
            pass
    g = globals()
    return {k: g[k] for k in ("BLK", "SIDE", "PNL", "PNL2", "HOVER", "ROW_HOVER", "BRN", "BRN2", "GOLD", "TXT", "DIM", "RED", "OK", "WARN", "INFO", "ACC2", "GRID", "CARD", "CARD2")} | {"PALETTE": list(PALETTE)}


def fit(font, s, maxw):
    s = str(s)
    if maxw <= 10 or font.measure(s) <= maxw:
        return s
    while s and font.measure(s + "…") > maxw:
        s = s[:-1]
    return s + "…"


class Ctx:
    """Everything a page needs to draw: the canvas, its width, the palette of this moment, the fonts, the language, the numbers, and the lists that collect
    what can be clicked and what shows a tooltip."""

    def __init__(self, app, cv, W, P, F, lg, v):
        self.app, self.cv, self.W, self.P, self.F, self.lg, self.v = app, cv, W, P, F, lg, v
        self.clicks, self.hits = [], []
        CH.use(P)                                           # the shapes of the look in use (square / rounded / cut)

    def t(self, k):
        return X.T(self.lg, k)

    def text(self, x, y, s, fill=None, font=None, anchor="w", **kw):
        return self.cv.create_text(x, y, text=s, fill=fill or self.P["TXT"], font=font or self.F["md"], anchor=anchor, **kw)

    def card(self, x, y, w, h, title="", hot=False):
        CH.card(self.cv, x, y, w, h, self.P, title, self.F["xs"], hot)

    def click(self, x1, y1, x2, y2, fn):
        self.clicks.append((x1, y1, x2, y2, fn))

    def tip(self, x1, y1, x2, y2, text):
        self.hits.append((x1, y1, x2, y2, "tip", text))

    def cols(self, want):
        n = want if self.W >= 940 else (min(want, 2) if self.W >= 520 else 1)
        return n, (self.W - 2 * M - (n - 1) * G) / n

    def pills(self, x, y, items, active, pick, font=None, x0=None, x1=None):
        """A row of pills (items = [(key, label)]) that wraps inside x0..x1 (default: the page margins); returns the y below it."""
        font = font or self.F["sm"]
        x0 = M if x0 is None else x0
        x1 = (self.W - M) if x1 is None else x1
        for key, label in items:
            w = font.measure(label) + 28
            if x + w > x1 and x > x0:
                x, y = x0, y + 34
            CH.pill(self.cv, x, y, label, key == active, font, self.P)
            self.click(x, y, x + w, y + 28, (lambda k=key: pick(k)))
            x += w + 8
        return y + 28

    def pill_rows(self, x, items, font=None, x0=None, x1=None):
        """How many rows pills() will need (the same wrapping, nothing drawn) - for cards that must be tall enough beforehand."""
        font = font or self.F["sm"]
        x0 = M if x0 is None else x0
        x1 = (self.W - M) if x1 is None else x1
        rows = 1
        for _key, label in items:
            w = font.measure(label) + 28
            if x + w > x1 and x > x0:
                x, rows = x0, rows + 1
            x += w + 8
        return rows

    def dur(self, s, secs=False):
        return X.fmt_dur(s, self.lg, secs)


# ---------------------------------------------------------------- pages (each returns the height it used)
def pg_overview(c):
    v, P, F, t = c.v, c.P, c.F, c.t
    app = c.app
    ov = v.overview()
    y = c.pills(M, 14, [(k, t(lab)) for k, lab in PERIODS], app.st_period, app.st_set_period) + 14
    today, yest = ov["today"], ov["yesterday"]
    ser = v.series(7)
    n, cw = c.cols(4)
    delta = X.delta_text(today["listen"], yest["listen"], c.lg)
    heroes = [
        (t("listening") + " · " + t("today"), c.dur(today["listen"]), ((delta + " " + t("vs_yday")) if delta else ""), P["OK"] if not delta.startswith("−") else P["WARN"], [r["listen"] for r in ser], P["GOLD"]),
        (t("appopen") + " · " + t("today"), c.dur(today["open"]), "%s: %d" % (t("sessions_n"), today["sessions"]), P["DIM"], None, P["TXT"]),
        (t("plays") + " · " + t("today"), X.fmt_num(today["lastfm"], c.lg), t("of_started") % today["starts"], P["DIM"], None, P["TXT"]),
        (t("streak"), X.n_days(ov["streak"]["current"], c.lg), "%s: %s" % (t("longest_streak"), X.n_days(ov["streak"]["longest"], c.lg)), P["DIM"], None, P["TXT"]),
    ]
    for i, (cap, val, sub, subcol, spark, valcol) in enumerate(heroes):
        x, yy = M + (i % n) * (cw + G), y + (i // n) * (112 + G)
        c.card(x, yy, cw, 112, cap)
        c.text(x + 16, yy + 56, val, fill=valcol, font=F["xl"])
        c.text(x + 16, yy + 90, CH_fit(F["sm"], sub, cw - 32), fill=subcol, font=F["sm"])
        if spark:
            sw = cw - 32 - F["xl"].measure(val) - 18                      # what is left to the right of the big number
            if sw >= 56:
                sw = min(sw, 110)
                CH.spark(c.cv, x + cw - 16 - sw, yy + 40, sw, 36, spark, P["GOLD"], CH.mix(P["CARD"], P["GOLD"], 0.18))
    y += ((len(heroes) + n - 1) // n) * (112 + G)
    # day by day + totals
    two = c.W >= 760
    cwid = (c.W - 2 * M - G) * 0.64 if two else c.W - 2 * M
    ser14 = v.series(14)
    c.card(M, y, cwid, 232, t("by_day") + " · 14 " + t("days"))
    hits0 = len(c.hits)
    CH.bars(c.cv, M + 16, y + 30, cwid - 32, 196, [(str(r["key"][8:]), r["listen"]) for r in ser14], P, F["xs"], 1 if cwid > 520 else 2, c.hits, len(ser14) - 1,
            lambda i: "%s\n%s %s\n%s %s\n%s %d" % (X.fmt_date(ser14[i]["key"], c.lg), t("listening"), c.dur(ser14[i]["listen"]), t("appopen"), c.dur(ser14[i]["open"]), t("plays"), ser14[i]["plays"]),
            lambda s: X.fmt_axis(s, c.lg), [r["open"] for r in ser14])
    lx = M + cwid - 16
    c.cv.create_rectangle(lx - 150, y + 12, lx - 142, y + 20, fill=P["BRN2"], outline="")
    c.text(lx - 138, y + 16, t("listening"), fill=P["DIM"], font=F["xs"])
    c.cv.create_rectangle(lx - 60, y + 12, lx - 52, y + 20, fill=P["CARD2"], outline="")
    c.text(lx - 48, y + 16, t("open_"), fill=P["DIM"], font=F["xs"])
    if two:
        tx, tw = M + cwid + G, c.W - 2 * M - cwid - G
        c.card(tx, y, tw, 232, t("total"))
        c.text(tx + tw - 16 - 70, y + 16, t("listening"), fill=P["DIM"], font=F["xs"], anchor="e")
        c.text(tx + tw - 16, y + 16, t("plays"), fill=P["DIM"], font=F["xs"], anchor="e")
        for i, (key, lab) in enumerate((("today", "today"), ("7d", "w7"), ("30d", "d30"), ("year", "year"), ("all", "all"))):
            yy = y + 46 + i * 34
            c.cv.create_line(tx + 16, yy - 14, tx + tw - 16, yy - 14, fill=P["GRID"])
            c.text(tx + 16, yy, t(lab), fill=P["TXT"], font=F["sm"])
            c.text(tx + tw - 16 - 70, yy, c.dur(ov[key]["listen"]), fill=P["GOLD"], font=F["sm"], anchor="e")
            c.text(tx + tw - 16, yy, X.fmt_num(ov[key]["lastfm"], c.lg), fill=P["TXT"], font=F["sm"], anchor="e")
        y += 232 + G
    else:
        y += 232 + G
    # top lists
    n2, w2 = c.cols(2)
    ts = v.rank(app.st_period, "plays", "song", app.st_rule, 5)
    ta = v.rank(app.st_period, "plays", "artist", app.st_rule, 5)
    h1 = toplist(c, M, y, w2, ts, t("top_songs"), "song")
    h2 = toplist(c, M + (w2 + G if n2 > 1 else 0), y + (0 if n2 > 1 else h1 + G), w2, ta, t("top_artists"), "artist")
    y += (max(h1, h2) if n2 > 1 else h1 + G + h2) + G
    # ratios + time of day
    allt = ov["all"]
    c.card(M, y, w2, 170, t("completion") + " · " + t("skip_rate") + " · " + t("repeat"))
    for i, (lab, val, col) in enumerate(((t("completion"), ov["completion"], P["OK"]), (t("skip_rate"), ov["skip_rate"], P["WARN"]), (t("repeat"), ov["repeat_ratio"], P["INFO"]))):
        cx = M + w2 * (i + 0.5) / 3.0
        CH.ring(c.cv, cx, y + 80, 36, val, col, P["CARD2"], 9)
        c.text(cx, y + 80, X.fmt_pct(val), fill=P["TXT"], font=F["lg"], anchor="center")
        c.text(cx, y + 138, lab, fill=P["DIM"], font=F["xs"], anchor="center")
    x2 = M + (w2 + G if n2 > 1 else 0)
    y2 = y + (0 if n2 > 1 else 170 + G)
    c.card(x2, y2, w2, 170, t("by_time"))
    sh = ov["shares"]
    parts = [(t("night"), sh["night"], P["ACC2"]), (t("morning"), sh["morning"], P["INFO"]), (t("afternoon"), sh["afternoon"], P["WARN"]), (t("evening"), sh["evening"], P["OK"])]   # four colours that stay apart in every theme
    tot = sum(p[1] for p in parts) or 1.0
    xx = x2 + 16
    for lab, val, col in parts:
        wd = (w2 - 32) * val / tot
        if wd >= 1:
            c.cv.create_rectangle(xx, y2 + 40, xx + wd, y2 + 56, fill=col, outline="")
        xx += wd
    for i, (lab, val, col) in enumerate(parts):
        lx0 = x2 + 16 + (i % 2) * ((w2 - 32) / 2)
        ly = y2 + 78 + (i // 2) * 22
        c.cv.create_oval(lx0, ly - 5, lx0 + 10, ly + 5, fill=col, outline="")
        c.text(lx0 + 16, ly, "%s  %s" % (lab, X.fmt_pct(val)), fill=P["TXT"], font=F["sm"])
    if ov["peak_hour"] is not None:
        c.text(x2 + 16, y2 + 136, "%s %02d:00   ·   %s %s" % (t("peak_hour"), ov["peak_hour"], t("peak_day"), X.T(c.lg, "weekdays_long")[ov["peak_weekday"]]), fill=P["DIM"], font=F["sm"])
    y += (170 if n2 > 1 else 170 + G + 170) + 24
    if not allt["starts"]:
        c.text(c.W / 2.0, y + 10, t("none"), fill=P["DIM"], font=F["md"], anchor="center")
        y += 40
    return y


def CH_fit(font, s, w):
    return fit(font, s, w)


def toplist(c, x, y, w, rows, title, level):
    P, F, t = c.P, c.F, c.t
    h = 40 + max(1, len(rows)) * 46
    c.card(x, y, w, h, title)
    if not rows:
        c.text(x + 16, y + 56, t("none"), fill=P["DIM"], font=F["sm"])
        return h
    mx = max(r["plays"] for r in rows) or 1
    for i, r in enumerate(rows):
        yy = y + 40 + i * 46
        c.text(x + 16, yy + 12, str(i + 1), fill=P["GOLD"] if i == 0 else P["DIM"], font=F["lg"])
        nm = r["title"] if level == "song" else r["name"]
        c.text(x + 44, yy + 8, fit(F["md"], nm, w - 150), fill=P["TXT"], font=F["md"])
        sub = r["artist"] if level == "song" else X.n_songs(r["songs"], c.lg)
        c.text(x + 44, yy + 25, fit(F["xs"], sub, w - 150), fill=P["DIM"], font=F["xs"])
        CH.hbar(c.cv, x + 44, yy + 36, w - 150, 4, r["plays"] / mx, P["GOLD"] if i == 0 else P["BRN2"], P["CARD2"])
        c.text(x + w - 16, yy + 8, X.fmt_num(r["plays"], c.lg), fill=P["TXT"], font=F["lg"], anchor="e")
        c.text(x + w - 16, yy + 27, c.dur(r["time"]), fill=P["DIM"], font=F["xs"], anchor="e")
        if level == "song":
            c.click(x, yy, x + w, yy + 44, (lambda p=r["name"]: c.app.st_select_song(p)))
    return h


def pg_live(c):
    v, P, F, t = c.v, c.P, c.F, c.t
    n = v.now()
    today = v.totals("today")
    y = 14
    two = c.W >= 700
    bw = (c.W - 2 * M - G) / 2.0 if two else c.W - 2 * M
    for i, (cap, val, sub, col) in enumerate(((t("listening") + " · " + t("today_so_far"), today["listen"], "%s: %d / %d" % (t("plays"), today["lastfm"], today["starts"]), P["GOLD"]),
                                              (t("appopen") + " · " + t("today_so_far"), today["open"], "%s: %d" % (t("sessions_n"), today["sessions"]), P["TXT"]))):
        x = M + (i * (bw + G) if two else 0)
        yy = y + (0 if two else i * (128 + G))
        c.card(x, yy, bw, 128, cap, hot=(i == 0 and n["playing"]))
        c.text(x + 16, yy + 66, X.fmt_clock(val), fill=col, font=F["mono"])
        c.text(x + 16, yy + 104, sub, fill=P["DIM"], font=F["sm"])
    y += (128 + G) if two else 2 * (128 + G)
    # now playing
    c.card(M, y, bw if two else c.W - 2 * M, 150, t("now_playing"), hot=n["playing"])
    x = M
    w = bw if two else c.W - 2 * M
    if n["title"]:
        c.text(x + 16, y + 48, fit(F["lg"], n["title"], w - 32), fill=P["TXT"], font=F["lg"])
        c.text(x + 16, y + 72, fit(F["sm"], n["artist"] or "-", w - 32), fill=P["DIM"], font=F["sm"])
        frac = (n["pos"] / n["dur"]) if n["dur"] else 0
        CH.hbar(c.cv, x + 16, y + 92, w - 32, 6, frac, P["GOLD"], P["CARD2"])
        c.text(x + 16, y + 112, X.fmt_mmss(n["pos"]), fill=P["DIM"], font=F["xs"])
        c.text(x + w - 16, y + 112, X.fmt_mmss(n["dur"]) if n["dur"] else "?", fill=P["DIM"], font=F["xs"], anchor="e")
        lis = n["listened_play"]
        lf, sp, _d, _s = C.classify(lis, n["dur"], "inflight", 0)
        if lf:
            st, col = t("counted"), P["OK"]
        elif sp:
            st, col = t("heard_only"), P["INFO"]
        else:
            st, col = "%s %s" % (t("counts_in"), X.fmt_mmss(30 - lis)), P["DIM"]
        c.text(x + 16, y + 134, "%s %s  ·  %s" % (t("this_song"), X.fmt_mmss(lis), st), fill=col, font=F["xs"])
    else:
        c.text(x + 16, y + 70, t("nothing"), fill=P["DIM"], font=F["md"])
    x2 = M + (bw + G if two else 0)
    y2 = y + (0 if two else 150 + G)
    c.card(x2, y2, bw if two else c.W - 2 * M, 150, t("session"))
    rows = ((t("up"), X.fmt_clock(n["session_up"])), (t("heard"), X.fmt_clock(n["session_listen"])), (t("starts"), str(n["session_plays"])), (t("surfaces"), n["surface"] or "-"))
    for i, (k, val) in enumerate(rows):
        c.text(x2 + 16, y2 + 48 + i * 26, k, fill=P["DIM"], font=F["sm"])
        c.text(x2 + (bw if two else c.W - 2 * M) - 16, y2 + 48 + i * 26, val, fill=P["TXT"], font=F["sm"], anchor="e")
    y += (150 + G) if two else 2 * (150 + G)
    # hours of today + today's plays
    hrs = today["hours"]
    nowh = C.hour_of(v.now_ms(), v.z())
    c.card(M, y, c.W - 2 * M, 190, t("per_hour") + " · " + t("today"))
    CH.bars(c.cv, M + 16, y + 28, c.W - 2 * M - 32, 156, [("%02d" % h, hrs[h]) for h in range(24)], P, F["xs"], 1 if c.W > 640 else 3, c.hits, nowh,
            lambda i: "%02d:00\n%s" % (i, c.dur(hrs[i])), lambda s: X.fmt_axis(s, c.lg))
    y += 190 + G
    plays = list(reversed(v.today_plays()))[:12]
    h = 44 + max(1, len(plays)) * 30
    c.card(M, y, c.W - 2 * M, h, t("plays") + " · " + t("today"))
    if not plays:
        c.text(M + 16, y + 56, t("none"), fill=P["DIM"], font=F["sm"])
    for i, p in enumerate(plays):
        yy = y + 52 + i * 30
        col = (P["OK"], P["INFO"], P["DIM"])[2 - p[5]] if p[5] in (0, 1, 2) else P["DIM"]
        c.cv.create_oval(M + 16, yy - 5, M + 26, yy + 5, fill=col, outline="")
        c.text(M + 36, yy, C.clock(p[0], p[1])[:5], fill=P["DIM"], font=F["sm"])
        ti, ar = v.title(p[2])
        c.text(M + 90, yy, fit(F["sm"], ti + (" - " + ar if ar else ""), c.W - 2 * M - 250), fill=P["TXT"], font=F["sm"])
        c.text(c.W - M - 16, yy, "%s  ·  %s" % (X.fmt_mmss(p[3]), t("w_" + p[4]) if ("w_" + p[4]) in X.TX["en"] else p[4]), fill=P["DIM"], font=F["xs"], anchor="e")
    y += h + 24
    return y


def pg_rank(c, level):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    y = c.pills(M, 14, [(k, t(lab)) for k, lab in PERIODS], app.st_period, app.st_set_period) + 10
    y = c.pills(M, y + 8, [("plays", t("by_plays")), ("time", t("by_time_"))], app.st_by, app.st_set_by) + 10
    if app.st_by == "plays":
        y = c.pills(M, y + 8, [(k, t(lab)) for k, lab in RULES], app.st_rule, app.st_set_rule, F["xs"]) + 10
    if level != "song":
        y = c.pills(M, y + 8, [("artist", t("artists")), ("folder", t("folders"))], app.st_level, app.st_set_level) + 10
    lv = "song" if level == "song" else app.st_level
    y += 10
    rows = v.rank(app.st_period, app.st_by, lv, app.st_rule, 60)
    if lv == "song" and app.st_sel:
        y = song_detail(c, y) + G
    wide = c.W >= 700
    ncol = {"last": 62 if wide else 0, "skips": 62 if wide else 0, "done": 62 if wide else 0, "time": 84, "plays": 64}
    right = M + 16
    xs = {}
    for k in ("last", "skips", "done", "time", "plays"):
        if ncol[k]:
            xs[k] = c.W - right
            right += ncol[k]
    barw = 110 if c.W >= 620 else 0
    barx = c.W - right - (barw + 8 if barw else 0)
    h = 70 + len(rows) * 38
    c.card(M, y, c.W - 2 * M, h, "")
    hy = y + 22
    c.text(M + 16, hy, t("rank"), fill=P["DIM"], font=F["xs"])
    c.text(M + 50, hy, (t("title") if lv == "song" else (t("artist") if lv == "artist" else t("folders"))).upper(), fill=P["DIM"], font=F["xs"])
    for k, lab in (("plays", "plays"), ("time", "time"), ("done", "done"), ("skips", "skips"), ("last", "last")):
        if k in xs:
            c.text(xs[k], hy, t(lab).upper(), fill=P["DIM"], font=F["xs"], anchor="e")
    c.cv.create_line(M + 12, y + 36, c.W - M - 12, y + 36, fill=P["GRID"])
    if not rows:
        c.text(M + 16, y + 64, t("none"), fill=P["DIM"], font=F["md"])
        return y + h + 24
    mx = max((r["plays"] if app.st_by == "plays" else r["time"]) for r in rows) or 1
    for i, r in enumerate(rows):
        yy = y + 44 + i * 38
        sel = lv == "song" and r["name"] == app.st_sel
        if sel:
            CH.box(c.cv, M + 8, yy - 3, c.W - M - 8, yy + 33, P, 8, fill=P["CARD2"], outline=P["GOLD"])
        c.text(M + 16, yy + 15, str(i + 1), fill=P["GOLD"] if i < 3 else P["DIM"], font=F["lg"] if i < 3 else F["md"])
        nm = r["title"] if lv == "song" else r["name"]
        sub = r["artist"] if lv == "song" else X.n_songs(r["songs"], c.lg)
        tw = (barx if barw else c.W - right) - (M + 50) - 14
        c.text(M + 50, yy + 9, fit(F["md"], nm, tw), fill=P["TXT"], font=F["md"])
        c.text(M + 50, yy + 25, fit(F["xs"], sub, tw), fill=P["DIM"], font=F["xs"])
        if barw:
            CH.hbar(c.cv, barx, yy + 13, barw, 7, (r["plays"] if app.st_by == "plays" else r["time"]) / mx, P["GOLD"] if i == 0 else P["BRN2"], P["CARD2"])
        if "plays" in xs:
            c.text(xs["plays"], yy + 15, X.fmt_num(r["plays"], c.lg), fill=P["TXT"], font=F["md"], anchor="e")
        c.text(xs["time"], yy + 15, c.dur(r["time"]), fill=P["TXT"] if app.st_by == "time" else P["DIM"], font=F["sm"], anchor="e")
        if "done" in xs:
            c.text(xs["done"], yy + 15, X.fmt_pct(r["completion"]), fill=P["DIM"], font=F["sm"], anchor="e")
        if "skips" in xs:
            c.text(xs["skips"], yy + 15, X.fmt_pct(r["skip_rate"]), fill=P["WARN"] if r["skip_rate"] > 0.3 else P["DIM"], font=F["sm"], anchor="e")
        if "last" in xs:
            c.text(xs["last"], yy + 15, C.day_key(C.day_index(r["last"], v.z()))[5:] if r["last"] else "", fill=P["DIM"], font=F["sm"], anchor="e")
        if lv == "song":
            c.click(M + 8, yy - 3, c.W - M - 8, yy + 33, (lambda p=r["name"]: app.st_select_song(p)))
    return y + h + 24


def song_detail(c, y):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    d = v.song(app.st_sel)
    r, meta = d["row"], d["meta"]
    h = 132
    c.card(M, y, c.W - 2 * M, h, t("detail"), hot=True)
    ti, ar = v.title(app.st_sel)
    c.text(M + 16, y + 46, fit(F["lg"], ti, c.W - 2 * M - 220), fill=P["TXT"], font=F["lg"])
    c.text(M + 16, y + 68, fit(F["sm"], ar or "-", c.W - 2 * M - 220), fill=P["DIM"], font=F["sm"])
    if r:
        facts = ((t("rank_of"), "#%d %s %d" % (d["rank"], t("of"), d["of"])), (t("plays"), str(r["plays"])), (t("time"), c.dur(r["time"])), (t("completion"), X.fmt_pct(r["completion"])), (t("skip_rate"), X.fmt_pct(r["skip_rate"])))
        for i, (k, val) in enumerate(facts):
            x = M + 16 + i * 104
            if x + 100 > c.W - M - 190:
                break
            c.text(x, y + 96, val, fill=P["GOLD"], font=F["md"])
            c.text(x, y + 114, k, fill=P["DIM"], font=F["xs"])
    if meta.get("first"):
        c.text(c.W - M - 16, y + 46, "%s %s" % (t("first_played"), C.day_key(C.day_index(meta["first"], v.z()))), fill=P["DIM"], font=F["xs"], anchor="e")
    CH.spark(c.cv, c.W - M - 176, y + 60, 160, 50, d["per_day"], P["GOLD"], CH.mix(P["CARD"], P["GOLD"], 0.18))
    c.text(c.W - M - 16, y + h - 10, t("plays_14"), fill=P["DIM"], font=F["xs"], anchor="e")
    c.text(c.W - M - 16, y + 16, "×", fill=P["DIM"], font=F["lg"], anchor="e")
    c.click(c.W - M - 40, y, c.W - M, y + 30, lambda: app.st_select_song(""))
    return y + h


def pg_days(c):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    y = c.pills(M, 14, [(14, "14"), (30, "30"), (90, "90")], app.st_days, app.st_set_days) + 14
    ser = v.series(app.st_days)
    lis = [r["listen"] for r in ser]
    act = [r for r in ser if r["listen"] >= C.ACTIVE_DAY_S]
    best = max(ser, key=lambda r: r["listen"])
    n, cw = c.cols(4)
    cards = ((t("total"), c.dur(sum(lis)), ""), (t("avg_cal"), c.dur(sum(lis) / max(1, len(ser))), ""), (t("avg_active"), c.dur(sum(r["listen"] for r in act) / max(1, len(act))), X.n_days(len(act), c.lg)),
             (t("best_day"), c.dur(best["listen"]), X.fmt_date(best["key"], c.lg) if best["listen"] else ""))
    for i, (cap, val, sub) in enumerate(cards):
        x, yy = M + (i % n) * (cw + G), y + (i // n) * (96 + G)
        c.card(x, yy, cw, 96, cap)
        c.text(x + 16, yy + 52, val, fill=P["GOLD"] if i == 0 else P["TXT"], font=F["lg"])
        c.text(x + 16, yy + 78, sub, fill=P["DIM"], font=F["xs"])
    y += ((len(cards) + n - 1) // n) * (96 + G)
    c.card(M, y, c.W - 2 * M, 260, t("by_day"))
    CH.bars(c.cv, M + 16, y + 30, c.W - 2 * M - 32, 224, [(r["key"][8:], r["listen"]) for r in ser], P, F["xs"], max(1, len(ser) // 15), c.hits, len(ser) - 1,
            lambda i: "%s\n%s %s\n%s %s\n%s %d" % (X.fmt_date(ser[i]["key"], c.lg), t("listening"), c.dur(ser[i]["listen"]), t("appopen"), c.dur(ser[i]["open"]), t("plays"), ser[i]["plays"]),
            lambda s: X.fmt_axis(s, c.lg), [r["open"] for r in ser])
    y += 260 + G
    h = 44 + len(ser) * 32
    c.card(M, y, c.W - 2 * M, h, t("by_day"))
    mx = max(lis) or 1
    wide = c.W >= 700
    for i, r in enumerate(reversed(ser)):
        yy = y + 46 + i * 32
        c.text(M + 16, yy, X.fmt_date(r["key"], c.lg), fill=P["TXT"] if r["listen"] else P["DIM"], font=F["sm"])
        bx = M + 150
        bwid = max(40, min(260, c.W - 2 * M - 150 - (330 if wide else 230)))
        CH.hbar(c.cv, bx, yy - 4, bwid, 8, r["listen"] / mx, P["GOLD"] if r["key"] == ser[-1]["key"] else P["BRN2"], P["CARD2"])
        c.text(bx + bwid + 12, yy, c.dur(r["listen"]) if r["listen"] else "·", fill=P["TXT"], font=F["sm"])
        c.text(c.W - M - 16 - (150 if wide else 0), yy, "%s %s" % (t("open_"), c.dur(r["open"])) if r["open"] else "", fill=P["DIM"], font=F["xs"], anchor="e")
        if wide:
            c.text(c.W - M - 16, yy, fit(F["xs"], ((v.title(r["top"])[0]) if r["top"] else ""), 136), fill=P["DIM"], font=F["xs"], anchor="e")
    return y + h + 24


def pg_time(c):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    y = c.pills(M, 14, [(k, t(lab)) for k, lab in PERIODS[1:]], app.st_period if app.st_period != "today" else "30d", app.st_set_period) + 14
    per = app.st_period if app.st_period != "today" else "30d"
    hm = v.heat(per)
    tot = v.totals(per)
    wl = X.T(c.lg, "weekdays")
    c.card(M, y, c.W - 2 * M, 252, t("heat") + " · " + t(dict(PERIODS_LABEL)[per]))
    CH.heatmap(c.cv, M + 16, y + 34, c.W - 2 * M - 32, hm["m"], hm["n"], P, F["xs"], wl, lambda d, h, val: "%s %02d:00\n%s" % (X.T(c.lg, "weekdays_long")[d], h, c.dur(val) + " " + t("per_day")), c.hits)
    y += 252 + G
    n2, w2 = c.cols(2)
    c.card(M, y, w2, 210, t("per_hour"))
    CH.bars(c.cv, M + 16, y + 28, w2 - 32, 176, [("%02d" % h, tot["hours"][h]) for h in range(24)], P, F["xs"], 3, c.hits, (max(range(24), key=lambda h: tot["hours"][h]) if sum(tot["hours"]) else None),
            lambda i: "%02d:00\n%s" % (i, c.dur(tot["hours"][i])), lambda s: X.fmt_axis(s, c.lg))
    x2, y2 = (M + w2 + G, y) if n2 > 1 else (M, y + 210 + G)
    c.card(x2, y2, w2, 210, t("per_weekday"))
    wd = [sum(hm["m"][d]) for d in range(7)]
    avg = [(wd[d] / hm["n"][d]) if hm["n"][d] else 0.0 for d in range(7)]
    CH.bars(c.cv, x2 + 16, y2 + 28, w2 - 32, 176, [(wl[d], avg[d]) for d in range(7)], P, F["xs"], 1, c.hits, (max(range(7), key=lambda d: avg[d]) if sum(avg) else None),
            lambda i: "%s\n%s %s" % (X.T(c.lg, "weekdays_long")[i], c.dur(avg[i]), t("per_day")), lambda s: X.fmt_axis(s, c.lg))
    y += (210 if n2 > 1 else 420 + G) + G
    c.card(M, y, c.W - 2 * M, 120, t("surfaces"))
    surf = tot["surfaces"]
    total = sum(surf.values()) or 1.0
    for i, (k, val) in enumerate(sorted(surf.items(), key=lambda kv: -kv[1])[:3]):
        yy = y + 44 + i * 26
        c.text(M + 16, yy, {"gui": "Window (GUI)", "tui": "Terminal (TUI)", "daemon": "Daemon"}.get(k, k), fill=P["TXT"], font=F["sm"])
        CH.hbar(c.cv, M + 160, yy - 4, max(60, c.W - 2 * M - 330), 8, val / total, P["BRN2"], P["CARD2"])
        c.text(c.W - M - 16, yy, "%s  (%s)" % (c.dur(val), X.fmt_pct(val / total)), fill=P["DIM"], font=F["xs"], anchor="e")
    if not surf:
        c.text(M + 16, y + 56, t("none"), fill=P["DIM"], font=F["sm"])
    return y + 120 + 24


PERIODS_LABEL = (("7d", "w7"), ("30d", "d30"), ("year", "year"), ("all", "all"), ("today", "today"))


def pg_activity(c):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    y = c.pills(M, 14, [(k, t(lab)) for k, _kinds, lab in FILTERS], app.st_filter, app.st_set_filter, F["xs"]) + 14
    kinds = next((ks for k, ks, _l in FILTERS if k == app.st_filter), None)
    evs = list(reversed(v.events(80, kinds)))[:60]
    n2, w2 = c.cols(2)
    lw = (c.W - 2 * M - G) * 0.62 if n2 > 1 else c.W - 2 * M
    h = 44 + max(1, len(evs)) * 28
    c.card(M, y, lw, h, t("activity"))
    if not evs:
        c.text(M + 16, y + 58, t("none"), fill=P["DIM"], font=F["sm"])
    for i, ev in enumerate(evs):
        yy = y + 52 + i * 28
        c.cv.create_oval(M + 16, yy - 4, M + 24, yy + 4, fill=CH.kind_color(ev[2], P), outline="")
        c.text(M + 34, yy, C.clock(ev[0], ev[1]), fill=P["DIM"], font=F["xs"])
        line = X.ev_text(ev, c.lg)
        full = line.split("  ", 2)[-1]
        c.text(M + 100, yy, fit(F["sm"], full, lw - 120), fill=P["TXT"], font=F["sm"])
        if F["sm"].measure(full) > lw - 120:
            c.tip(M, yy - 13, M + lw, yy + 13, C.clock(ev[0], ev[1]) + "\n" + full)
    kcard_x, kcard_y = (M + lw + G, y) if n2 > 1 else (M, y + h + G)
    kw = c.W - 2 * M - lw - G if n2 > 1 else c.W - 2 * M
    kinds_n = v.kinds(app.st_period)
    krows = sorted(kinds_n.items(), key=lambda kv: -kv[1])[:16]
    pitems = [(k, t(lab)) for k, lab in PERIODS]
    prow = c.pill_rows(kcard_x + 16, pitems, F["xs"], kcard_x + 16, kcard_x + kw - 12)
    kh = 40 + prow * 34 + 14 + max(1, len(krows)) * 26 + 14
    c.card(kcard_x, kcard_y, kw, kh, t("kinds"))
    yy0 = c.pills(kcard_x + 16, kcard_y + 34, pitems, app.st_period, app.st_set_period, F["xs"], kcard_x + 16, kcard_x + kw - 12)
    mx = max([v_ for _k, v_ in krows] + [1])
    for i, (k, val) in enumerate(krows):
        yy = yy0 + 24 + i * 26
        nm = k.split(":")[0]
        lab = t("k_" + nm) if ("k_" + nm) in X.TX["en"] else nm
        if k.startswith("ui:"):
            lab += " · " + k[3:]
        c.cv.create_oval(kcard_x + 16, yy - 4, kcard_x + 24, yy + 4, fill=CH.kind_color(nm, P), outline="")
        c.text(kcard_x + 34, yy, fit(F["sm"], lab, kw * 0.48 - 34 - 10), fill=P["TXT"], font=F["sm"])
        CH.hbar(c.cv, kcard_x + kw * 0.48, yy - 3, kw * 0.26, 6, val / mx, P["BRN2"], P["CARD2"])
        c.text(kcard_x + kw - 16, yy, X.fmt_num(val, c.lg), fill=P["DIM"], font=F["xs"], anchor="e")
    return max(y + h, kcard_y + kh) + 24


def pg_records(c):
    v, P, F, t, app = c.v, c.P, c.F, c.t, c.app
    rc = v.records()
    q = v.quality()
    y = 14
    n, cw = c.cols(4)
    cards = []
    if rc["best_day"][0]:
        cards.append((t("best_day"), c.dur(rc["best_day"][1]), X.fmt_date(rc["best_day"][0], c.lg, True)))
    if rc["most_plays_day"][0]:
        cards.append((t("most_plays"), str(rc["most_plays_day"][1]), X.fmt_date(rc["most_plays_day"][0], c.lg, True)))
    if rc["most_repeats"][2] > 1:
        cards.append((t("most_repeat"), "%dx" % rc["most_repeats"][2], v.title(rc["most_repeats"][1])[0]))
    if rc["longest_bout"][1] > 0:
        cards.append((t("longest_bout"), c.dur(rc["longest_bout"][1]), X.n_songs(rc["longest_bout"][2], c.lg)))
    if rc["longest_session"][1] > 0:
        cards.append((t("longest_session"), c.dur(rc["longest_session"][1]), rc["longest_session"][2]))
    if rc["most_open_day"][0]:
        cards.append((t("most_open"), c.dur(rc["most_open_day"][1]), X.fmt_date(rc["most_open_day"][0], c.lg, True)))
    s = rc["streak"]
    cards.append((t("longest_streak"), X.n_days(s["longest"], c.lg), ("%s → %s" % (s["longest_from"], s["longest_to"])) if s["longest"] else ""))
    cards.append((t("current_streak"), X.n_days(s["current"], c.lg), ""))
    for i, (cap, val, sub) in enumerate(cards):
        x, yy = M + (i % n) * (cw + G), y + (i // n) * (100 + G)
        c.card(x, yy, cw, 100, cap)
        c.text(x + 16, yy + 54, val, fill=P["GOLD"], font=F["lg"])
        c.text(x + 16, yy + 82, fit(F["xs"], sub, cw - 32), fill=P["DIM"], font=F["xs"])
    y += ((len(cards) + n - 1) // n) * (100 + G)
    # data quality: the card's height follows what is in it (narrow windows wrap the buttons and push the rows down)
    ver = app.st_ver
    wide = c.W >= 700
    ok_ = ver is not None and ver.get("ok")
    col = P["OK"] if ok_ else (P["RED"] if ver is not None else P["DIM"])
    msg = (t("chain_ok") if ok_ else t("chain_bad")) if ver is not None else (t("checking") if app.st_checking else t("not_verified"))
    errs = (ver.get("errors") or [])[:2] if ver is not None else []
    rows = ((t("records_n"), X.fmt_num(q["records"], c.lg)), (t("since"), X.fmt_stamp(q["first"], v.z(), c.lg) if q.get("first") else "-"), (t("observed"), "%s  (%s)" % (c.dur(q["live_s"]), X.fmt_pct(q["live_share"]))),
            (t("inferred"), "%s  (%s)" % (c.dur(q["inferred_s"]), X.fmt_pct(q["inferred_share"]))), (t("gaps"), "%d  (%s)" % (q["gaps"], c.dur(q["gap_s"]))), (t("clocks"), str(q["clock_jumps"])),
            (t("recovered"), str(q["recovered"])))
    status_h = 88 + 16 * len(errs)                                    # the status line, the chain details and up to two errors
    ry = 36 if wide else status_h + 10
    body = max(status_h + (60 if wide else 0), ry + len(rows) * 22 + 6) if wide else ry + len(rows) * 22 + 6
    tools = ((t("verify"), app.st_verify), (t("export") + " CSV", lambda: app.st_export("csv")), (t("export") + " JSON", lambda: app.st_export("json")), (t("define"), app.st_toggle_define))
    bxs, bx, brow = [], 16, 0
    for lab, fn in tools:
        w = F["sm"].measure(lab) + 28
        if bx + w > c.W - 2 * M - 16 and bx > 16:
            bx, brow = 16, brow + 1
        bxs.append((lab, fn, bx, brow, w))
        bx += w + 8
    qh = body + 14 + (brow + 1) * 34 + (22 if app.st_note else 6)
    c.card(M, y, c.W - 2 * M, qh, t("quality") + " · " + t("integrity"))
    c.cv.create_oval(M + 16, y + 40, M + 28, y + 52, fill=col, outline="")
    c.text(M + 38, y + 46, msg, fill=col, font=F["md"])
    if ver is not None:
        c.text(M + 38, y + 68, "n=%d  %s  %s" % (ver.get("n", 0), ver.get("head", ""), ("· " + t("verified") + (" (deep)" if ver.get("deep") else "")) if ok_ else ""), fill=P["DIM"], font=F["xs"])
        for j, e in enumerate(errs):
            c.text(M + 38, y + 86 + j * 16, fit(F["xs"], e, c.W - 2 * M - 60), fill=P["RED"], font=F["xs"])
    if wide:                                                          # a short explanation of what the light means, in the free left half
        c.cv.create_text(M + 16, y + status_h + 8, text=t("integrity_note"), fill=P["DIM"], font=F["xs"], anchor="nw", width=(c.W - 2 * M) * 0.5 - 40)
    rx = M + (c.W - 2 * M) * (0.5 if wide else 0.0)
    for i, (k, val) in enumerate(rows):
        c.text(rx + 16, y + ry + 8 + i * 22, k, fill=P["DIM"], font=F["xs"])
        c.text(c.W - M - 16, y + ry + 8 + i * 22, val, fill=P["TXT"], font=F["xs"], anchor="e")
    for lab, fn, bx, brow, w in bxs:
        by = y + body + 14 + brow * 34
        CH.pill(c.cv, M + bx, by, lab, False, F["sm"], P)
        c.click(M + bx, by, M + bx + w, by + 28, fn)
    if app.st_note:
        c.text(M + 16, y + qh - 14, fit(F["xs"], app.st_note, c.W - 2 * M - 32), fill=P["GOLD"], font=F["xs"])
    y += qh + G
    if app.st_define:
        c.card(M, y, c.W - 2 * M, 10, "")
        txt = X.definitions(c.lg)
        item = c.cv.create_text(M + 16, y + 16, text=txt, fill=P["TXT"], font=F["xs"], anchor="nw", width=c.W - 2 * M - 32)
        bb = c.cv.bbox(item)
        hh = (bb[3] - bb[1]) + 32 if bb else 200
        c.cv.delete("defbox")
        CH.box(c.cv, M, y, c.W - M, y + hh, P, 12, fill=P["CARD"], outline=P["GRID"], tags="defbox")
        c.cv.tag_lower("defbox", item)
        y += hh + G
    c.text(M, y + 8, t("not_medical"), fill=P["DIM"], font=F["xs"])
    return y + 40


PAGES = {"overview": pg_overview, "live": pg_live, "songs": lambda c: pg_rank(c, "song"), "artists": lambda c: pg_rank(c, "artist"), "days": pg_days, "time": pg_time,
         "activity": pg_activity, "records": pg_records}


# ---------------------------------------------------------------- the window
class Mixin:
    def st_lang(self):
        return "id" if self.T("home") == "Beranda" else "en"

    def st_base_font(self):
        """(family, size) of the window's normal font. The host keeps fonts as tuples like ("DejaVu Sans", 11); a tkfont.Font object works too."""
        f = getattr(self, "f_ui", None)
        fam, size = "DejaVu Sans", 10
        try:
            if isinstance(f, (tuple, list)):
                fam, size = str(f[0]), int(f[1])
            elif f is not None:
                fam, size = f.actual("family"), int(f.actual("size"))
        except Exception:
            pass
        return fam, size

    def st_fonts(self):
        if self.st_fnt is not None:
            return self.st_fnt
        fam, base = self.st_base_font()
        sg = -1 if base < 0 else 1
        b = abs(base) or 10
        try:
            mono = tkfont.nametofont("TkFixedFont").actual("family")
        except Exception:
            mono = "Courier"
        fm = getattr(self, "f_mono", None)
        if isinstance(fm, (tuple, list)) and fm:
            mono = str(fm[0])

        def mk(k, weight="normal", family=None):
            return tkfont.Font(family=family or fam, size=sg * max(7, int(round(b * k))), weight=weight)
        self.st_fnt = {"xs": mk(0.78), "sm": mk(0.9), "md": mk(1.0), "lg": mk(1.3, "bold"), "xl": mk(1.95, "bold"), "mono": mk(2.5, "bold", mono)}
        return self.st_fnt

    # -------------------------------------------------- the page (a menu item in the sidebar, right under Visual)
    def st_build_view(self):
        """Builds the page inside app.main and returns its frame (the host packs it when the page is opened)."""
        P = palette()
        lg = self.st_lang()
        self.st_fnt = None                                         # fonts follow the look: made again after every rebuild
        fr = tk.Frame(self.main, bg=P["PNL"])
        self.st_win = fr
        if AN is None:
            tk.Label(fr, text="rofpalys_analytics.py / _calc / _text / rofpalys_gui_stats_charts.py are missing.\nRun: python ~/rofpalys.py install", bg=P["PNL"], fg=P["DIM"],
                     font=self.f_ui, justify="left", anchor="nw").pack(fill="x", padx=24, pady=24)
            self.st_cv = self.st_tabs = self.st_status = None
            return fr
        self.st_status = tk.Label(fr, text="", bg=P["PNL"], fg=P["DIM"], font=self.f_small, anchor="w")
        self.st_status.pack(side="bottom", fill="x", padx=18, pady=(0, 4))
        self.st_tabs = tk.Canvas(fr, height=58, bg=P["PNL"], highlightthickness=0)
        self.st_tabs.pack(side="top", fill="x")
        body = tk.Frame(fr, bg=P["PNL"])
        body.pack(side="top", fill="both", expand=True)
        self.st_cv = tk.Canvas(body, bg=P["PNL"], highlightthickness=0, takefocus=1)
        sb = tk.Scrollbar(body, orient="vertical", command=self.st_cv.yview, bg=P["PNL2"], troughcolor=P["PNL"], activebackground=P["HOVER"], bd=0, highlightthickness=0, width=10)
        self.st_cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.st_cv.pack(side="left", fill="both", expand=True)
        self.st_cv.bind("<Configure>", lambda e: self.st_later())
        self.st_tabs.bind("<Configure>", lambda e: self.st_draw_tabs())
        self.st_tabs.bind("<Button-1>", lambda e: self.st_hit(self.st_tabs, e, self.st_tab_clicks))
        self.st_cv.bind("<Button-1>", lambda e: (self.st_cv.focus_set(), self.st_hit(self.st_cv, e, self.st_clicks)))
        self.st_cv.bind("<Motion>", self.st_motion)
        self.st_cv.bind("<Leave>", lambda e: self.st_cv.delete("tip"))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.st_cv.bind(seq, self.st_wheel)
        self.st_cv.bind("<Key-Left>", lambda e: (self.st_step(-1), "break")[1])           # "break": the arrow keys step the tabs here instead of seeking the song
        self.st_cv.bind("<Key-Right>", lambda e: (self.st_step(1), "break")[1])
        self.st_cv.bind("<Escape>", lambda e: (self.st_close(), "break")[1])
        self.st_ver, self.st_note, self.st_view, self.st_view_t = None, "", None, 0.0
        self.st_after = None
        self.st_mouse = None
        self.st_clicks, self.st_hits, self.st_tab_clicks = [], [], []
        return fr

    def st_show(self):
        """Called by the host every time the page is opened."""
        if self.st_cv is None:
            return
        self.st_draw_tabs()
        self.st_redraw()
        if self.st_tab == "records" and self.st_ver is None:
            self.st_verify(False)
        try:
            self.st_cv.focus_set()
        except Exception:
            pass

    def st_open(self, tab=None):
        if tab in TABS:
            self.st_tab = tab
        if hasattr(self, "go"):
            self.go("stats")

    def st_close(self):
        if getattr(self, "view", "") == "stats":
            self.go("library")

    open_stats = show_stats = stats_dialog = open_stats_dialog = lambda self, *a: self.st_open()

    def st_toggle(self, _e=None):
        if getattr(self, "view", "") == "stats":
            self.st_close()
        else:
            self.st_open()

    def st_visible(self):
        return self.st_cv is not None and getattr(self, "view", "") == "stats"

    # -------------------------------------------------- state changes (each one redraws)
    def st_set_tab(self, k):
        self.st_tab = k
        self.st_draw_tabs()
        if self.st_cv is None:
            return
        self.st_cv.yview_moveto(0)
        self.st_redraw()
        if k == "records" and self.st_ver is None:
            self.st_verify(False)                                  # the integrity light is never left blank: a quick check of the chain runs when the page opens

    def st_step(self, d):
        if self.st_cv is None:
            return
        i = (TABS.index(self.st_tab) + d) % len(TABS)
        self.st_set_tab(TABS[i])

    def st_set_period(self, k):
        self.st_period = k
        self.st_redraw()

    def st_set_by(self, k):
        self.st_by = k
        self.st_redraw()

    def st_set_rule(self, k):
        self.st_rule = k
        self.st_redraw()

    def st_set_level(self, k):
        self.st_level = k
        self.st_redraw()

    def st_set_days(self, k):
        self.st_days = k
        self.st_redraw()

    def st_set_filter(self, k):
        self.st_filter = k
        self.st_redraw()

    def st_select_song(self, path):
        self.st_sel = path if path != self.st_sel else ""
        if path and self.st_tab != "songs":
            self.st_tab = "songs"
            self.st_draw_tabs()
        self.st_redraw()

    def st_toggle_define(self):
        self.st_define = not self.st_define
        self.st_redraw()

    # -------------------------------------------------- tools of the records page
    def st_verify(self, deep=True):
        if self.st_checking:
            return
        self.st_checking = True
        self.st_note = X.T(self.st_lang(), "verify") + " ..." if deep else ""
        self.st_redraw()

        def work():
            try:
                self._st_job = ("ver", AN.verify(deep=deep))
            except Exception as e:
                self._st_job = ("err", repr(e))
        threading.Thread(target=work, daemon=True).start()

    def st_export(self, kind):
        lg = self.st_lang()
        home = os.path.expanduser("~")
        for cand in (os.path.join(home, "storage", "downloads"), os.path.join(home, "Downloads"), home):
            if os.path.isdir(cand):
                break
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(cand, "rofpalys-stats-%s" % stamp) + (".json" if kind == "json" else "")
        try:
            files = AN.export(kind, dest)
            self.st_note = "%s: %s" % (X.T(lg, "exported"), files[0] if kind == "json" else dest)
        except Exception as e:
            self.st_note = "export failed: %r" % (e,)
        self.st_redraw()

    # -------------------------------------------------- drawing
    def st_later(self):
        if self.st_after is None and self.st_cv is not None:
            try:
                self.st_after = self.st_cv.after(60, self._st_do_redraw)
            except Exception:
                self.st_after = None

    def _st_do_redraw(self):
        self.st_after = None
        self.st_redraw()

    def st_draw_tabs(self):
        cv = self.st_tabs
        if cv is None:
            return
        try:
            P, F, lg = palette(), self.st_fonts(), self.st_lang()
            cv.delete("all")
            cv.configure(bg=P["PNL"])
            self.st_tab_clicks = []
            W = max(cv.winfo_width(), 300)
            cv.create_text(M, 18, text=X.T(lg, "stats").upper(), fill=P["TXT"], font=F["lg"], anchor="w")
            rec = AN is not None and AN.recorder() is not None and AN.recorder().state == "running"
            cv.create_oval(W - M - 8, 14, W - M, 22, fill=P["OK"] if rec else P["WARN"], outline="")
            cv.create_text(W - M - 14, 18, text=X.T(lg, "rec_on") if rec else X.T(lg, "rec_off"), fill=P["DIM"], font=F["xs"], anchor="e")
            x, y = M, 30
            for k in TABS:
                lab = X.T(lg, "tab_" + k)
                w = F["sm"].measure(lab) + 24
                if x + w > W - M and x > M:
                    x, y = M, y + 30
                CH.pill(cv, x, y, lab, k == self.st_tab, F["sm"], P, h=24, pad=12)
                self.st_tab_clicks.append((x, y, x + w, y + 24, (lambda kk=k: self.st_set_tab(kk))))
                x += w + 6
            need = y + 34
            if int(float(cv.cget("height"))) != need:
                cv.configure(height=need)
        except Exception as e:
            log("stats tabs: %r" % (e,))

    def st_view_now(self):
        """The numbers: with a running recorder a fresh View each time (cheap); otherwise one View read from the files, kept for a few seconds."""
        rec = AN.recorder() if AN is not None else None
        if rec is not None and rec.state == "running":
            return rec.view()
        if self.st_view is None or time.time() - self.st_view_t > 5.0:
            self.st_view, self.st_view_t = AN.View(None), time.time()
        return self.st_view

    def st_redraw(self):
        cv = self.st_cv
        if cv is None or self.st_win is None or not self.st_visible():
            return
        try:
            top = cv.yview()[0]
            W = max(cv.winfo_width(), 360)
            P, lg = palette(), self.st_lang()
            cv.configure(bg=P["PNL"])
            cv.delete("all")
            c = Ctx(self, cv, W, P, self.st_fonts(), lg, self.st_view_now())
            h = PAGES[self.st_tab](c)
            self.st_clicks, self.st_hits = c.clicks, c.hits
            cv.configure(scrollregion=(0, 0, W, max(h, cv.winfo_height())))
            cv.yview_moveto(top)
            self.st_last = time.time()
            if self.st_status is not None:
                rec = AN.recorder()
                self.st_status.configure(text=(X.T(lg, "tip_f7") if rec is not None and rec.state == "running" else X.T(lg, "no_recorder")), bg=P["PNL"], fg=P["DIM"])
            self.st_draw_tabs()
            if self.st_mouse:
                self.st_motion(self.st_mouse)
        except Exception as e:
            log("stats redraw: %r" % (e,))

    def st_hit(self, cv, e, clicks):
        x, y = cv.canvasx(e.x), cv.canvasy(e.y)
        for x1, y1, x2, y2, fn in reversed(clicks):
            if x1 <= x <= x2 and y1 <= y <= y2:
                try:
                    fn()
                except Exception as ex:
                    log("stats click: %r" % (ex,))
                return

    def st_motion(self, e):
        cv = self.st_cv
        if cv is None:
            return
        self.st_mouse = e
        x, y = cv.canvasx(e.x), cv.canvasy(e.y)
        txt = ""
        for x1, y1, x2, y2, _k, text in self.st_hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                txt = text
                break
        hand = any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2, _f in self.st_clicks)
        try:
            cv.configure(cursor="hand2" if hand else "")
            CH.tooltip(cv, txt, x, y, palette(), self.st_fonts()["xs"], cv.winfo_width())
        except Exception:
            pass

    def st_wheel(self, e):
        d = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
        try:
            self.st_cv.yview_scroll(d * 3, "units")
        except Exception:
            pass

    # -------------------------------------------------- real time
    def st_poll(self):
        if not self.st_visible():
            return
        job, self._st_job = self._st_job, None
        if job:
            self.st_checking = False
            if job[0] == "ver":
                self.st_ver = job[1]
                self.st_note = ""
            else:
                self.st_note = job[1]
            self.st_redraw()
            return
        every = 1.0 if self.st_tab in LIVE_TABS else 5.0
        if time.time() - self.st_last >= every:
            self.st_redraw()


def build_stats_button(app, bar):
    app.b_stats = IconBtn(bar, "stats", app.st_open, size=20, bg=PNL, pad=7)
    app.b_stats.pack(side="right")
    return [app.b_stats.cv]


def register(app):
    app.st_win = app.st_cv = app.st_tabs = app.st_status = app.st_fnt = app.st_after = app.st_mouse = None
    app.st_tab, app.st_period, app.st_by, app.st_rule, app.st_level, app.st_days, app.st_filter = "overview", "all", "plays", "lastfm", "artist", 30, "all"
    app.st_sel, app.st_ver, app.st_note, app.st_define, app.st_view, app.st_view_t, app.st_last, app._st_job, app.st_checking = "", None, "", False, None, 0.0, 0.0, None, False
    app.st_clicks, app.st_hits, app.st_tab_clicks = [], [], []
    if hasattr(app, "add_nav") and hasattr(app, "add_view"):
        app.add_nav(55, "stats", "stats_nav", "stats")             # the sidebar item: right under Visual (50) and above Settings (90)
        app.add_view("stats", lambda a: a.st_build_view(), lambda a: a.st_show())
    if AN is None:
        return
    try:
        AN.start(E, "gui")                                        # the launcher starts it first; this makes sure when the window is started another way
    except Exception:
        pass
    app.add_toolbar(14, build_stats_button)
    app.add_poll(lambda a: a.st_poll())
    if hasattr(app, "add_relabel"):
        app.add_relabel(lambda a: a.st_redraw())                  # a language change: the page is drawn again at once
    try:
        app.root.bind_all("<F7>", app.st_toggle)
    except Exception:
        pass
    if TH2 is not None:
        TH2.on_switch(lambda old, new, m: app.st_redraw())


# END-OF-FILE rofpalys_gui_stats.py

