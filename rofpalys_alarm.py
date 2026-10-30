#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - wake-up alarm: at a clock time (in a chosen time zone) a song or playlist starts, softly, then gets louder
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""No UI, no engine. The player (GUI, terminal UI or `rofpalys daemon`) starts the watcher; it calls back when an alarm is due.
The player has to be running at that time (on a phone: keep Termux alive with `termux-wake-lock`)."""
import json
import os
import threading
import time
import uuid

import rofpalys_library as lib
import rofpalys_sleep as SL

FILE = os.path.join(lib.CONFIG_DIR, "alarms.json")
GRACE = 300                           # an alarm that is more than 5 minutes late (the player was closed) is skipped, not played


def _read():
    try:
        with open(FILE, encoding="utf-8") as f:
            return [a for a in json.load(f).get("alarms", []) if isinstance(a, dict) and a.get("id")]
    except (OSError, ValueError, AttributeError):
        return []


def _write(items):
    try:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        with open(FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"alarms": items}, f)
        os.replace(FILE + ".tmp", FILE)
    except OSError:
        pass


def all_alarms():
    return _read()


def next_ts(a, now=None):
    """Unix time of the next ring. days = [] means once; otherwise weekdays 0=Monday ... 6=Sunday."""
    now = time.time() if now is None else now
    days = a.get("days") or []
    ts = SL.next_occurrence(a.get("zone", "local"), a["hh"], a["mm"], now)
    for _ in range(9):
        if not days or SL.wall_clock(a.get("zone", "local"), ts).weekday() in days:
            return ts
        ts = SL.next_occurrence(a.get("zone", "local"), a["hh"], a["mm"], ts + 60)
    return ts


def add(hh, mm, zone="local", target=None, days=(), ramp=60):
    """target: {'type': 'song', 'ref': path} | {'type': 'playlist', 'ref': playlist id}. Returns the alarm id."""
    items = _read()
    a = {"id": "al" + uuid.uuid4().hex[:6], "hh": int(hh), "mm": int(mm), "zone": zone, "days": sorted(set(days)), "target": target or {}, "enabled": True, "ramp": int(ramp)}
    a["next"] = next_ts(a)
    items.append(a)
    _write(items)
    return a["id"]


def remove(aid):
    items = _read()
    n = len(items)
    _write([a for a in items if a["id"] != aid])
    return len(items) > n


def set_enabled(aid, flag):
    items = _read()
    for a in items:
        if a["id"] == aid:
            a["enabled"] = bool(flag)
            if flag:
                a["next"] = next_ts(a)
    _write(items)


def describe(a):
    d = ("every day" if len(a.get("days") or []) == 7 else ",".join("MTWTFSS"[i] for i in a["days"])) if a.get("days") else "once"
    tgt = a.get("target", {})
    what = os.path.splitext(os.path.basename(tgt.get("ref", "")))[0] if tgt.get("type") == "song" else "playlist"
    return "%02d:%02d %s  %s  -> %s%s" % (a["hh"], a["mm"], SL.zone(a.get("zone", "local"))[2], d, what, "" if a.get("enabled") else "  (off)")


def check(callback, now=None):
    """Fire every alarm that is due. Returns the list of alarms that rang."""
    now = time.time() if now is None else now
    items, rang, changed = _read(), [], False
    for a in items:
        if not a.get("enabled"):
            continue
        nxt = a.get("next", 0)
        if not nxt:
            a["next"], changed = next_ts(a, now), True
        elif now >= nxt:
            if now - nxt <= GRACE:
                rang.append(dict(a))
            if a.get("days"):
                a["next"] = next_ts(a, max(now, nxt) + 61)
            else:
                a["enabled"] = False
            changed = True
    if changed:
        _write(items)
    for a in rang:
        try:
            callback(a)
        except Exception:
            pass
    return rang


_watcher = {"thread": None, "stop": False}


def start(callback):
    """Watch the clock in a background thread (idempotent)."""
    if _watcher["thread"] is not None and _watcher["thread"].is_alive():
        return
    _watcher["stop"] = False

    def loop():
        while not _watcher["stop"]:
            check(callback)
            time.sleep(2.0)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    _watcher["thread"] = t


def stop():
    _watcher["stop"] = True


# END-OF-FILE rofpalys_alarm.py

