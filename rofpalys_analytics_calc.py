#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - statistics maths: raw facts in, numbers out (no files, no engine, no UI)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The recorder (rofpalys_analytics.py) writes RAW FACTS: a play started, a stretch of listening of so many seconds from this moment, a play ended, the volume
changed, ... This file turns the facts into numbers. The rules (what counts as a play, a skip, a completed song, a streak day) live HERE, as plain constants,
so a rule can change without losing a single fact: the numbers are simply recomputed from the log (RULES_V tells the saved summary when to do that).

  Agg          takes the records one by one (ingest) and keeps per-day summaries: listening seconds, app-open seconds, 24 hour buckets of both, per-song counters.
  overlay      the part of "now" that is not in a record yet (the running stretch of listening, the running session), so the numbers tick in real time.
  totals/rank/series/heat/streaks/records/quality/overview   ask questions of an Agg; every one takes the overlay as an optional last argument.

Time: every record carries its UTC time in milliseconds and the UTC offset (minutes) that was valid at that moment. A "day" is the local calendar day with THAT offset,
so the day boundaries stay right after a time-zone change. Intervals that cross an hour or midnight are split exactly (split_hours).
Everything here is plain Python (no numpy)."""
import datetime as _dt

__version__ = "1.0"
RULES_V = 1

# ---------------------------------------------------------------- the rules (definitions are printed by `rofpalys stats define`)
SP_MIN = 30.0                        # Spotify-style stream: at least 30 s of listening
LF_MIN, LF_FRAC, LF_ABS = 30.0, 0.5, 240.0   # Last.fm-style scrobble: at least 30 s AND (half the song OR 4 minutes); the song must be longer than 30 s
DONE_FRAC = 0.9                      # completed: the song ended by itself, or you got to 90 % of it
SKIP_S = 30.0                        # skipped: you left before 30 s of listening
BOUT_GAP = 300.0                     # a listening bout goes on while the pause between two stretches is at most 5 minutes
ACTIVE_DAY_S = 60.0                  # a day counts for the streak when you listened at least a minute
RECENT_N, RECENT_PLAYS_N = 400, 300  # how many latest events / plays are kept for the live feed
RULES = ("lastfm", "spotify", "starts", "finished")
_RULE_AT = {"starts": 0, "lastfm": 1, "spotify": 2, "finished": 3}

_EPOCH = 719163                      # date.fromordinal() of 1970-01-01
_DK = {}


# ---------------------------------------------------------------- time
def day_index(t_ms, z=0):
    """Local day number (0 = 1970-01-01) of a UTC time in ms with a UTC offset in minutes."""
    return (int(t_ms) + int(z) * 60000) // 86400000


def day_key(i):
    k = _DK.get(i)
    if k is None:
        k = _DK[i] = _dt.date.fromordinal(_EPOCH + int(i)).isoformat()
    return k


def key_index(k):
    return _dt.date.fromisoformat(k).toordinal() - _EPOCH


def weekday(i):
    """0 = Monday ... 6 = Sunday for a day number."""
    return (int(i) + 3) % 7


def hour_of(t_ms, z=0):
    return ((int(t_ms) + int(z) * 60000) % 86400000) // 3600000


def clock(t_ms, z=0):
    """'HH:MM:SS' local time of a UTC ms time."""
    s = ((int(t_ms) + int(z) * 60000) % 86400000) // 1000
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def split_hours(a_ms, b_ms, z=0):
    """Yield (day_number, hour, seconds) for every local hour the interval [a, b) touches - exact, also across midnight."""
    a = int(a_ms) + int(z) * 60000
    b = int(b_ms) + int(z) * 60000
    while a < b:
        e = min(b, (a // 3600000 + 1) * 3600000)
        yield a // 86400000, (a % 86400000) // 3600000, (e - a) / 1000.0
        a = e


def classify(listened, dur, why, reach):
    """(lastfm, spotify, completed, skipped) as 0/1 for one finished play."""
    sp = listened >= SP_MIN
    lf = listened >= LF_MIN and ((dur >= LF_MIN and listened >= LF_FRAC * dur) or listened >= LF_ABS)
    done = why == "finished" or (dur > 0 and reach >= DONE_FRAC * dur)
    skip = why == "left" and listened < SKIP_S
    return int(lf), int(sp), int(bool(done)), int(skip)


def _day():
    return {"l": 0.0, "o": 0.0, "h": [0.0] * 24, "oh": [0.0] * 24, "s": {}, "e": {}, "ss": 0, "sf": {}}


def _srow():
    return [0, 0, 0, 0, 0, 0.0]          # starts, lastfm, spotify, completed, skipped, listening seconds


def _short(v, n=90):
    v = str(v)
    return v if len(v) <= n else v[:n - 1] + "…"


# ---------------------------------------------------------------- the aggregate
class Agg:
    """Per-day summaries built from the records. ingest() is called once per record, in order; state()/from_state() save and load it."""

    def __init__(self):
        self.days = {}          # "YYYY-MM-DD" -> day dict
        self.songs = {}         # path -> {"title","artist","folder","dur","first","last"}
        self.so = {}            # open sessions   sid -> {"a","z","surf","last","listen","plays"}
        self.pl = {}            # open plays      id  -> {"path","t","z","dur","listen","sid"}
        self.sessions = []      # closed sessions [a, b, surface, listened, plays, why, z]
        self.bouts = []         # closed listening bouts [a, b, listened, plays, z]
        self.bout = None        # the open bout {"a","b","listen","plays","pid","z"}
        self.plays = []         # latest finished plays [t, z, path, listened, why, tier(0/1/2), reach]
        self.recent = []        # latest events [t, z, kind, {small}]
        self.q = {"records": 0, "bad": 0, "orphan": 0, "gaps": 0, "gap_s": 0.0, "live_s": 0.0, "inferred_s": 0.0, "clock_jumps": 0, "recovered": 0, "torn": 0, "first": 0, "last": 0}
        self.head = {"n": 0, "h": "0" * 16}
        self._first = None
        self.on_play = None     # optional: called with every finished play row (the exporter collects them all)

    # ------------------------------------------------------------ helpers
    def _d(self, i):
        k = day_key(i)
        d = self.days.get(k)
        if d is None:
            d = self.days[k] = _day()
            if self._first is None or i < self._first:
                self._first = i
        return d

    def first_day(self):
        if self._first is None and self.days:
            self._first = min(key_index(k) for k in self.days)
        return self._first

    def _listen(self, a, b, z, path):
        for di, hh, s in split_hours(a, b, z):
            d = self._d(di)
            d["l"] += s
            d["h"][hh] += s
            if path:
                d["s"].setdefault(path, _srow())[5] += s

    def _open(self, a, b, z, surf):
        for di, hh, s in split_hours(a, b, z):
            d = self._d(di)
            d["o"] += s
            d["oh"][hh] += s
            d["sf"][surf] = d["sf"].get(surf, 0.0) + s

    def _count(self, t, z, key, n=1):
        e = self._d(day_index(t, z))["e"]
        e[key] = e.get(key, 0) + n

    def title_of(self, path):
        m = self.songs.get(path)
        return (m or {}).get("title") or (path.rsplit("/", 1)[-1] if path else "?")

    def artist_of(self, path):
        return (self.songs.get(path) or {}).get("artist") or ""

    # ------------------------------------------------------------ one record
    def ingest(self, rec):
        try:
            k = rec["k"]
            d = rec.get("d") or {}
            t = int(rec.get("at") or rec["t"])
            z = int(rec.get("z", 0))
            sid = rec.get("s", "")
            if rec.get("n") is not None:
                self.head = {"n": rec["n"], "h": rec.get("h", "")}
            if k == "file":                       # the header line of a new log file: part of the chain, not a fact
                return
            self.q["records"] += 1
            if not self.q["first"] or t < self.q["first"]:
                self.q["first"] = t
            if t > self.q["last"]:
                self.q["last"] = t
            so = self.so.get(sid)
            if so is not None and t > so["last"]:
                so["last"] = t
            h = _HANDLERS.get(k)
            if h is not None:
                getattr(self, h)(rec, d, t, z, sid)
            if k not in ("seg", "file"):
                self._count(t, z, ("ui:" + str(d.get("what", "?"))) if k == "ui" else k)
        except (KeyError, TypeError, ValueError, AttributeError):
            self.q["bad"] += 1

    def _ev(self, t, z, k, small):
        self.recent.append([t, z, k, {a: (_short(b) if isinstance(b, str) else b) for a, b in small.items()}])
        if len(self.recent) > RECENT_N + 100:
            del self.recent[:len(self.recent) - RECENT_N]

    # ------------------------------------------------------------ handlers
    def _h_sess(self, rec, d, t, z, sid):
        self.so[sid] = {"a": t, "z": z, "surf": str(d.get("surface", "?")), "last": t, "listen": 0.0, "plays": 0}
        self._d(day_index(t, z))["ss"] += 1
        self._ev(t, z, "sess", {"surface": d.get("surface", "?"), "ver": d.get("ver", "")})

    def _h_end(self, rec, d, t, z, sid):
        s = self.so.pop(sid, None)
        why = str(d.get("why", "exit"))
        if s is not None:
            b = max(t, s["a"])
            self._open(s["a"], b, s["z"], s["surf"])
            self.sessions.append([s["a"], b, s["surf"], round(s["listen"], 2), s["plays"], why, s["z"]])
        if why == "recovered":
            self.q["recovered"] += 1
        self._ev(t, z, "end", {"why": why, "up": round(((t - s["a"]) / 1000.0) if s else 0, 1)})

    def _h_play(self, rec, d, t, z, sid):
        path = str(d.get("path", ""))
        self.pl[d["id"]] = {"path": path, "t": t, "z": z, "dur": float(d.get("dur") or 0), "listen": 0.0, "sid": sid}
        m = self.songs.setdefault(path, {"title": "", "artist": "", "folder": "", "dur": 0.0, "first": t, "last": t})
        for f in ("title", "artist", "folder"):
            if d.get(f):
                m[f] = str(d[f])
        if d.get("dur"):
            m["dur"] = float(d["dur"])
        m["last"] = max(m["last"], t)
        self._d(day_index(t, z))["s"].setdefault(path, _srow())[0] += 1
        so = self.so.get(sid)
        if so is not None:
            so["plays"] += 1
        self._ev(t, z, "play", {"title": m["title"] or path.rsplit("/", 1)[-1], "artist": m["artist"]})

    def _h_seg(self, rec, d, t, z, sid):
        wall = float(d["d"])
        a = int(d["a"])
        if wall <= 0:
            return
        p = self.pl.get(d.get("id"))
        path = p["path"] if p else str(d.get("path", ""))
        self._listen(a, a + int(round(wall * 1000)), z, path)
        if p is not None:
            p["listen"] += wall
        so = self.so.get(sid)
        if so is not None:
            so["listen"] += wall
        if d.get("q") == "gap":
            self.q["inferred_s"] += wall
        else:
            self.q["live_s"] += wall
        b = a + int(round(wall * 1000))
        bt = self.bout
        pid = d.get("id")
        if bt is not None and a - bt["b"] <= BOUT_GAP * 1000:
            bt["b"] = max(bt["b"], b)
            bt["listen"] += wall
            if pid != bt["pid"]:
                bt["plays"] += 1
                bt["pid"] = pid
        else:
            if bt is not None:
                self.bouts.append([bt["a"], bt["b"], round(bt["listen"], 2), bt["plays"], bt["z"]])
            self.bout = {"a": a, "b": b, "listen": wall, "plays": 1, "pid": pid, "z": z}

    def _h_fin(self, rec, d, t, z, sid):
        p = self.pl.pop(d.get("id"), None)
        if p is None:
            self.q["orphan"] += 1
            return
        dur = float(d.get("dur") or p["dur"] or 0)
        reach = float(d.get("pos") or 0)
        why = str(d.get("why", "left"))
        lf, sp, done, skip = classify(p["listen"], dur, why, reach)
        row = self._d(day_index(p["t"], p["z"]))["s"].setdefault(p["path"], _srow())
        row[1] += lf
        row[2] += sp
        row[3] += done
        row[4] += skip
        tier = 2 if lf else (1 if sp else 0)
        row_ = [p["t"], p["z"], p["path"], round(p["listen"], 1), why, tier, round(reach / dur, 3) if dur else 0]
        self.plays.append(row_)
        if self.on_play is not None:
            self.on_play(list(row_))
        if len(self.plays) > RECENT_PLAYS_N + 100:
            del self.plays[:len(self.plays) - RECENT_PLAYS_N]
        self._ev(t, z, "fin", {"title": self.title_of(p["path"]), "artist": self.artist_of(p["path"]), "why": why, "listened": round(p["listen"], 1), "tier": tier})

    def _h_gap(self, rec, d, t, z, sid):
        self.q["gaps"] += 1
        self.q["gap_s"] += float(d.get("s", 0))
        self._ev(t, z, "gap", {"s": float(d.get("s", 0))})

    def _h_clock(self, rec, d, t, z, sid):
        self.q["clock_jumps"] += 1
        self._ev(t, z, "clock", {"delta": d.get("delta", 0)})

    def _h_torn(self, rec, d, t, z, sid):
        self.q["torn"] += 1
        self._ev(t, z, "recover", {"what": "torn", "bytes": d.get("bytes", 0)})

    def _h_simple(self, rec, d, t, z, sid):
        k = rec["k"]
        small = {a: b for a, b in d.items() if a in ("from", "to", "name", "path", "on", "left", "n", "label", "source", "what", "title", "artist", "delta", "pos", "id") and not isinstance(b, (dict, list))}
        if "path" in small:
            small["title"] = self.title_of(small["path"])
        self._ev(t, z, k, small)

    # ------------------------------------------------------------ save / load
    def state(self):
        return {"v": RULES_V, "days": self.days, "songs": self.songs, "so": self.so, "pl": self.pl, "sessions": self.sessions, "bouts": self.bouts, "bout": self.bout,
                "plays": self.plays, "recent": self.recent[-RECENT_N:], "q": self.q, "head": self.head}

    @classmethod
    def from_state(cls, s):
        a = cls()
        if not isinstance(s, dict) or s.get("v") != RULES_V:
            raise ValueError("saved summary has other rules")
        a.days, a.songs, a.so, a.pl = s["days"], s["songs"], s["so"], s["pl"]
        a.sessions, a.bouts, a.bout, a.plays, a.recent = s["sessions"], s["bouts"], s["bout"], s["plays"], s["recent"]
        for k, v in s["q"].items():
            a.q[k] = v
        a.head = s["head"]
        return a


_HANDLERS = {"sess": "_h_sess", "end": "_h_end", "play": "_h_play", "seg": "_h_seg", "fin": "_h_fin", "gap": "_h_gap", "clock": "_h_clock", "torn": "_h_torn"}
for _k in ("pause", "resume", "seek", "vol", "mode", "fav", "sleep", "queue", "fx", "lyrics", "ui", "recover"):
    _HANDLERS[_k] = "_h_simple"


# ---------------------------------------------------------------- the part of "now" that is not in a record yet
def make_overlay(agg, live, now_ms, z=0):
    """live = {"sid": current session id, "seg": {"a","d","z"} or None, "plays": [{"path","t","z","dur","listened","maxpos"}]}  (what the recorder has in hand right now).
    Returns {"days": {key: {"l","o","h","oh","sf"}}, "songs": {key: {path: row}}, "bout": open-bout-length}."""
    ov = {"days": {}, "songs": {}}
    live = live or {}

    def dd(di):
        return ov["days"].setdefault(day_key(di), {"l": 0.0, "o": 0.0, "h": [0.0] * 24, "oh": [0.0] * 24, "sf": {}})

    seg = live.get("seg")
    if seg and seg.get("d", 0) > 0:
        a = int(seg["a"])
        for di, hh, s in split_hours(a, a + int(round(seg["d"] * 1000)), seg.get("z", z)):
            x = dd(di)
            x["l"] += s
            x["h"][hh] += s
            if seg.get("path"):
                ov["songs"].setdefault(day_key(di), {}).setdefault(seg["path"], _srow())[5] += s
    for pl in live.get("plays", ()):
        lf, sp, _done, _skip = classify(pl["listened"], pl.get("dur", 0), "inflight", pl.get("maxpos", 0))
        row = ov["songs"].setdefault(day_key(day_index(pl["t"], pl["z"])), {}).setdefault(pl["path"], _srow())
        row[1] += lf
        row[2] += sp
    for sid, s in agg.so.items():
        b = now_ms if sid == live.get("sid") else s["last"]
        for di, hh, sec in split_hours(s["a"], max(b, s["a"]), s["z"]):
            x = dd(di)
            x["o"] += sec
            x["oh"][hh] += sec
            x["sf"][s["surf"]] = x["sf"].get(s["surf"], 0.0) + sec
    return ov


# ---------------------------------------------------------------- questions
def today_index(now_ms, z=0):
    return day_index(now_ms, z)


def span(name, today, first):
    """(first day number, last day number) of a named period. names: today yesterday 7d 30d 90d month year all"""
    if name == "today":
        return today, today
    if name == "yesterday":
        return today - 1, today - 1
    if name in ("7d", "week"):
        return today - 6, today
    if name in ("30d", "month30"):
        return today - 29, today
    if name == "90d":
        return today - 89, today
    if name == "month":
        d = _dt.date.fromordinal(_EPOCH + today)
        return today - (d.day - 1), today
    if name == "year":
        d = _dt.date.fromordinal(_EPOCH + today)
        return today - (d.timetuple().tm_yday - 1), today
    return (first if first is not None else today), today


def _get(agg, ov, i):
    k = day_key(i)
    return agg.days.get(k), (ov["days"].get(k) if ov else None)


def totals(agg, a, b, ov=None):
    """Sums over the calendar days a..b (day numbers, inclusive)."""
    r = {"listen": 0.0, "open": 0.0, "starts": 0, "lastfm": 0, "spotify": 0, "completed": 0, "skipped": 0, "sessions": 0, "hours": [0.0] * 24, "ohours": [0.0] * 24,
         "events": {}, "active_days": 0, "days": max(0, b - a + 1), "songs": 0, "artists": 0, "surfaces": {}}
    songs, arts = set(), set()
    for i in range(a, b + 1):
        d, o = _get(agg, ov, i)
        k = day_key(i)
        if d is None and o is None:
            continue
        lis = (d["l"] if d else 0.0) + (o["l"] if o else 0.0)
        r["listen"] += lis
        r["open"] += (d["o"] if d else 0.0) + (o["o"] if o else 0.0)
        if lis >= ACTIVE_DAY_S:
            r["active_days"] += 1
        for src in (d, o):
            if src:
                for h in range(24):
                    r["hours"][h] += src["h"][h]
                    r["ohours"][h] += src["oh"][h]
                for s, v in src["sf"].items():
                    r["surfaces"][s] = r["surfaces"].get(s, 0.0) + v
        if d:
            r["sessions"] += d["ss"]
            for e, n in d["e"].items():
                r["events"][e] = r["events"].get(e, 0) + n
        rows = [x["s"] for x in (d,) if x] + ([ov["songs"][k]] if ov and k in ov["songs"] else [])
        for srows in rows:
            for path, v in srows.items():
                r["starts"] += v[0]
                r["lastfm"] += v[1]
                r["spotify"] += v[2]
                r["completed"] += v[3]
                r["skipped"] += v[4]
                if v[0] or v[5] > 0:
                    songs.add(path)
                    arts.add(agg.artist_of(path) or "?")
    r["songs"], r["artists"] = len(songs), len(arts)
    return r


def series(agg, a, b, ov=None):
    """One dict per calendar day a..b (zeros for quiet days): day, key, listen, open, starts, plays (Last.fm rule), spotify."""
    out = []
    for i in range(a, b + 1):
        d, o = _get(agg, ov, i)
        k = day_key(i)
        row = {"i": i, "key": k, "wd": weekday(i), "listen": 0.0, "open": 0.0, "starts": 0, "plays": 0, "spotify": 0, "top": ""}
        if d or o:
            row["listen"] = (d["l"] if d else 0.0) + (o["l"] if o else 0.0)
            row["open"] = (d["o"] if d else 0.0) + (o["o"] if o else 0.0)
            sr = dict(d["s"]) if d else {}
            for path, v in ((ov or {}).get("songs", {}).get(k, {})).items():
                cur = sr.get(path)
                sr[path] = [x + y for x, y in zip(cur, v)] if cur else list(v)
            for v in sr.values():
                row["starts"] += v[0]
                row["plays"] += v[1]
                row["spotify"] += v[2]
            if sr:
                top = max(sr.items(), key=lambda kv: (kv[1][1], kv[1][5], kv[1][0]))
                row["top"] = top[0] if (top[1][1] or top[1][5] > 0) else ""
        out.append(row)
    return out


def rank(agg, a, b, by="plays", level="song", rule="lastfm", n=20, ov=None):
    """Top list over the days a..b. level: song | artist | folder.  by: plays | time.  rule: lastfm | spotify | starts | finished (what 'plays' counts).
    Each row: name, title, artist, plays, starts, time, completed, skipped, completion (0..1), skip_rate (0..1), last (ms), songs (artist/folder level), path (song level)."""
    acc = {}
    at = _RULE_AT.get(rule, 1)
    for i in range(a, b + 1):
        d, o = _get(agg, ov, i)
        k = day_key(i)
        for srows in ([d["s"]] if d else []) + ([ov["songs"][k]] if ov and k in ov["songs"] else []):
            for path, v in srows.items():
                x = acc.setdefault(path, _srow())
                for j in range(6):
                    x[j] += v[j]
    groups = {}
    for path, v in acc.items():
        if not v[0] and v[5] <= 0 and not v[1]:
            continue
        m = agg.songs.get(path) or {}
        if level == "artist":
            name = m.get("artist") or "?"
        elif level == "folder":
            name = m.get("folder") or "?"
        else:
            name = path
        g = groups.setdefault(name, {"name": name, "title": "", "artist": "", "plays": 0, "starts": 0, "time": 0.0, "completed": 0, "skipped": 0, "last": 0, "songs": 0, "path": path if level == "song" else ""})
        g["plays"] += v[at] if at else v[0]
        g["starts"] += v[0]
        g["time"] += v[5]
        g["completed"] += v[3]
        g["skipped"] += v[4]
        g["songs"] += 1
        g["last"] = max(g["last"], int(m.get("last", 0)))
        if level == "song":
            g["title"], g["artist"] = agg.title_of(path), m.get("artist", "")
        else:
            g["title"] = name
    rows = [g for g in groups.values() if (g["time"] > 0 if by == "time" else g["plays"] > 0)]     # a song that was only heard for a moment has no place in a 'plays' ranking
    for g in rows:
        g["completion"] = (g["completed"] / g["starts"]) if g["starts"] else 0.0
        g["skip_rate"] = (g["skipped"] / g["starts"]) if g["starts"] else 0.0
    if by == "time":
        rows.sort(key=lambda g: (-g["time"], -g["plays"], g["name"]))
    else:
        rows.sort(key=lambda g: (-g["plays"], -g["time"], g["name"]))
    return rows[:n] if n else rows


def heat(agg, a, b, ov=None):
    """{"m": 7x24 listening seconds (Monday first), "n": calendar days of each weekday inside a..b}"""
    m = [[0.0] * 24 for _ in range(7)]
    n = [0] * 7
    for i in range(a, b + 1):
        w = weekday(i)
        n[w] += 1
        d, o = _get(agg, ov, i)
        for src in (d, o):
            if src:
                for h in range(24):
                    m[w][h] += src["h"][h]
    return {"m": m, "n": n}


def streaks(agg, today, ov=None):
    """{"current","longest","longest_from","longest_to","active_days"}: a streak is a run of days with at least ACTIVE_DAY_S of listening."""
    act = []
    for k, d in agg.days.items():
        i = key_index(k)
        o = ov["days"].get(k) if ov else None
        if d["l"] + (o["l"] if o else 0.0) >= ACTIVE_DAY_S:
            act.append(i)
    if ov:
        for k, o in ov["days"].items():
            if k not in agg.days and o["l"] >= ACTIVE_DAY_S:
                act.append(key_index(k))
    act = sorted(set(act))
    best, run, start, bf, bt = 0, 0, None, None, None
    prev = None
    for i in act:
        if prev is not None and i == prev + 1:
            run += 1
        else:
            run, start = 1, i
        if run > best:
            best, bf, bt = run, start, i
        prev = i
    s = set(act)
    cur = 0
    i = today if today in s else today - 1
    while i in s:
        cur += 1
        i -= 1
    return {"current": cur, "longest": best, "longest_from": day_key(bf) if bf is not None else "", "longest_to": day_key(bt) if bt is not None else "", "active_days": len(act)}


def records(agg, today, ov=None):
    """The personal bests, each with its date."""
    r = {"best_day": ("", 0.0), "most_plays_day": ("", 0), "most_repeats": ("", "", 0), "longest_bout": (0, 0.0, 0), "longest_session": (0, 0.0, "", 0), "most_open_day": ("", 0.0)}
    for k, d in agg.days.items():
        o = ov["days"].get(k) if ov else None
        lis = d["l"] + (o["l"] if o else 0.0)
        op = d["o"] + (o["o"] if o else 0.0)
        if lis > r["best_day"][1]:
            r["best_day"] = (k, lis)
        if op > r["most_open_day"][1]:
            r["most_open_day"] = (k, op)
        st = sum(v[0] for v in d["s"].values())
        if st > r["most_plays_day"][1]:
            r["most_plays_day"] = (k, st)
        for path, v in d["s"].items():
            if v[0] > r["most_repeats"][2]:
                r["most_repeats"] = (k, path, v[0])
    bl = list(agg.bouts) + ([[agg.bout["a"], agg.bout["b"], agg.bout["listen"], agg.bout["plays"], agg.bout["z"]]] if agg.bout else [])
    for a, b, lis, pl, z in bl:
        if lis > r["longest_bout"][1]:
            r["longest_bout"] = (a, lis, pl)
    for a, b, surf, lis, pl, why, z in agg.sessions:
        if (b - a) / 1000.0 > r["longest_session"][1]:
            r["longest_session"] = (a, (b - a) / 1000.0, surf, pl)
    r["streak"] = streaks(agg, today, ov)
    return r


def quality(agg, ov=None):
    """How trustworthy the numbers are: how much was measured live, how much inferred across gaps, how many gaps / clock jumps / recoveries."""
    q = dict(agg.q)
    tot = q["live_s"] + q["inferred_s"]
    q["live_share"] = (q["live_s"] / tot) if tot else 1.0
    q["inferred_share"] = (q["inferred_s"] / tot) if tot else 0.0
    q["open_sessions"] = len(agg.so)
    q["open_plays"] = len(agg.pl)
    return q


def overview(agg, now_ms, z=0, ov=None):
    """Everything the first screen needs: today / yesterday / week / month / all-time totals, streaks, ratios and the time-of-day shares."""
    t = today_index(now_ms, z)
    first = agg.first_day()
    out = {"now": now_ms, "z": z, "today": t, "first": day_key(first) if first is not None else ""}
    for name in ("today", "yesterday", "7d", "30d", "month", "year", "all"):
        a, b = span(name, t, first)
        out[name] = totals(agg, a, b, ov)
    allt = out["all"]
    out["streak"] = streaks(agg, t, ov)
    hrs = allt["hours"]
    tot = sum(hrs) or 1.0
    out["shares"] = {"night": sum(hrs[0:5]) / tot, "morning": sum(hrs[5:12]) / tot, "afternoon": sum(hrs[12:18]) / tot, "evening": sum(hrs[18:24]) / tot}
    out["peak_hour"] = max(range(24), key=lambda h: hrs[h]) if sum(hrs) > 0 else None
    wd = [0.0] * 7
    for i in range(first if first is not None else t, t + 1):
        d, o = _get(agg, ov, i)
        wd[weekday(i)] += (d["l"] if d else 0.0) + (o["l"] if o else 0.0)
    out["weekday_s"] = wd
    out["peak_weekday"] = max(range(7), key=lambda w: wd[w]) if sum(wd) > 0 else None
    ad = allt["active_days"]
    out["avg_active_day"] = (allt["listen"] / ad) if ad else 0.0
    out["avg_calendar_day"] = (allt["listen"] / allt["days"]) if allt["days"] else 0.0
    out["completion"] = (allt["completed"] / allt["starts"]) if allt["starts"] else 0.0
    out["skip_rate"] = (allt["skipped"] / allt["starts"]) if allt["starts"] else 0.0
    out["repeat_ratio"] = (1 - allt["songs"] / allt["starts"]) if allt["starts"] else 0.0
    return out


def song_detail(agg, path, today, ov=None):
    """One song: totals, first/last, per-day listening of the last 30 days."""
    first = agg.first_day()
    a, b = (first if first is not None else today), today
    rows = rank(agg, a, b, level="song", n=0, ov=ov)
    me = next((r for r in rows if r["name"] == path), None)
    per = []
    for i in range(today - 29, today + 1):
        d, o = _get(agg, ov, i)
        v = ((d or {}).get("s", {}) or {}).get(path)
        per.append((v[5] if v else 0.0) + ((ov or {}).get("songs", {}).get(day_key(i), {}).get(path, [0] * 6)[5]))
    m = agg.songs.get(path) or {}
    rank_by_plays = 1 + sum(1 for r in rows if (r["plays"], r["time"]) > ((me or {}).get("plays", 0), (me or {}).get("time", 0)))
    return {"row": me, "meta": m, "per_day": per, "rank": rank_by_plays if me else 0, "of": len(rows)}


def activity_by_kind(agg, a, b):
    """{event kind: count} over the days a..b (every kind the recorder wrote: play, pause, seek, vol, fav, ...)."""
    r = {}
    for i in range(a, b + 1):
        d = agg.days.get(day_key(i))
        if d:
            for e, n in d["e"].items():
                r[e] = r.get(e, 0) + n
    return r


# END-OF-FILE rofpalys_analytics_calc.py

