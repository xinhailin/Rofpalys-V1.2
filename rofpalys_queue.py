#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - play queue ("Up next"), play history ("previous" goes back to what you really heard) and smart shuffle
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""No UI, no engine. The engine asks this module what to play next and tells it what was played."""
import random

upnext = []                 # songs you queued: played before anything else (except in "repeat one")
history = []                # songs already played, most recent last (capped)
_bag, _bag_key = [], None   # smart shuffle: songs not yet heard in the current round
HISTORY_MAX = 300


def add(path, front=False):
    """Queue a song at the end ('Add to queue') or at the front ('Play next')."""
    if not path:
        return
    if front:
        upnext.insert(0, path)
    else:
        upnext.append(path)


def add_many(paths, front=False):
    for p in (reversed(paths) if front else paths):
        add(p, front)


def remove(index):
    if 0 <= index < len(upnext):
        return upnext.pop(index)
    return None


def move(index, delta):
    j = index + delta
    if 0 <= index < len(upnext) and 0 <= j < len(upnext):
        upnext[index], upnext[j] = upnext[j], upnext[index]
        return j
    return index


def clear():
    del upnext[:]


def pop_next():
    return upnext.pop(0) if upnext else None


def push_history(path):
    if path and (not history or history[-1] != path):
        history.append(path)
        del history[:-HISTORY_MAX]


def pop_previous(current):
    """The song played before `current` (None if there is none): this is what the 'previous' button should go back to."""
    while history:
        p = history.pop()
        if p != current:
            return p
    return None


def shuffle_next(candidates, current=None):
    """Smart shuffle: every song is played once before any song repeats, and never the same song twice in a row."""
    global _bag, _bag_key
    if not candidates:
        return None
    key = (len(candidates), candidates[0], candidates[-1])
    if key != _bag_key or not _bag:
        _bag_key = key
        _bag = [p for p in candidates if p != current] or list(candidates)
        random.shuffle(_bag)
    return _bag.pop()


def reset():
    clear()
    del history[:]
    global _bag, _bag_key
    _bag, _bag_key = [], None


# END-OF-FILE rofpalys_queue.py

