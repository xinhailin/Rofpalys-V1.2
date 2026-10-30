#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - your own playlists (create, rename, add/remove/move songs, import and export .m3u)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""No UI. Every change re-reads the file first, so two windows or the command line can never overwrite each other's changes."""
import json
import os
import time
import uuid

import rofpalys_library as lib

FILE = os.path.join(lib.CONFIG_DIR, "playlists.json")


def _read():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
        pls = d.get("playlists", [])
        return [p for p in pls if isinstance(p, dict) and p.get("id") and isinstance(p.get("paths"), list)]
    except (OSError, ValueError, AttributeError):
        return []


def _write(pls):
    try:
        os.makedirs(os.path.dirname(FILE), exist_ok=True)
        with open(FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"playlists": pls}, f, ensure_ascii=False)
        os.replace(FILE + ".tmp", FILE)
    except OSError:
        pass


def _mutate(fn):
    pls = _read()
    res = fn(pls)
    _write(pls)
    return res


def all_playlists():
    return _read()


def get(pid):
    return next((p for p in _read() if p["id"] == pid), None)


def unique_name(base, pls=None):
    names = {p["name"].lower() for p in (pls if pls is not None else _read())}
    base = (base or "New playlist").strip()[:60] or "New playlist"
    name, n = base, 2
    while name.lower() in names:
        name = "%s (%d)" % (base, n)
        n += 1
    return name


def create(name, paths=()):
    def f(pls):
        pid = "pl" + uuid.uuid4().hex[:8]
        pls.append({"id": pid, "name": unique_name(name, pls), "paths": list(dict.fromkeys(paths)), "created": int(time.time())})
        return pid
    return _mutate(f)


def rename(pid, name):
    def f(pls):
        for p in pls:
            if p["id"] == pid:
                p["name"] = unique_name(name, [q for q in pls if q["id"] != pid])
                return True
        return False
    return _mutate(f)


def delete(pid):
    def f(pls):
        n = len(pls)
        pls[:] = [p for p in pls if p["id"] != pid]
        return len(pls) < n
    return _mutate(f)


def add(pid, paths):
    """Adds songs at the end (a song is only in a playlist once). Returns how many were really added."""
    def f(pls):
        for p in pls:
            if p["id"] == pid:
                have = set(p["paths"])
                new = [x for x in dict.fromkeys(paths) if x not in have]
                p["paths"].extend(new)
                return len(new)
        return 0
    return _mutate(f)


def remove(pid, path):
    def f(pls):
        for p in pls:
            if p["id"] == pid and path in p["paths"]:
                p["paths"].remove(path)
                return True
        return False
    return _mutate(f)


def move(pid, path, delta):
    def f(pls):
        for p in pls:
            if p["id"] == pid and path in p["paths"]:
                i = p["paths"].index(path)
                j = max(0, min(len(p["paths"]) - 1, i + delta))
                p["paths"].insert(j, p["paths"].pop(i))
                return j
        return -1
    return _mutate(f)


def export_m3u(pid, dest):
    p = get(pid)
    if not p:
        return False
    try:
        with open(dest, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n#PLAYLIST:%s\n" % p["name"])
            for s in p["paths"]:
                f.write("#EXTINF:-1,%s\n%s\n" % (os.path.splitext(os.path.basename(s))[0], s))
        return True
    except OSError:
        return False


def import_m3u(src, name=None):
    """Creates a playlist from an .m3u/.m3u8 file. Returns (playlist id, number of songs) or (None, 0)."""
    paths = lib.read_m3u(src)
    if not paths:
        return None, 0
    return create(name or os.path.splitext(os.path.basename(src))[0], paths), len(paths)


# ------------------------------------------------------------------ more ways to fill and manage a playlist
def add_group(pid, paths):
    """Add a whole list of songs (a folder, an artist, search results, the queue ...). Returns how many were new."""
    return add(pid, list(paths))


def create_from(name, paths):
    """New playlist that starts with these songs (duplicates removed, order kept). Returns its id."""
    return create(name, list(paths))


def duplicate(pid, name=None):
    """A copy of a playlist under a new name ('Gym (2)'). Returns the new id or None."""
    src = get(pid)
    if not src:
        return None
    return create(name or src["name"], src["paths"])


def merge(target_pid, source_pid):
    """Put the songs of `source` at the end of `target` (the source stays). Returns how many were new."""
    src = get(source_pid)
    return add(target_pid, src["paths"]) if src and target_pid != source_pid else 0


def clear(pid):
    def f(pls):
        for p in pls:
            if p["id"] == pid:
                n = len(p["paths"])
                p["paths"] = []
                return n
        return 0
    return _mutate(f)


def set_paths(pid, paths):
    """Replace the whole order (used after dragging / sorting)."""
    def f(pls):
        for p in pls:
            if p["id"] == pid:
                p["paths"] = list(dict.fromkeys(paths))
                return True
        return False
    return _mutate(f)


def prune_missing(pid):
    """Remove songs whose file no longer exists. Returns how many were removed."""
    def f(pls):
        for p in pls:
            if p["id"] == pid:
                keep = [x for x in p["paths"] if os.path.isfile(x)]
                n = len(p["paths"]) - len(keep)
                p["paths"] = keep
                return n
        return 0
    return _mutate(f)


def containing(path):
    """Ids of the playlists that already contain this song."""
    return [p["id"] for p in _read() if path in p["paths"]]


# END-OF-FILE rofpalys_playlists.py

