#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI providers: WHERE the lyrics come from (syncedlyrics -> lrcdl -> lyriq -> librelyrics) and what happens when one fails
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The 'fetching' half of CyroKayAI. It knows four lyric downloaders and asks them one after the other until one of them gives lyrics that FIT THE SONG:

    1. syncedlyrics   (default, first)   Musixmatch, LRCLIB, NetEase, Megalobiz ...   pip install syncedlyrics
    2. lrcdl                              LRCLIB, looked up from the audio file         pip install lrcdl          (needs Python 3.11+)
    3. lyriq                              LRCLIB, exact and fuzzy search                pip install lyriq
    4. librelyrics                        plugin based (needs one search plugin)        pip install librelyrics + a plugin
    then, in rofpalys_CyroKayAI_lyric.py, the built-in safety net (LRCLIB, YouTube captions, lyrics.ovh) which needs no package at all.

A provider has FAILED, and the next one is asked, when it is not installed, raised an error, took too long, found nothing, found only text without
timestamps, gave a file that is not a lyric file, named another song in its header, or gave lyrics that do not fit the voice in the recording
(fit < 35 %). A fit of 60 % or more is accepted at once (the priority order is respected); between 35 % and 60 % the next provider gets a say as well
and the better fit wins (a tie goes to the provider that comes first).

Order: environment ROFPALYS_LYRIC_PROVIDERS="syncedlyrics,lrcdl,lyriq,librelyrics" (or "off" = only the built-in safety net), else the saved choice
(rofpalys lyrics providers order ...), else the order above.  Every adapter uses the package's Python API and, when only its command is installed,
the command. A provider that keeps failing with errors is left alone for 10 minutes so one broken server does not slow down every song.
Honest limits: the four packages are third-party code that was read about, not run, while this file was written; every adapter is therefore guarded
(a crash or a hang in a package is caught and counts as 'failed'), and the audio fit is the final judge of whether the lyrics belong to the song."""
import difflib
import hashlib
import importlib
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

try:
    import rofpalys_CyroKayAI_memory as MEM
except Exception:
    MEM = None

__version__ = "1.0"
DEFAULT_ORDER = ("syncedlyrics", "lrcdl", "lyriq", "librelyrics")
MIN_PY = {"syncedlyrics": (3, 8), "lrcdl": (3, 11), "lyriq": (3, 9), "librelyrics": (3, 10)}
TIMEOUT = {"syncedlyrics": 45.0, "lrcdl": 30.0, "lyriq": 25.0, "librelyrics": 40.0}      # seconds one provider may take for one question
GOOD = 0.60                                         # a fit this good is accepted at once
OK = 0.35                                           # below this the lyrics do not fit the song: the provider has failed
COOLDOWN = 600.0                                    # seconds a provider that keeps raising errors is left alone
NOTE_HELP = {"not-installed": "not installed", "python-too-old": "needs a newer Python", "no-result": "nothing found", "plain-only": "only text without timestamps",
             "bad-lrc": "not a lyric file", "wrong-song": "another song", "timeout": "too slow", "cooldown": "resting after errors", "no-audio": "needs the audio file",
             "no-plugin": "needs a plugin", "low-fit": "does not fit the song", "duplicate": "same lyrics as before", "stopped": "stopped", "no-query": "no title",
             "ok": "ok", "fit-error": "could not be checked"}
NOTE_ID = {"not-installed": "belum terpasang", "python-too-old": "butuh Python lebih baru", "no-result": "tidak ada hasil", "plain-only": "hanya teks tanpa waktu",
           "bad-lrc": "bukan file lirik", "wrong-song": "lagu lain", "timeout": "terlalu lambat", "cooldown": "istirahat setelah error", "no-audio": "butuh file lagunya",
           "no-plugin": "butuh plugin", "low-fit": "tidak cocok dengan lagunya", "duplicate": "lirik sama seperti sebelumnya", "stopped": "dihentikan", "no-query": "tanpa judul",
           "ok": "ok", "fit-error": "tidak bisa dicek"}
_LOCK = threading.RLock()
_HEALTH = {}
_MODS = {}


def log(msg):
    if os.environ.get("ROFPALYS_DEBUG"):
        try:
            sys.stderr.write("[CyroKayAI providers] %s\n" % msg)
        except Exception:
            pass


class _Halt(Exception):
    """A provider call that was ended from outside: too slow (code 'timeout') or the song changed (code 'stopped')."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


# ------------------------------------------------------------------ the order
_ALIASES = {"syncedlyrics": "syncedlyrics", "syncedlyric": "syncedlyrics", "synced": "syncedlyrics", "lrcdl": "lrcdl", "lyriq": "lyriq",
            "librelyrics": "librelyrics", "librelyric": "librelyrics", "libre": "librelyrics"}


def parse_order(value):
    """'syncedlyrics, lrcdl > lyriq' -> ['syncedlyrics', 'lrcdl', 'lyriq'];  'off' -> [] (built-in safety net only);  nothing usable -> None."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = ",".join(str(v) for v in value)
    s = str(value).strip().lower()
    if not s:
        return None
    if s in ("off", "none", "no", "0", "builtin", "built-in"):
        return []
    out = []
    for tok in re.split(r"[\s,;>|]+|->|→", s):
        n = _ALIASES.get(tok)
        if n and n not in out:
            out.append(n)
    return out or None


def order():
    """The providers in the order they are asked: environment, then the saved choice, then the default (syncedlyrics first)."""
    for src in (os.environ.get("ROFPALYS_LYRIC_PROVIDERS"), MEM.get_pref("providers") if MEM is not None else None):
        o = parse_order(src)
        if o is not None:
            return o
    return list(DEFAULT_ORDER)


def set_order(value):
    """Save the order (None = back to the default). -> the order now in force (the environment variable, if set, still wins)."""
    if MEM is not None:
        o = parse_order(value)
        MEM.set_pref("providers", None if (value is None or o is None) else ("off" if not o else o))
    return order()


def reset():
    """Forget the import results and the resting times (after pip install, and for tests)."""
    with _LOCK:
        _MODS.clear()
        _HEALTH.clear()


# ------------------------------------------------------------------ lyric text hygiene
_STAMP = re.compile(r"\[(\d{1,3}):(\d{2}(?:[.:]\d{1,3})?)\]")
_LEAD = re.compile(r"^(\s*(?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]\s*)+)(.*)$")
_WORD_TAG = re.compile(r"<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>")
_HDR = re.compile(r"^\[(ar|ti|al|by|length|offset|re|ve|au|la|tool|id):([^\]]*)\]\s*$", re.I)


def _secs(mm, ss):
    return int(mm) * 60 + float(ss.replace(":", "."))


def _fmt_stamp(t):
    t = max(0.0, t)
    m = int(t // 60)
    return "[%02d:%05.2f]" % (m, t - 60 * m)


def _shift_line(line, dt):
    m = _LEAD.match(line)
    if not m:
        return line
    stamps = _STAMP.findall(m.group(1))
    return "".join(_fmt_stamp(_secs(a, b) + dt) for a, b in stamps) + m.group(2)


def clean_lrc(text):
    """Raw text from a provider -> (lrc, meta, n): only the timed lines (word-by-word tags removed, [offset:] applied, header tags moved to meta),
    meta = {'ti': ..., 'ar': ..., 'length': ...} and n = how many different time stamps there are. n < 4 means: this is not synced lyrics."""
    meta = {}
    if not text:
        return "", meta, 0
    body = []
    for ln in str(text).replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿").split("\n"):
        s = ln.strip()
        if not s:
            continue
        h = _HDR.match(s)
        if h:
            meta[h.group(1).lower()] = h.group(2).strip()
            continue
        m = _LEAD.match(s)
        if m:
            txt = m.group(2)
            if _WORD_TAG.search(txt):
                txt = re.sub(r"\s{2,}", " ", _WORD_TAG.sub("", txt)).strip()
            body.append(re.sub(r"\s+$", "", m.group(1).replace(" ", "")) + txt)
    try:
        off = int(re.sub(r"[^\d+-]", "", meta.get("offset", "")) or 0)
    except ValueError:
        off = 0
    if off:
        body = [_shift_line(b, -off / 1000.0) for b in body]                      # LRC: a positive offset makes the lyrics appear EARLIER
    times = set()
    for b in body:
        m = _LEAD.match(b)
        if m and m.group(2).strip():
            for a, c in _STAMP.findall(m.group(1)):
                times.add(round(_secs(a, c), 2))
    return "\n".join(body), meta, len(times)


def clean_plain(text):
    """Raw text without timestamps -> tidy text (stamps and header tags removed, stanza breaks kept)."""
    if not text:
        return ""
    out = []
    for ln in str(text).replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿").split("\n"):
        if _HDR.match(ln.strip()):
            continue
        out.append(_WORD_TAG.sub("", _STAMP.sub("", ln)).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _lines(text):
    return sum(1 for ln in (text or "").split("\n") if ln.strip())


def _norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def similar(a, b):
    """0..1 how alike two titles / names are (case, punctuation and spaces do not matter; one inside the other counts 0.9 when long enough)."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 4 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def text_key(raw):
    """The same lyrics from two providers (they share databases) give the same key: time stamps and punctuation do not matter."""
    return hashlib.sha1(_norm(re.sub(r"\[[^\]]*\]", "", raw or "")).encode("utf-8", "replace")).hexdigest()


def _length(meta):
    m = re.match(r"^\s*(\d{1,3}):(\d{1,2})(?:[.:]\d+)?\s*$", (meta or {}).get("length", ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0.0


def _wrong_song(meta, q):
    """The file's own header names another title than the one we asked for (only when the header exists). Not a veto: the same song can be written
    in another alphabet or with a different subtitle. The chain halves the audio fit of such lyrics, so a provider that names the right title wins
    a tie, but lyrics that fit the voice well are still used when nothing better exists."""
    ti = (meta or {}).get("ti", "")
    return bool(ti and q.get("title") and _title_alike(ti, q["title"]) < 0.5)


def _title_alike(a, b):
    """Like similar(), but two titles of several words that share only a word or two ('Some Other Song' / 'Test Song') are not alike."""
    s = similar(a, b)
    ta, tb = set(re.findall(r"\w+", (a or "").lower())), set(re.findall(r"\w+", (b or "").lower()))
    if s < 0.9 and len(ta) >= 2 and len(tb) >= 2:
        s = min(s, len(ta & tb) / float(len(ta | tb)) + 0.15)
    return s


MISMATCH_FACTOR = 0.5


def _term(q):
    return " ".join(x for x in (q.get("title"), q.get("artist")) if x).strip()              # the syncedlyrics documentation: "[TRACK_NAME] [ARTIST_NAME]"


def _safe_name(s):
    return re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", s or "").strip(" .")[:90] or "song"


# ------------------------------------------------------------------ plumbing: imports, time limits, commands
def _py_ok(name):
    return sys.version_info >= MIN_PY[name]


def _module(name):
    """The imported package, or None. A failed import is not repeated for a minute."""
    with _LOCK:
        e = _MODS.get(name)
    if e is not None and (e[0] is not None or time.time() - e[1] < 60):
        return e[0]
    try:
        m = importlib.import_module(name)
    except BaseException:                                                   # a broken package (even SystemExit) is just 'not installed'
        m = None
    with _LOCK:
        _MODS[name] = (m, time.time())
    return m


def _quiet(name):
    """A package that logs 'no lyrics found' must not write into the terminal player."""
    try:
        lg = logging.getLogger(name)
        lg.setLevel(logging.CRITICAL + 1)
        lg.propagate = False
    except Exception:
        pass


def _guard(fn, timeout, stop=None):
    """Run fn() in a helper thread; give up after `timeout` seconds or when stop() says so (the thread is left to die by itself)."""
    box = {}

    def work():
        try:
            box["v"] = fn()
        except BaseException as e:                                          # includes SystemExit from a command line tool used as a library
            box["e"] = e
    th = threading.Thread(target=work, daemon=True)
    th.start()
    t0 = time.time()
    while th.is_alive():
        th.join(0.15)
        if stop is not None and stop():
            raise _Halt("stopped")
        if time.time() - t0 > timeout:
            raise _Halt("timeout")
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _run(cmd, timeout, cwd=None, stop=None):
    """Run a command, return (code, stdout, stderr); killed after `timeout` seconds or when stop() says so."""
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    t0 = time.time()
    while True:
        try:
            out, err = p.communicate(timeout=0.25)
            return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            halted = bool(stop is not None and stop())
            if halted or time.time() - t0 > timeout:
                p.kill()
                try:
                    p.communicate(timeout=2)
                except Exception:
                    pass
                raise _Halt("stopped" if halted else "timeout")


def _read_first(folder, exts=(".lrc", ".txt"), recursive=False):
    """The biggest lyric file a command wrote into `folder`, as text ('' if none)."""
    found = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(exts):
                try:
                    p = os.path.join(root, f)
                    found.append((os.path.getsize(p), p))
                except OSError:
                    pass
        if not recursive:
            break
    for _, p in sorted(found, reverse=True):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            continue
    return ""


def _link(path, folder, label):
    """A name for the audio file inside a private folder (symlink, else hard link, else a copy of a file up to 80 MB), so a command that writes its
    .lrc next to the audio file writes it THERE and not into the music folder."""
    dst = os.path.join(folder, _safe_name(label) + (os.path.splitext(path)[1] or ".mp3"))
    for how in ("symlink", "link", "copy"):
        try:
            if how == "symlink":
                os.symlink(os.path.abspath(path), dst)
            elif how == "link":
                os.link(path, dst)
            else:
                if os.path.getsize(path) > 80 * 1024 * 1024:
                    return None
                shutil.copyfile(path, dst)
            return dst
        except (OSError, NotImplementedError, AttributeError):
            continue
    return None


# ------------------------------------------------------------------ the four adapters: each returns (synced_or_text, plain_text, code)
def _a_syncedlyrics(q, mode, ctx):
    term = _term(q)
    if not term:
        return "", "", "no-query"
    mod = _module("syncedlyrics") if ctx["py_ok"] else None
    if mod is not None:
        _quiet("syncedlyrics")
        kw = {"synced_only": True} if mode == "synced" else {"plain_only": True}
        try:
            r = mod.search(term, **kw)
        except TypeError:                                                   # an older release without synced_only / plain_only
            r = mod.search(term)
        return (r or ""), "", "ran"
    exe = shutil.which("syncedlyrics")
    if not exe:
        return "", "", "python-too-old" if not ctx["py_ok"] else "not-installed"
    tmp = tempfile.mkdtemp(prefix="rofpalys_sl_")
    try:
        out = os.path.join(tmp, "out.lrc")
        _run([exe, term, "--synced-only" if mode == "synced" else "--plain-only", "-o", out], ctx["timeout"], tmp, ctx["stop"])
        return _read_first(tmp), "", "ran"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _a_lrcdl(q, mode, ctx):
    path = q.get("path")
    if not path or not os.path.isfile(path):
        return "", "", "no-audio"
    exe = shutil.which("lrcdl")
    mod = _module("lrcdl") if ctx["py_ok"] else None
    if not exe and mod is None:
        return "", "", "python-too-old" if not ctx["py_ok"] else "not-installed"
    tmp = tempfile.mkdtemp(prefix="rofpalys_dl_")
    try:
        link = _link(path, tmp, "%s - %s" % (q.get("artist") or "", q.get("title") or ""))
        if link is None:
            return "", "", "no-audio"
        out = os.path.splitext(link)[0] + ".lrc"
        if exe:
            cmd = [exe, link]
            for flag, key in (("--title", "title"), ("--artist", "artist"), ("--album", "album")):
                if q.get(key):
                    cmd += [flag, q[key]]
            if mode == "plain":
                cmd.append("--include-plain")
            _run(cmd, ctx["timeout"], tmp, ctx["stop"])
        else:
            try:
                opts = mod.Options(download_path=out, include_plain=True) if mode == "plain" else mod.Options(download_path=out)
            except TypeError:
                opts = mod.Options(download_path=out)
            mod.Track(link).download_lyrics(opts)
        txt = ""
        if os.path.isfile(out):
            with open(out, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        return (txt or _read_first(tmp, (".lrc",))), "", "ran"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _best_hit(hits, q):
    """The best of several LRCLIB records (lyriq search): the title and artist must fit, the length decides between versions."""
    best = None
    for h in hits or []:
        synced = getattr(h, "synced_lyrics", "") or ""
        plain = getattr(h, "plain_lyrics", "") or ""
        if not (synced or plain) or getattr(h, "instrumental", False):
            continue
        s = 0.6 * similar(q.get("title"), getattr(h, "track_name", "") or getattr(h, "name", ""))
        s += 0.2 * (similar(q.get("artist"), getattr(h, "artist_name", "")) if q.get("artist") else 0.7)
        d, hd = q.get("duration") or 0, getattr(h, "duration", 0) or 0
        s += (0.2 if abs(d - hd) <= 3 else 0.1 if abs(d - hd) <= 8 else 0.0) if d and hd else 0.08
        s += 0.15 if synced else 0.0
        if s >= 0.55 and (best is None or s > best[0]):
            best = (s, h)
    return best[1] if best else None


def _a_lyriq(q, mode, ctx):
    title, artist = q.get("title"), q.get("artist")
    if not title:
        return "", "", "no-query"
    mod = _module("lyriq") if ctx["py_ok"] else None
    if mod is None:
        exe = shutil.which("lyriq")
        if not exe:
            return "", "", "python-too-old" if not ctx["py_ok"] else "not-installed"
        if not artist:
            return "", "", "no-query"
        tmp = tempfile.mkdtemp(prefix="rofpalys_lq_")
        try:
            out = os.path.join(tmp, "out.lrc")
            cmd = [exe, title, artist] + (["--duration", str(int(round(q["duration"])))] if (q.get("duration") or 0) > 0 else []) + ["--file", out, "--file-format", "lrc"]
            _run(cmd, ctx["timeout"], tmp, ctx["stop"])
            return _read_first(tmp, (".lrc",)), "", "ran"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    dur = int(round(q["duration"])) if (q.get("duration") or 0) > 0 else None
    obj = None
    if artist:
        obj = mod.get_lyrics(title, artist, q.get("album") or None, dur)
        if obj is None and (q.get("album") or dur):
            obj = mod.get_lyrics(title, artist)                             # LRCLIB's exact lookup is strict about album and length: ask loosely, the audio fit judges
    if obj is None or getattr(obj, "instrumental", False) or not (getattr(obj, "synced_lyrics", "") or getattr(obj, "plain_lyrics", "")):
        hits = mod.search_lyrics(song_name=title, artist_name=artist) if artist else mod.search_lyrics(q=title)
        obj = _best_hit(hits, q)
    if obj is None:
        return "", "", "ran"
    return (getattr(obj, "synced_lyrics", "") or ""), (getattr(obj, "plain_lyrics", "") or ""), "ran"


def _lrc_of(resp):
    """The lyric text of whatever librelyrics returned (a response object, or a list of them)."""
    if isinstance(resp, (list, tuple)):
        resp = resp[0] if resp else None
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    fn = getattr(resp, "to_lrc", None)
    if callable(fn):
        r = fn()
        if isinstance(r, str):
            return r
    for attr in ("lrc", "synced", "lyrics", "text"):
        v = getattr(resp, attr, None)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _a_librelyrics(q, mode, ctx):
    artist, title = q.get("artist"), q.get("title")
    if not (artist and title):
        return "", "", "no-query"
    mod = _module("librelyrics") if ctx["py_ok"] else None
    if mod is None:
        exe = shutil.which("librelyrics")
        if not exe:
            return "", "", "python-too-old" if not ctx["py_ok"] else "not-installed"
        tmp = tempfile.mkdtemp(prefix="rofpalys_ll_")
        try:
            code, out, err = _run([exe, "--artist", artist, "--title", title], ctx["timeout"], tmp, ctx["stop"])
            if re.search(r"no (search )?plugin|plugin", err + out, re.I) and not _read_first(tmp, (".lrc", ".txt"), True):
                return "", "", "no-plugin"
            return _read_first(tmp, (".lrc", ".txt"), True), "", "ran"                # the files go to ./downloads (its default), which is inside tmp
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    try:
        resp = mod.LibreLyrics().fetch_query(mod.TrackQuery(artist=artist, title=title))
    except Exception as e:
        if re.search(r"plugin|no (search )?(source|provider)", str(e), re.I):
            return "", "", "no-plugin"
        raise
    return _lrc_of(resp), "", "ran"


_ADAPTERS = {"syncedlyrics": _a_syncedlyrics, "lrcdl": _a_lrcdl, "lyriq": _a_lyriq, "librelyrics": _a_librelyrics}


# ------------------------------------------------------------------ one question to one provider
def _cooling(name):
    with _LOCK:
        h = _HEALTH.get(name)
        return bool(h and h.get("until", 0) > time.time())


def _note_health(name, code):
    with _LOCK:
        h = _HEALTH.setdefault(name, {"fails": 0, "until": 0.0})
        if code.startswith("error") or code == "timeout":
            h["fails"] += 1
            if h["fails"] >= 3:
                h["until"] = time.time() + COOLDOWN
                h["fails"] = 0
        elif code == "no-plugin":
            h["until"] = time.time() + 6 * COOLDOWN
        elif code not in ("stopped", "not-installed", "python-too-old"):
            h["fails"] = 0


def _scale():
    try:
        return max(0.1, float(os.environ.get("ROFPALYS_LYRIC_TIMEOUT", "1") or 1))
    except ValueError:
        return 1.0


def fetch(name, q, mode="synced", stop=None, timeout=None):
    """Ask ONE provider. q = {'artist', 'title', 'album', 'duration', 'path'}; mode 'synced' or 'plain'.
    -> {'provider', 'raw' (clean LRC with timestamps or ''), 'plain' (text without timestamps or ''), 'note' (see NOTE_HELP, or 'error: ...'), 'meta',
    'duration', 'secs', 'mismatch' (the header names another title)}"""
    R = {"provider": name, "raw": "", "plain": "", "note": "", "meta": {}, "duration": 0.0, "secs": 0.0, "mismatch": False}
    t0 = time.time()
    ad = _ADAPTERS.get(name)
    if ad is None:
        R["note"] = "error: unknown provider"
        return R
    if _cooling(name):
        R["note"] = "cooldown"
        return R
    tmo = (timeout or TIMEOUT.get(name, 30.0)) * _scale()
    ctx = {"py_ok": _py_ok(name), "timeout": tmo, "stop": stop}
    text, plain, note = "", "", "ran"
    try:
        text, plain, note = _guard(lambda: ad(q, mode, ctx), tmo + 2.0, stop)
    except _Halt as h:
        note = h.code
    except Exception as e:
        note = ("error: %s: %s" % (type(e).__name__, str(e).replace("\n", " ")[:80])).strip()
        log("%s failed: %s" % (name, note))
    R["secs"] = round(time.time() - t0, 2)
    if text or plain:
        _classify(R, text, plain, q)
    else:
        R["note"] = "no-result" if note == "ran" else note
    _note_health(name, R["note"])
    return R


def _classify(R, text, plain, q):
    if text:
        lrc, meta, n = clean_lrc(text)
        if n >= 4:
            R["meta"], R["duration"] = meta, _length(meta)
            R.update(raw=lrc, note="ok", mismatch=_wrong_song(meta, q))
            return
        plain = plain or text
    p = clean_plain(plain)
    if _lines(p) >= 4:
        R["plain"], R["note"] = p, "plain-only"
    else:
        R["note"] = "bad-lrc" if text else "no-result"


# ------------------------------------------------------------------ the chain
def run_chain(queries, verify, stop=None, progress=None, names=None, budget=150.0):
    """Ask the providers one after the other until one gives lyrics that fit the song.
    queries   [{'artist','title','album','duration','path'}, ...]  the verified creator first, then alternative spellings (at most 2 are used per provider)
    verify    verify(cand) -> {'conf': 0..1 or None, 'final': bool, ...}   the audio fit of one candidate (conf None: the audio could not tell;
              final True: no audio to check against, so the first lyrics that parse are taken)
    Returns {'best': {'cand', 'conf', 'check', 'rank', 'provider'} or None, 'trace': [...], 'plains': [...], 'seen': {text keys already fitted}}"""
    names = list(order() if names is None else names)
    trace, held, plains, seen = [], [], [], {}
    t_start = time.time()
    for name in names:
        if (stop is not None and stop()) or time.time() - t_start > budget:
            break
        if progress:
            progress(name)
        got, last = None, None
        for q in queries[:2]:
            last = fetch(name, q, "synced", stop)
            if last["plain"]:
                plains.append(last)
            if last["raw"]:
                got = last
                break
            if last["note"] in ("not-installed", "python-too-old", "cooldown", "no-plugin", "no-audio", "timeout", "stopped") or last["note"].startswith("error"):
                break                                                       # another spelling will not change that
        entry = {"provider": name, "result": (got or last or {}).get("note", "no-result"), "secs": round(sum([(got or last or {}).get("secs", 0.0)]), 2), "conf": None}
        trace.append(entry)
        if got is None:
            continue
        key = text_key(got["raw"])
        if key in seen:                                                     # lrcdl, lyriq and syncedlyrics' Lrclib share one database: do not fit the same text twice
            entry["result"] = "duplicate"
            h = held[seen[key]]
            if h["mismatch"] and not got.get("mismatch"):                   # a second provider gives the same text under the right title: the flag was a false alarm
                h["mismatch"], h["conf"] = False, h["raw_conf"]
                h["rank"] = h["conf"] if h["conf"] is not None else 0.15
                h["entry"]["conf"], h["entry"]["mismatch"] = h["conf"], False
                h["entry"]["result"] = "ok" if (h["conf"] is None or h["conf"] >= OK) else "low-fit"
                if h["conf"] is not None and h["conf"] >= GOOD:
                    break
            continue
        cand = {"source": name, "provider": name, "artist": queries[0].get("artist", ""), "title": queries[0].get("title", ""), "duration": got["duration"],
                "synced": True, "raw": got["raw"], "score": 1.0}
        try:
            chk = verify(cand) or {}
        except Exception as e:
            log("verify failed for %s: %r" % (name, e))
            entry["result"] = "fit-error"
            continue
        conf = raw_conf = chk.get("conf")
        if got.get("mismatch") and conf is not None:
            conf = round(conf * MISMATCH_FACTOR, 3)
            entry["mismatch"] = True
        entry["conf"] = conf
        entry["result"] = "ok" if (conf is None or conf >= OK) else "low-fit"
        seen[key] = len(held)
        held.append({"cand": cand, "conf": conf, "raw_conf": raw_conf, "mismatch": bool(entry.get("mismatch")), "entry": entry, "check": chk,
                     "rank": conf if conf is not None else 0.15, "provider": name, "i": len(held)})
        if chk.get("final") or (conf is not None and conf >= GOOD):
            break
    best = max(held, key=lambda h: (h["rank"], -h["i"])) if held else None
    return {"best": best, "trace": trace, "plains": plains, "seen": seen}


def plain_text(queries, plains=(), stop=None, names=None):
    """Lyrics WITHOUT timestamps, as a last resort: what the chain already saw, else every provider once more in plain mode. -> (text, provider) or ('', '')."""
    for R in plains:
        if R.get("plain"):
            return R["plain"], R["provider"]
    for name in list(order() if names is None else names):
        if stop is not None and stop():
            break
        R = fetch(name, queries[0], "plain", stop)
        if R["plain"]:
            return R["plain"], name
        if R["raw"]:                                                        # asked for plain, got timed lines: still lyrics
            return clean_plain(R["raw"]), name
    return "", ""


def trace_line(trace, lang="en"):
    """'syncedlyrics ✗ not installed → lrcdl ✗ nothing found → lyriq ✓ 82 %' for the status line."""
    help_ = NOTE_ID if lang == "id" else NOTE_HELP
    parts = []
    for t in trace or []:
        r = t.get("result", "")
        if r == "ok":
            mark = "✓ %d%%" % round(t["conf"] * 100) if t.get("conf") is not None else ("· " + ("tanpa cek audio" if lang == "id" else "not checked against audio"))
        else:
            mark = "✗ " + (help_.get(r) or r.replace("error: ", "error ")[:40])
            if r == "low-fit" and t.get("conf") is not None:
                mark += " (%d%%)" % round(t["conf"] * 100)
        if t.get("mismatch"):
            mark += " (" + ("judul lain" if lang == "id" else "other title") + ")"
        parts.append("%s %s" % (t.get("provider", "?"), mark))
    return " → ".join(parts)


# ------------------------------------------------------------------ status, install, live test (rofpalys lyrics providers ...)
def _version(name):
    try:
        from importlib import metadata
        return metadata.version(name)
    except Exception:
        return ""


def status():
    """One row per provider: {'name', 'position' (in the order, 0 = off), 'installed', 'module', 'cli', 'version', 'python_ok', 'resting', 'note'}"""
    ordr = order()
    rows = []
    for n in DEFAULT_ORDER:
        mod = importlib.util.find_spec(n) is not None if _py_ok(n) else False
        cli = shutil.which(n) or ""
        note = ""
        if not _py_ok(n):
            note = "needs Python %d.%d+ (this is %d.%d)" % (MIN_PY[n] + sys.version_info[:2])
        elif not (mod or cli):
            note = "pip install " + n
        elif n == "librelyrics":
            note = "needs a search plugin (see: librelyrics plugin list)"
        rows.append({"name": n, "position": ordr.index(n) + 1 if n in ordr else 0, "installed": bool(mod or cli), "module": bool(mod), "cli": cli, "version": _version(n) if mod else "",
                     "python_ok": _py_ok(n), "resting": _cooling(n), "note": note})
    return rows


def format_status(lang="en"):
    id_ = lang == "id"
    rows = status()
    out = [("Urutan: " if id_ else "Order: ") + (" → ".join(order()) or ("(mati: hanya cadangan bawaan)" if id_ else "(off: built-in safety net only)")) + "  → LRCLIB / YouTube / lyrics.ovh"]
    for r in rows:
        state = ("✓ %s" % (r["version"] or ("terpasang" if id_ else "installed"))) if r["installed"] else "✗"
        if r["resting"]:
            state += "  (" + ("istirahat" if id_ else "resting") + ")"
        out.append("  %d. %-13s %s%s" % (r["position"], r["name"], state, ("   " + r["note"]) if r["note"] else ""))
    return "\n".join(out)


def install(names=None, extra=(), progress=None):
    """pip install the providers that are missing. -> {name: (ok, message)}. `extra` goes to pip (for example --break-system-packages)."""
    say = progress or (lambda m: None)
    res = {}
    for n in (names or list(DEFAULT_ORDER)):
        if n not in MIN_PY:
            res[n] = (False, "unknown provider")
            continue
        if not _py_ok(n):
            res[n] = (False, "needs Python %d.%d or newer" % MIN_PY[n])
            continue
        if importlib.util.find_spec(n) is not None:
            res[n] = (True, "already installed")
            continue
        say("pip install " + n)
        try:
            p = subprocess.run([sys.executable, "-m", "pip", "install", n] + list(extra), capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
            txt = (p.stdout + p.stderr).decode("utf-8", "replace")
        except Exception as e:
            res[n] = (False, "%s: %s" % (type(e).__name__, e))
            continue
        if p.returncode == 0:
            res[n] = (True, "installed")
        elif "externally-managed" in txt:
            res[n] = (False, "this Python is managed by the system: use  rofpalys lyrics providers install --break-system-packages  or a virtual environment / pipx")
        else:
            res[n] = (False, (txt.strip().splitlines() or ["pip failed"])[-1][:160])
    reset()
    return res


def live_test(q, names=None, stop=None):
    """Ask every provider the same question and say what came back (no audio fit). -> [{'provider', 'note', 'lines', 'synced', 'secs'}]"""
    rows = []
    for n in (names or list(DEFAULT_ORDER)):
        R = fetch(n, q, "synced", stop)
        rows.append({"provider": n, "note": R["note"], "lines": _lines(R["raw"] or R["plain"]), "synced": bool(R["raw"]), "secs": R["secs"]})
    return rows


# ------------------------------------------------------------------ self-test: no packages, no internet (the adapters are replaced by fakes)
def selftest(verbose=True):
    ok_all = [True]

    def check(name, cond):
        if not cond:
            ok_all[0] = False
        if verbose or not cond:
            print("  [%s] %s" % ("ok" if cond else "FAIL", name))
    lrc = "\n".join("[00:%02d.00]line number %d goes here" % (10 + 4 * i, i) for i in range(8))
    other = "\n".join("[00:%02d.00]a different song %d" % (10 + 4 * i, i) for i in range(8))
    check("order default is syncedlyrics first", parse_order(None) is None and list(DEFAULT_ORDER)[0] == "syncedlyrics")
    check("order parse", parse_order("lyriq > syncedlyrics, nonsense, lrcdl") == ["lyriq", "syncedlyrics", "lrcdl"] and parse_order("off") == [] and parse_order("  ") is None)
    c, m, n = clean_lrc("[ti:Song]\n[ar:Someone]\n[length: 03:21]\n[offset:+500]\n[00:10.00]<00:10.00> hello <00:10.40> world\n[00:14.50]second\n[00:20.00]third\n[00:24.00]fourth\n")
    check("clean_lrc: header, offset, word tags", n == 4 and m.get("ti") == "Song" and _length(m) == 201 and c.split("\n")[0] == "[00:09.50]hello world")
    check("clean_lrc: plain text is not synced", clean_lrc("just words\nmore words\neven more\nand more")[2] == 0)
    check("similar", similar("Blinding Lights", "blinding  lights!") == 1.0 and similar("Blinding Lights", "Hello") < 0.45)
    q = {"artist": "A", "title": "Blinding Lights", "album": "", "duration": 200.0, "path": None}
    calls = []
    saved = dict(_ADAPTERS)

    def mk(res, name):
        def f(q_, mode, ctx):
            calls.append((name, mode))
            r = res(q_, mode) if callable(res) else res
            if isinstance(r, Exception):
                raise r
            return r
        return f
    try:
        reset()
        _ADAPTERS.update({"syncedlyrics": mk(("", "", "not-installed"), "syncedlyrics"), "lrcdl": mk(("", "", "no-audio"), "lrcdl"),
                          "lyriq": mk((lrc, "", "ran"), "lyriq"), "librelyrics": mk((other, "", "ran"), "librelyrics")})
        r = run_chain([q], lambda cand: {"conf": 0.8}, names=list(DEFAULT_ORDER))
        check("chain: failover to the first provider that fits", r["best"]["provider"] == "lyriq" and [t["result"] for t in r["trace"]] == ["not-installed", "no-audio", "ok"])
        check("chain: stops after a good fit (librelyrics not asked)", ("librelyrics", "synced") not in calls)
        check("trace line", "syncedlyrics ✗ not installed" in trace_line(r["trace"]) and "lyriq ✓ 80%" in trace_line(r["trace"]))
        calls[:] = []
        _ADAPTERS.update({"syncedlyrics": mk((lrc, "", "ran"), "syncedlyrics"), "lyriq": mk((lrc, "", "ran"), "lyriq"), "librelyrics": mk((other, "", "ran"), "librelyrics")})
        reset()
        r = run_chain([q], lambda cand: {"conf": 0.45 if "different" not in cand["raw"] else 0.9}, names=["syncedlyrics", "lyriq", "librelyrics"])
        check("chain: a middling fit gets a second opinion, a better fit wins", r["best"]["provider"] == "librelyrics" and [t["result"] for t in r["trace"]] == ["ok", "duplicate", "ok"])
        reset()
        r = run_chain([q], lambda cand: {"conf": 0.2}, names=["syncedlyrics", "librelyrics"])
        check("chain: nothing fits -> the best of the bad is returned, trace says low-fit", r["best"] is not None and r["trace"][0]["result"] == "low-fit")
        reset()
        r = run_chain([q], lambda cand: {"conf": None, "final": True}, names=["syncedlyrics", "lyriq"])
        check("chain: no audio to check against -> the first lyrics that parse", r["best"]["provider"] == "syncedlyrics" and len(r["trace"]) == 1)
        reset()
        _ADAPTERS.update({"syncedlyrics": mk(RuntimeError("boom"), "syncedlyrics")})
        for _ in range(3):
            fetch("syncedlyrics", q)
        n0 = len(calls)
        res = fetch("syncedlyrics", q)
        check("a provider that keeps failing rests (no call, note cooldown)", res["note"] == "cooldown" and len(calls) == n0)
        reset()
        _ADAPTERS.update({"syncedlyrics": mk(("", "", "ran"), "syncedlyrics"), "lyriq": mk(("", "plain words here\nand more of them\nthird line\nfourth line", "ran"), "lyriq")})
        r = run_chain([q], lambda cand: {"conf": 0.9}, names=["syncedlyrics", "lyriq"])
        t, who = plain_text([q], r["plains"], names=["syncedlyrics", "lyriq"])
        check("plain-only text is kept for the last resort", r["best"] is None and who == "lyriq" and _lines(t) == 4)
        reset()
        _ADAPTERS.update({"syncedlyrics": mk(("[ti:Another Title]\n" + lrc, "", "ran"), "syncedlyrics"), "lyriq": mk((other, "", "ran"), "lyriq")})
        check("a header that names another title is flagged", fetch("syncedlyrics", q)["mismatch"] is True and fetch("lyriq", q)["mismatch"] is False)
        reset()
        r = run_chain([q], lambda cand: {"conf": 0.9}, names=["syncedlyrics", "lyriq"])
        check("chain: the provider with the right title beats a flagged one (fit halved, no veto)", r["best"]["provider"] == "lyriq" and r["trace"][0].get("mismatch") and r["trace"][0]["conf"] == 0.45)
        reset()
        _ADAPTERS.update({"lyriq": mk((lrc, "", "ran"), "lyriq")})
        r = run_chain([q], lambda cand: {"conf": 0.9}, names=["syncedlyrics", "lyriq"])
        check("chain: the same text under the right title clears the flag", r["best"]["provider"] == "syncedlyrics" and r["best"]["conf"] == 0.9 and r["trace"][1]["result"] == "duplicate")
        reset()
        r = run_chain([q], lambda cand: {"conf": 0.9}, names=["syncedlyrics"])
        check("chain: a flagged provider is still used when nothing better exists", r["best"] is not None and r["best"]["provider"] == "syncedlyrics")
        reset()

        def slow(q_, mode):
            time.sleep(5)
            return (lrc, "", "ran")
        _ADAPTERS.update({"syncedlyrics": mk(slow, "syncedlyrics")})
        t0 = time.time()
        res = fetch("syncedlyrics", q, timeout=0.5)
        check("a hanging provider is given up on (timeout)", res["note"] == "timeout" and time.time() - t0 < 4.0)
    finally:
        _ADAPTERS.clear()
        _ADAPTERS.update(saved)
        reset()
    return ok_all[0]


# END-OF-FILE rofpalys_CyroKayAI_providers.py

