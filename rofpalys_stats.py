#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - listening statistics (plays, minutes per day, streak, top songs / artists)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The engine reports every song start and every second listened; this module keeps the numbers and writes them to stats.json."""
import datetime as dt
import json
import os
import time

import rofpalys_library as lib
import rofpalys_lyrics as LY

STATS_FILE = os.path.join(lib.CONFIG_DIR, "stats.json")
stats = {}              # path -> {"plays": n, "sec": seconds, "ts": last start}   (same shape the GUI always used)
days = {}               # "2026-10-08" -> seconds listened that day
total_sec = 0.0
_dirty, _last_save = False, 0.0


def _today():
    return time.strftime("%Y-%m-%d")


def load(legacy_stats=None, legacy_total=0):
    """Read stats.json. `legacy_*`: numbers the old GUI kept in gui.json - they are taken over once."""
    global total_sec, _dirty
    stats.clear()
    days.clear()
    total_sec = 0.0
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        stats.update({p: v for p, v in d.get("songs", {}).items() if isinstance(v, dict)})
        days.update({k: float(v) for k, v in d.get("days", {}).items()})
        total_sec = float(d.get("total_sec", 0))
    except (OSError, ValueError, AttributeError):
        if legacy_stats:
            stats.update({p: v for p, v in legacy_stats.items() if isinstance(v, dict)})
            total_sec = float(legacy_total or 0)
            _dirty = True
            save(force=True)


def save(force=False):
    global _dirty, _last_save
    if not (_dirty or force):
        return
    try:
        os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
        with open(STATS_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"songs": stats, "days": days, "total_sec": total_sec}, f)
        os.replace(STATS_FILE + ".tmp", STATS_FILE)
        _dirty, _last_save = False, time.time()
    except OSError:
        pass


def played(path):
    global _dirty
    st = stats.setdefault(path, {"plays": 0, "sec": 0})
    st["plays"] = st.get("plays", 0) + 1
    st["ts"] = time.time()
    _dirty = True


def tick(path, seconds):
    """`seconds` of real listening (not paused) to `path`."""
    global total_sec, _dirty
    if seconds <= 0 or not path:
        return
    st = stats.setdefault(path, {"plays": 0, "sec": 0})
    st["sec"] = st.get("sec", 0) + seconds
    total_sec += seconds
    d = _today()
    days[d] = days.get(d, 0.0) + seconds
    _dirty = True
    if time.time() - _last_save > 20:
        save()


def reset():
    global total_sec, _dirty
    stats.clear()
    days.clear()
    total_sec, _dirty = 0.0, False
    try:
        os.remove(STATS_FILE)
    except OSError:
        pass


def streak(today=None):
    """Days in a row (ending today, or yesterday if you have not listened yet today) with some listening."""
    d = dt.date.fromisoformat(today) if today else dt.date.today()
    if days.get(d.isoformat(), 0) <= 0:
        d -= dt.timedelta(days=1)
    n = 0
    while days.get(d.isoformat(), 0) > 0:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def last_days(n=14, today=None):
    d = dt.date.fromisoformat(today) if today else dt.date.today()
    return [((d - dt.timedelta(days=i)).isoformat(), days.get((d - dt.timedelta(days=i)).isoformat(), 0.0)) for i in range(n - 1, -1, -1)]


def summary(today=None):
    top = sorted(((p, v) for p, v in stats.items() if v.get("plays", 0) > 0), key=lambda x: (-x[1].get("sec", 0), -x[1].get("plays", 0)))
    artists = {}
    for p, v in stats.items():
        a = LY.guess(p)[0] or "?"
        e = artists.setdefault(a, [0.0, 0])
        e[0] += v.get("sec", 0)
        e[1] += v.get("plays", 0)
    top_artists = sorted(((a, e[0], e[1]) for a, e in artists.items() if a != "?" and e[1] > 0), key=lambda x: -x[1])
    ld = last_days(14, today)
    best = max(ld, key=lambda x: x[1]) if ld else ("", 0.0)
    return {"total_sec": total_sec, "songs": len([1 for v in stats.values() if v.get("plays", 0) > 0]), "plays": sum(v.get("plays", 0) for v in stats.values()),
            "streak": streak(today), "last_days": ld, "best_day": best, "top_songs": top[:10], "top_artists": top_artists[:8],
            "week_sec": sum(s for _, s in ld[-7:])}


# END-OF-FILE rofpalys_stats.py

