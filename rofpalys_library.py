#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - library scanner (find songs anywhere: home, shared storage, SD card)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Rofpalys library: cross-platform music discovery, scan cache, and input resolving."""
import difflib
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.parse

IS_WIN = sys.platform == "win32"
HOME = os.path.expanduser("~")
IS_TERMUX = bool(os.environ.get("TERMUX_VERSION")) or "com.termux" in os.environ.get("PREFIX", "")

if IS_WIN:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", HOME), "rofpalys")
    CACHE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HOME), "rofpalys", "cache")
else:
    CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "rofpalys")
    CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"), "rofpalys")
LEGACY_DIR = os.path.join(HOME, ".config", "rofpalysx")      # where the old GUI kept favorites/settings
CACHE_FILE = os.path.join(CACHE_DIR, "library.json")

AUDIO_EXTS = (
    '.mp3', '.aac', '.wav', '.flac', '.alac', '.aiff', '.aif', '.ogg',
    '.wma', '.opus', '.mid', '.midi', '.m4a', '.m4b', '.m4p', '.pcm',
    '.dsd', '.dsf', '.dff', '.amr', '.ape', '.wv', '.mpc', '.ac3',
    '.dts', '.truehd', '.eac3', '.ra', '.au', '.caf', '.voc', '.iff',
    '.tak', '.tta', '.mp4', '.webm', '.mka'
)
# folders that never contain "real" music (or are huge / unreadable)
DEFAULT_SKIP = ("node_modules", "site-packages", "dist-packages", "__pycache__", "venv", "$recycle.bin",
                "system volume information", "lost+found", "ringtones", "notifications", "alarms")
_BLOCKED_SUFFIX = ("/android/data", "/android/obb")           # Android blocks these anyway


def _blocked(path):
    return path.replace("\\", "/").lower().endswith(_BLOCKED_SUFFIX)


def prune_roots(roots):
    """Resolve symlinks, drop duplicates and roots that live inside another root."""
    rs = []
    for r in roots:
        r = os.path.realpath(os.path.expanduser(r))
        if r not in rs:
            rs.append(r)
    return [r for r in rs if not any(r != o and r.startswith(o.rstrip(os.sep) + os.sep) for o in rs)]


def default_roots(extra=(), scan_home=True):
    """Every place songs may live: the whole home folder, extra folders, Android shared storage and SD cards."""
    roots = []
    if scan_home:
        roots.append(HOME)
    roots += list(extra)
    if IS_TERMUX or os.path.isdir("/storage/emulated/0"):
        roots += ["/sdcard", "/storage/emulated/0"]
        st = os.path.join(HOME, "storage")                    # created by termux-setup-storage (symlinks)
        if os.path.isdir(st):
            roots += [os.path.join(st, n) for n in sorted(os.listdir(st))]
        try:
            roots += ["/storage/" + n for n in os.listdir("/storage") if n not in ("emulated", "self")]
        except OSError:
            pass
    elif sys.platform == "darwin":
        roots.append(os.path.join(HOME, "Music"))
    return prune_roots([r for r in roots if os.path.isdir(r)])


def storage_hint():
    """Short hint when Termux cannot see phone storage yet."""
    if IS_TERMUX and not os.path.isdir(os.path.join(HOME, "storage")):
        return "run: termux-setup-storage"
    return ""


def scan(roots, exts=AUDIO_EXTS, min_size=0, max_depth=12, skip_names=(), stop=None, dedupe=True):
    """Walk the roots and return {path: mtime}. Hidden folders and junk folders are skipped."""
    exts = tuple(exts)
    skip = {s.lower() for s in DEFAULT_SKIP} | {str(s).lower() for s in skip_names}
    out, seen = {}, set()
    for root in prune_roots(roots):
        stack = [(root, 0)]
        while stack:
            if stop and stop():
                return out
            d, depth = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        name = e.name
                        if e.is_dir(follow_symlinks=False):
                            if depth < max_depth and not name.startswith(".") and name.lower() not in skip and not _blocked(e.path):
                                stack.append((e.path, depth + 1))
                        elif not name.startswith(".") and name.lower().endswith(exts):
                            st = e.stat()
                            if st.st_size < min_size:
                                continue
                            if dedupe:
                                key = (name.lower(), st.st_size)
                                if key in seen:
                                    continue
                                seen.add(key)
                            out[e.path] = st.st_mtime
                    except OSError:
                        continue
    return out


def save_cache(items, roots):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "time": int(time.time()), "roots": list(roots), "items": [[p, m] for p, m in items.items()]}, f)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def load_cache(roots):
    """Instant start: last scan result if it was made for the same roots."""
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") != 1 or d.get("roots") != list(roots):
            return {}
        return {p: m for p, m in d["items"] if os.path.isfile(p)}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def read_m3u(path):
    base, out = os.path.dirname(path), []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    p = ln if os.path.isabs(ln) else os.path.join(base, ln)
                    if os.path.isfile(p):
                        out.append(os.path.abspath(p))
    except OSError:
        pass
    return out


def resolve_inputs(args, exts=AUDIO_EXTS):
    """Turn command-line arguments (files, folders, .m3u, file:// URIs) into a list of audio files.
    Songs from ANY place on the device work - they do not have to be inside the library."""
    files, skipped = [], []
    for a in args:
        if a.startswith("file://"):
            a = urllib.parse.unquote(urllib.parse.urlparse(a).path)
        elif "://" in a:
            skipped.append(a)
            continue
        p = os.path.abspath(os.path.expanduser(a))
        if os.path.isdir(p):
            files += sorted(scan([p], exts, 0, max_depth=6, dedupe=False))
        elif os.path.isfile(p):
            low = p.lower()
            if low.endswith((".m3u", ".m3u8")):
                files += read_m3u(p)
            elif low.endswith(tuple(exts)):
                files.append(p)
            else:
                skipped.append(a)
        else:
            skipped.append(a)
    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq, skipped


# ------------------------------------------------------------------ groups: Spotify-like "playlists" made from where the songs live
CATEGORY_ORDER = ("termux", "wa", "app", "download", "phone", "sd", "rofpalys", "other")
CATEGORY_NAMES = {"termux": "Termux Music" if IS_TERMUX else "Home Music", "wa": "WhatsApp Music", "app": "App Music", "download": "Downloads",
                  "phone": "Phone Music", "sd": "SD Card Music", "rofpalys": "Rofpalys Downloads", "other": "Other Music"}
_SHARED = ("/storage/emulated/", "/sdcard/", "/storage/self/")
GENERIC_DIRS = ("music", "download", "downloads", "audio", "media", "songs", "sounds", "documents", "files")


def category_of(path):
    """termux | wa | app | download | phone | sd | rofpalys | other  - decided from the path only (no disk access)."""
    low = path.replace("\\", "/").lower()
    if "whatsapp" in low:
        return "wa"
    if "/music/rofpalys" in low:
        return "rofpalys"
    if low.startswith(_SHARED):
        if "/android/media/" in low or "/telegram" in low:
            return "app"
        if "/download" in low:
            return "download"
        return "phone"
    if low.startswith("/storage/"):
        return "sd"
    if low.startswith(HOME.replace("\\", "/").lower().rstrip("/") + "/"):
        return "termux"
    return "other"


def folder_label(d):
    base = os.path.basename(d.rstrip("/\\")) or d
    if base.lower() in GENERIC_DIRS:
        up = os.path.basename(os.path.dirname(d.rstrip("/\\")))
        if up and up.lower() not in ("home", "0", "emulated", "storage", "sdcard", "media", "users") and up != os.path.basename(HOME.rstrip("/\\")):
            return "%s / %s" % (up, base)
    return base


def short_path(d):
    d = d.replace("\\", "/")
    for a, b in (("/storage/emulated/0", "Phone"), ("/sdcard", "Phone"), (HOME.replace("\\", "/"), "~")):
        if d.startswith(a):
            return b + d[len(a):]
    return d


def build_groups(paths):
    """(categories, folders): each a list of {id, kind, name, sub, paths}. The paths keep the order they came in."""
    cats, dirs = {}, {}
    for p in paths:
        cats.setdefault(category_of(p), []).append(p)
        dirs.setdefault(os.path.dirname(p), []).append(p)
    categories = [{"id": "cat:" + c, "kind": "category", "name": CATEGORY_NAMES[c], "sub": "", "paths": cats[c]} for c in CATEGORY_ORDER if c in cats]
    folders = sorted(({"id": "dir:" + d, "kind": "folder", "name": folder_label(d), "sub": short_path(d), "paths": ps} for d, ps in dirs.items()),
                     key=lambda g: g["name"].lower())
    return categories, folders


# ------------------------------------------------------------------ smart search (all local: no internet, no account)
_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ı": "i", "œ": "oe"})


def norm(s):
    s = unicodedata.normalize("NFKD", s.translate(_TRANSLIT))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[\W_]+", " ", s).strip()


_ent = {}


def _entry(p):
    e = _ent.get(p)
    if e is None:
        name = os.path.splitext(os.path.basename(p))[0]
        n = norm(name)
        toks = n.split()
        artist = norm(name.split(" - ", 1)[0]) if " - " in name else ""
        e = _ent[p] = (n, toks, {n[i:i + 2] for i in range(len(n) - 1)}, "".join(t[0] for t in toks), artist)
    return e


def _partial(q, n):
    """Best similarity of q to any part of n that starts at a word (so typos in the middle of a title still match)."""
    best = 0.0
    for i in [0] + [m.end() for m in re.finditer(" ", n)]:
        best = max(best, difflib.SequenceMatcher(None, q, n[i:i + len(q) + 2]).ratio())
    return best


def smart_search(query, paths, plays=None, favs=(), limit=60):
    """Ranked [(path, score)]. Understands: the beginning of a title, any word of it, initials ('cyf' = Choose Your Fighter),
    typos ('shpe of yuo'), and prefers songs you play often or have in favorites."""
    q = norm(query)
    if not q:
        return []
    qt, plays, qbig = q.split(), plays or {}, {q[i:i + 2] for i in range(len(q) - 1)}
    flat = q.replace(" ", "")
    out = []
    for p in paths:
        n, toks, big, init, artist = _entry(p)
        s = 0.0
        if q in n:
            i = n.index(q)
            if len(q) <= 2 and i and n[i - 1] != " ":
                continue                                     # one or two letters only match the start of a word
            s = 100 + (30 if i == 0 else 0) + (15 if i == 0 or n[i - 1] == " " else 0)
        elif len(q) >= 2:
            pref = sum(1 for t in qt if any(x.startswith(t) for x in toks))
            if pref == len(qt):
                s = 85
            elif pref:
                s = 45.0 * pref / len(qt)
            if len(flat) >= 3 and flat in init or len(flat) == 2 and init.startswith(flat):
                s = max(s, 60)                               # initials: "cyf" = Choose Your Fighter
            if s < 60 and qbig and len(qbig & big) / float(len(qbig)) >= 0.45:
                r = max(_partial(q, n), difflib.SequenceMatcher(None, q, n).ratio())
                if r >= 0.6:
                    s = max(s, 70 * r)
        if s < 30:
            continue
        s += min(15, plays.get(p, {}).get("plays", 0) * 2) + (8 if p in favs else 0) + (10 if artist and q in artist else 0)
        out.append((s, p))
    out.sort(key=lambda x: (-x[0], os.path.basename(x[1]).lower()))
    return [(p, s) for s, p in out[:limit]]


def did_you_mean(query, paths):
    """The closest title when nothing matched ('' if nothing is close)."""
    q = norm(query)
    if len(q) < 3:
        return ""
    qbig, best, best_p = {q[i:i + 2] for i in range(len(q) - 1)}, 0.0, ""
    for p in paths:
        n, _, big, _, _ = _entry(p)
        if qbig and len(qbig & big) / float(len(qbig)) < 0.3:
            continue
        r = _partial(q, n)
        if r > best:
            best, best_p = r, p
    return os.path.splitext(os.path.basename(best_p))[0] if best >= 0.55 else ""


def match_groups(query, groups, limit=5):
    q = norm(query)
    if not q:
        return []
    scored = []
    for g in groups:
        n = norm(g["name"])
        s = 100 if n.startswith(q) else 80 if q in n else 70 * difflib.SequenceMatcher(None, q, n).ratio()
        if s >= 50:
            scored.append((s, g))
    scored.sort(key=lambda x: -x[0])
    return [g for _, g in scored[:limit]]


# ------------------------------------------------------------------ recommendations ("Made for you", "Discover", ...)
def similar(seed, paths, exclude=(), limit=8):
    """Songs most like `seed`: same artist first, then same folder, then shared title words."""
    if not seed:
        return []
    _, toks, _, _, artist = _entry(seed)
    d, ex, out = os.path.dirname(seed), set(exclude), []
    for p in paths:
        if p == seed or p in ex:
            continue
        e = _entry(p)
        sc = (3 if artist and e[4] == artist else 0) + (1 if os.path.dirname(p) == d else 0) + min(1.5, 0.5 * len(set(toks) & set(e[1])))
        if sc > 0:
            out.append((sc, p))
    out.sort(key=lambda x: (-x[0], os.path.basename(x[1]).lower()))
    return [p for _, p in out[:limit]]


def home_sections(paths, plays, favs, mtimes, last=None):
    """[(key, [paths])] for the Home page: recent, mix, favorites, top, new, discover (empty ones are left out)."""
    pset = set(paths)
    rng = random.Random(time.strftime("%Y%m%d"))                     # the "Discover" mix changes once a day
    recent = [p for p in sorted((p for p, v in plays.items() if p in pset and v.get("ts")), key=lambda p: -plays[p]["ts"])][:6]
    top = sorted((p for p, v in plays.items() if p in pset and v.get("plays", 0) > 0), key=lambda p: -plays[p]["plays"])[:8]
    fav = [p for p in paths if p in favs][:8]
    new = sorted(paths, key=lambda p: -mtimes.get(p, 0))[:8]
    mix = similar(last if last in pset else (recent[0] if recent else None), paths, exclude=recent, limit=8)
    disc = [p for p in paths if not plays.get(p, {}).get("plays")]
    rng.shuffle(disc)
    secs = [("recent", recent), ("mix", mix), ("favorites", fav), ("top", top), ("new", new), ("discover", disc[:8])]
    return [(k, v) for k, v in secs if v]


# ------------------------------------------------------------------ more groups: Artists and Mixes (made from the file names)
MIX_RULES = (("slowed", "Slowed + Reverb", ("slowed", "reverb")), ("sped", "Sped Up / Nightcore", ("sped up", "speed up", "nightcore")),
             ("lofi", "Lo-fi", ("lofi", "lo fi")), ("remix", "Remixes", ("remix", "mashup", "bootleg")),
             ("long", "Long listens (1 hour+)", ("1 hour", "1hour", "hour version", "hours", "10 hour")), ("acoustic", "Acoustic & Live", ("acoustic", "unplugged", "live ")))
_ARTIST_SPLIT = re.compile(r",\s+|\s+x\s+|\s+feat\.?\s+|\s+ft\.?\s+|\s+featuring\s+", re.I)


def split_artists(name):
    """'Fyex, PHARAØH - Freaks' -> ['Fyex', 'PHARAØH']; no ' - ' in the name -> []."""
    base = os.path.splitext(os.path.basename(name))[0]
    if " - " not in base:
        return []
    return [a.strip() for a in _ARTIST_SPLIT.split(base.split(" - ", 1)[0]) if a.strip()]


def build_extra_groups(paths, min_artist_songs=2, min_mix_songs=3):
    """(artists, mixes). An artist needs at least 2 songs to get a page of his own; a mix needs 3."""
    art, shown = {}, {}
    mixes = {k: [] for k, _, _ in MIX_RULES}
    for p in paths:
        for a in split_artists(p):
            key = norm(a)
            if key:
                art.setdefault(key, []).append(p)
                shown.setdefault(key, a)
        n = " " + norm(os.path.splitext(os.path.basename(p))[0]) + " "
        for k, _, words in MIX_RULES:
            if any((" " + w.strip() + " ") in n or w in n for w in words):
                mixes[k].append(p)
    artists = sorted(({"id": "artist:" + k, "kind": "artist", "name": shown[k], "sub": "", "paths": v} for k, v in art.items() if len(v) >= min_artist_songs),
                     key=lambda g: (-len(g["paths"]), g["name"].lower()))
    mix = [{"id": "mix:" + k, "kind": "mix", "name": name, "sub": "", "paths": mixes[k]} for k, name, _ in MIX_RULES if len(mixes[k]) >= min_mix_songs]
    return artists, mix


# END-OF-FILE rofpalys_library.py

