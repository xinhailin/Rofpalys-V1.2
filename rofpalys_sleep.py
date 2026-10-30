#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - sleep timer + time zones (no UI, no engine: only time maths)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""While the timer runs, the song that is playing repeats; when the time is reached playback stops.

Two ways to set it:
  * a duration            start_duration(2 * 3600)   -> "02.00" = 2 hours
  * a clock time          start_until(0, 0, "id-wib") -> until 00:00 in Western Indonesia Time (next time that clock shows it)
Time zones come from the system tz database when Python can find it, and from a built-in table (with the EU / US / Australia
daylight-saving rules) when it cannot - which is the case on a bare Termux."""
import datetime as dt
import re
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:                                           # Python < 3.9
    ZoneInfo = None

# key, label, short name, tz database name, standard offset in minutes, daylight-saving rule
ZONES = [
    ("local", "Device time", "local", None, 0, None),
    ("id-wib", "Indonesia - WIB (Jakarta, Sumatra, Java)", "WIB", "Asia/Jakarta", 420, None),
    ("id-wita", "Indonesia - WITA (Bali, Makassar)", "WITA", "Asia/Makassar", 480, None),
    ("id-wit", "Indonesia - WIT (Papua, Maluku)", "WIT", "Asia/Jayapura", 540, None),
    ("my", "Malaysia (Kuala Lumpur)", "MYT", "Asia/Kuala_Lumpur", 480, None),
    ("sg", "Singapore", "SGT", "Asia/Singapore", 480, None),
    ("uk", "United Kingdom (London)", "UK", "Europe/London", 0, "eu"),
    ("de", "Germany (Berlin)", "CET", "Europe/Berlin", 60, "eu"),
    ("fr", "France (Paris)", "CET", "Europe/Paris", 60, "eu"),
    ("nl", "Netherlands (Amsterdam)", "CET", "Europe/Amsterdam", 60, "eu"),
    ("ru-msk", "Russia - Moscow", "MSK", "Europe/Moscow", 180, None),
    ("ru-ekb", "Russia - Yekaterinburg", "YEKT", "Asia/Yekaterinburg", 300, None),
    ("ru-vvo", "Russia - Vladivostok", "VLAT", "Asia/Vladivostok", 600, None),
    ("cn", "China (Beijing)", "CST", "Asia/Shanghai", 480, None),
    ("jp", "Japan (Tokyo)", "JST", "Asia/Tokyo", 540, None),
    ("kr", "South Korea (Seoul)", "KST", "Asia/Seoul", 540, None),
    ("in", "India", "IST", "Asia/Kolkata", 330, None),
    ("ae", "United Arab Emirates (Dubai)", "GST", "Asia/Dubai", 240, None),
    ("sa", "Saudi Arabia (Riyadh)", "AST", "Asia/Riyadh", 180, None),
    ("tr", "Turkey (Istanbul)", "TRT", "Europe/Istanbul", 180, None),
    ("eg", "Egypt (Cairo)", "EET", "Africa/Cairo", 120, None),
    ("au", "Australia (Sydney)", "AEST", "Australia/Sydney", 600, "au"),
    ("us-ny", "USA - New York", "ET", "America/New_York", -300, "us"),
    ("us-la", "USA - Los Angeles", "PT", "America/Los_Angeles", -480, "us"),
    ("br", "Brazil (Sao Paulo)", "BRT", "America/Sao_Paulo", -180, None),
]
_BY_KEY = {z[0]: z for z in ZONES}
PRESET_MINUTES = (0, 15, 30, 45, 60, 120)                      # the terminal UI cycles through these (0 = off)

# ------------------------------------------------------------------ timer state (one timer per program)
end_ts = 0.0                                                   # unix time when playback must stop (0 = no timer)
start_ts = 0.0
kind = ""                                                      # "duration" | "until"
zone_key = "local"
finish_song = False                                            # True: when the time is up, let the current song end first
text = ""                                                      # short description for the UI
fired = False


def zone(key):
    return _BY_KEY.get(key) or _BY_KEY["local"]


# ------------------------------------------------------------------ time zones
def _nth_sunday(year, month, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)              # first Sunday
    return d + dt.timedelta(weeks=n - 1)


def _last_sunday(year, month):
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def _dst_active(utc, std_min, rule):
    """utc: aware datetime in UTC. Fallback daylight-saving rules for when no tz database is available."""
    y = utc.year
    u = utc.replace(tzinfo=None)

    def at(d, hour, off_min):                                  # local wall clock `hour` on date d -> naive UTC
        return dt.datetime(d.year, d.month, d.day, hour) - dt.timedelta(minutes=off_min)
    if rule == "eu":
        return at(_last_sunday(y, 3), 1, 0) <= u < at(_last_sunday(y, 10), 1, 0)
    if rule == "us":
        return at(_nth_sunday(y, 3, 2), 2, std_min) <= u < at(_nth_sunday(y, 11, 1), 2, std_min + 60)
    if rule == "au":                                           # southern hemisphere: DST spans New Year
        return u >= at(_nth_sunday(y, 10, 1), 2, std_min) or u < at(_nth_sunday(y, 4, 1), 3, std_min + 60)
    return False


def offset_minutes(key, ts=None):
    """UTC offset of the zone at a moment (daylight saving included)."""
    ts = time.time() if ts is None else ts
    utc = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
    _, _, _, name, std, rule = zone(key)
    if key == "local" or name is None:
        off = dt.datetime.fromtimestamp(ts).astimezone().utcoffset()
        return int(off.total_seconds() // 60) if off is not None else 0
    if ZoneInfo is not None:
        try:
            return int(utc.astimezone(ZoneInfo(name)).utcoffset().total_seconds() // 60)
        except Exception:
            pass
    return std + (60 if _dst_active(utc, std, rule) else 0)


def wall_clock(key, ts=None):
    """Naive datetime showing what a clock in that zone shows at the moment."""
    ts = time.time() if ts is None else ts
    utc = dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None)
    return utc + dt.timedelta(minutes=offset_minutes(key, ts))


def next_occurrence(key, hh, mm, ts=None):
    """Unix time of the next moment a clock in that zone shows hh:mm (today if still ahead, otherwise tomorrow)."""
    ts = time.time() if ts is None else ts
    wall = wall_clock(key, ts)
    cand = wall.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cand <= wall:
        cand += dt.timedelta(days=1)
    guess = ts
    for _ in range(3):                                         # the offset can differ at the target moment (daylight saving change)
        off = offset_minutes(key, guess)
        guess = (cand - dt.timedelta(minutes=off) - dt.datetime(1970, 1, 1)).total_seconds()
    return guess


def zone_label(key):
    z = zone(key)
    off = offset_minutes(key)
    sign = "+" if off >= 0 else "-"
    return "%s  (UTC%s%02d:%02d)" % (z[1], sign, abs(off) // 60, abs(off) % 60)


# ------------------------------------------------------------------ parsing what the user types
def parse_clock(s):
    """'00:00', '0.00', '2100', '21' -> (hour, minute). Raises ValueError."""
    s = s.strip().replace(" ", "")
    m = re.match(r"^(\d{1,2})[.:,h](\d{2})$", s) or re.match(r"^(\d{1,2})(\d{2})$", s) or re.match(r"^(\d{1,2})()$", s)
    if not m:
        raise ValueError("clock")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mi > 59:
        raise ValueError("clock")
    return h, mi


def parse_duration(s):
    """'02.00' -> 2 h; '2:30' -> 2 h 30 min; '45' -> 45 min; '90m'; '1h30'; '2h'. Returns seconds. Raises ValueError."""
    s = s.strip().lower().replace(" ", "")
    m = re.match(r"^(\d{1,2})[.:](\d{2})$", s)
    if m:
        sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60
    else:
        m = re.match(r"^(?:(\d+)(?:jam|hours?|hrs?|h|j))?(?:(\d+)(?:minutes?|menit|mins?|m)?)?$", s)     # 2h | 1h30 | 90m | 45
        if m and (m.group(1) or m.group(2)):
            sec = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
        else:
            raise ValueError("duration")
    if sec <= 0 or sec > 24 * 3600:
        raise ValueError("range")
    return sec


# ------------------------------------------------------------------ the timer
def fmt_left(sec):
    sec = max(0, int(sec + 0.5))
    return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


def start_duration(seconds, finish=False, now=None):
    global end_ts, start_ts, kind, finish_song, text, fired
    now = time.time() if now is None else now
    end_ts, start_ts, kind, finish_song, fired = now + seconds, now, "duration", bool(finish), False
    text = "%s" % fmt_left(seconds)
    return end_ts


def start_until(hh, mm, key="local", finish=False, now=None):
    global end_ts, start_ts, kind, finish_song, text, fired, zone_key
    now = time.time() if now is None else now
    end_ts = next_occurrence(key, hh, mm, now)
    start_ts, kind, finish_song, fired, zone_key = now, "until", bool(finish), False, key
    w0, w1 = wall_clock(key, now), wall_clock(key, end_ts)
    text = "%s -> %02d:%02d %s" % (w0.strftime("%H:%M"), hh, mm, zone(key)[2])
    return end_ts


def cancel():
    global end_ts, kind, fired
    end_ts, kind, fired = 0.0, "", False


def active():
    return end_ts > 0 and not fired


def remaining():
    return max(0.0, end_ts - time.time()) if active() else 0.0


def due():
    return active() and time.time() >= end_ts


def fire():
    """The time is up: the engine calls this when it has stopped the music."""
    global fired, end_ts
    fired, end_ts = True, 0.0


def cycle_preset():
    """Terminal UI: off -> 15 -> 30 -> 45 -> 60 -> 120 -> off. Returns the minutes now set (0 = off)."""
    cur = round(remaining() / 60.0) if active() else 0
    nxt = next((m for m in PRESET_MINUTES if m > cur), 0) if cur < PRESET_MINUTES[-1] else 0
    if nxt:
        start_duration(nxt * 60)
    else:
        cancel()
    return nxt

# END-OF-FILE rofpalys_sleep.py

