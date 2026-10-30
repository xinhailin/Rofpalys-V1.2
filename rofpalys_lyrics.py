#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - lyrics: find, download, parse, cache (no UI, no engine)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Lyrics v1.1 - the brain is rofpalys_CyroKayAI_lyric.py: it finds out WHO made the song, checks the internet, listens to the recording and
fits the lyrics to the real voice (see that file). This file keeps the sources, the parser and the cache, and fetch_best() asks CyroKayAI first;
if CyroKayAI is missing or fails, the classic order below is used, exactly as before.
Where lyrics come from, in order (the first that answers wins):
   1. a .lrc / .txt file next to the song, then the cache of earlier downloads
   2. LRCLIB exact match (artist + title + length)      -> time-synced lyrics (karaoke)
   3. LRCLIB search, best match by title/artist/length  -> synced if possible
   4. YouTube subtitles through yt-dlp                  -> time-synced, but auto-captions can contain mistakes
   5. lyrics.ovh                                        -> plain text only
No account, no API key and no paid AI is needed: the 'smart' part is the matching (similar titles, typos, song length).
Instrumental parts (a drum solo, an intro, a long gap between two lines, '[Music]' in captions) become a melody marker: 🎶 (strong music) or 🎵 (soft music)."""
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import rofpalys_library as lib

__version__ = "1.2"
NOTE_HI, NOTE_LO = "🎶", "🎵"                       # melody markers: strong music / soft music
NOTE = NOTE_HI
_TEXT_NOTES = {"🎶": "♫", "🎵": "♪"}                  # for a terminal or a font without emoji: set ROFPALYS_NOTES=text (or call set_note_style("text"))
UA = "Rofpalys-lyrics/" + __version__
LYRICS_DIR = os.path.join(lib.CACHE_DIR, "lyrics")
_STAMP = re.compile(r"\[(\d{1,3}):(\d{2}(?:[.:]\d{1,3})?)\]")
_LRC_LINE = re.compile(r"^((?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\])+)(.*)$")
_NOTE_ALL = ("🎶", "🎵", "♫", "♪")
_BREAK_WORDS = {"music", "instrumental", "intro", "outro", "solo", "musik", "musica", "musique", "interlude", "beat"}


# ------------------------------------------------------------------ names
def guess(path):
    """(artist, title) from the file name: 'Artist - Title (Official Video)' -> ('Artist', 'Title')."""
    name = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
    name = re.sub(r"[\(\[][^)\]]*(official|video|lyric|audio|mv|hd|4k|visuali[sz]er|remaster)[^)\]]*[\)\]]", "", name, flags=re.I)
    name = re.sub(r"^\s*\d{1,3}\s*[-._)]\s+", "", name)
    name = re.sub(r"\s+", " ", name).strip(" -")
    if " - " in name:
        a, t = name.split(" - ", 1)
        return a.strip(), t.strip()
    return "", name


def _sim(a, b):
    a, b = lib.norm(a), lib.norm(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


# ------------------------------------------------------------------ parsing LRC / plain text
def set_note_style(style="emoji"):
    """'emoji' -> 🎶 / 🎵   'text' -> ♫ / ♪  (for fonts without emoji)."""
    global NOTE_HI, NOTE_LO, NOTE
    NOTE_HI, NOTE_LO = ("♫", "♪") if style == "text" else ("🎶", "🎵")
    NOTE = NOTE_HI


if os.environ.get("ROFPALYS_NOTES", "").lower() == "text":
    set_note_style("text")


def is_note(text):
    return (text or "").strip() in _NOTE_ALL


def canon_note(text):
    """Any of the four note symbols -> the symbol of the current style (strong 🎶/♫, soft 🎵/♪)."""
    return NOTE_HI if (text or "").strip() in ("🎶", "♫") else NOTE_LO


def is_break_text(text):
    t = re.sub(r"[\W_]+", " ", text).strip().lower()
    return t == "" or t in _BREAK_WORDS or text.strip() in _NOTE_ALL


def parse(raw):
    """-> (lines, synced). synced=True: lines = [(seconds, text)] sorted; text '' marks an instrumental part and a note symbol (🎶 / 🎵) is a melody marker.
    synced=False: lines = [text, ...]."""
    plain, synced, offset = [], [], 0.0
    for line in raw.splitlines():
        line = line.strip()
        mo = re.match(r"^\[offset:\s*([+-]?\d+)\s*\]", line, re.I)
        if mo:
            offset = int(mo.group(1)) / 1000.0
            continue
        m = _LRC_LINE.match(line)
        if m:
            text = re.sub(r"<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>", "", m.group(2)).strip()      # enhanced LRC word stamps
            if is_note(text):
                text = canon_note(text)
            elif is_break_text(text):
                text = ""
            for mm, ss in _STAMP.findall(m.group(1)):
                synced.append((max(0.0, int(mm) * 60 + float(ss.replace(":", ".")) - offset), text))
        elif line and not re.match(r"^\[[A-Za-z]+:.*\]$", line):
            plain.append(line)
    if synced:
        synced.sort(key=lambda x: x[0])
        return synced, True
    return plain, False


def est_len(text):
    """How long a sung line probably lasts (LRC has start times only)."""
    words = max(len(text.split()), len(text) / 3.0)
    return max(2.0, min(6.5, 0.4 * words + 1.2))


def add_breaks(lines, min_gap=4.5):
    """Put a melody marker where nobody sings: before the first line, in long gaps, after the last line, and where the file had an empty line.
    Markers that are already there (🎶 / 🎵, e.g. from CyroKayAI) are kept as they are."""
    ls = [(t, text or NOTE) for t, text in lines]
    out = []
    if ls and ls[0][0] > 3.5 and not is_note(ls[0][1]):
        out.append((0.0, NOTE))
    for i, (t, text) in enumerate(ls):
        if is_note(text) and out and out[-1][1] == text:
            continue
        out.append((t, text))
        if not is_note(text) and i + 1 < len(ls):
            end = t + est_len(text)
            if ls[i + 1][0] - end > min_gap and not is_note(ls[i + 1][1]):
                out.append((end, NOTE))
    if ls and not is_note(ls[-1][1]):
        out.append((ls[-1][0] + est_len(ls[-1][1]) + 0.5, NOTE))
    return out


def to_lrc(lines):
    return "\n".join("[%02d:%05.2f]%s" % (int(t // 60), t % 60, text) for t, text in lines)


# ------------------------------------------------------------------ cache
def _safe(path):
    return re.sub(r'[\\/:*?"<>|]', "_", os.path.splitext(os.path.basename(path))[0])


def cache_path(path):
    return os.path.join(LYRICS_DIR, _safe(path) + ".lrc")


def sidecar(path):
    base = os.path.splitext(path)[0]
    for ext in (".lrc", ".txt"):
        if os.path.isfile(base + ext):
            return base + ext
    return ""


def write_cache(path, raw, source):
    try:
        os.makedirs(LYRICS_DIR, exist_ok=True)
        with open(cache_path(path), "w", encoding="utf-8") as f:
            f.write("[by:Rofpalys/%s]\n%s\n" % (source, raw))
    except OSError:
        pass


def read_cache(path):
    """(raw, source) or ('', '')."""
    p = cache_path(path)
    if not os.path.isfile(p):
        return "", ""
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError:
        return "", ""
    m = re.match(r"^\[by:Rofpalys/([^\]]*)\]\n", raw)
    src = m.group(1) if m else "cache"
    try:
        if "melody" in src and time.time() - os.path.getmtime(p) > (600 if "offline" in src else 7 * 86400):
            return "", ""                                  # a melody-only track is not final: look for real lyrics again (10 min if the internet was off, else a week)
    except OSError:
        pass
    return (raw[m.end():], src) if m else (raw, src)


def delete_cache(path):
    try:
        os.remove(cache_path(path))
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ online sources
def _http(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _cand_from_lrclib(x):
    synced = (x.get("syncedLyrics") or "").strip()
    plain = (x.get("plainLyrics") or "").strip()
    raw = synced or plain or ((("[00:00.00]" + NOTE)) if x.get("instrumental") else "")
    return {"source": "LRCLIB", "artist": x.get("artistName", ""), "title": x.get("trackName", ""), "duration": float(x.get("duration") or 0),
            "synced": bool(synced) or bool(x.get("instrumental")), "raw": raw}


def lrclib_exact(artist, title, duration):
    if not (artist and title):
        return None
    q = {"artist_name": artist, "track_name": title}
    if duration and duration > 0:
        q["duration"] = int(round(duration))
    try:
        c = _cand_from_lrclib(_http("https://lrclib.net/api/get?" + urllib.parse.urlencode(q)))
        return c if c["raw"] else None
    except urllib.error.HTTPError:
        return None
    except Exception:
        return None


def lrclib_search(artist, title, duration):
    queries = []
    if artist:
        queries.append({"track_name": title, "artist_name": artist})
    queries.append({"q": ("%s %s" % (artist, title)).strip() or title})
    if artist:
        queries.append({"q": title})
    seen, out = set(), []
    for q in queries:
        try:
            data = _http("https://lrclib.net/api/search?" + urllib.parse.urlencode(q))
        except Exception:
            continue
        for x in data if isinstance(data, list) else []:
            c = _cand_from_lrclib(x)
            key = (lib.norm(c["artist"]), lib.norm(c["title"]), int(c["duration"]))
            if c["raw"] and key not in seen:
                seen.add(key)
                c["score"] = score(c, artist, title, duration)
                out.append(c)
    out.sort(key=lambda c: -c["score"])
    return out


def score(c, artist, title, duration):
    """0..1.2: how well a candidate matches what we look for (title, artist, song length; synced lyrics get a bonus)."""
    s = 0.6 * _sim(title, c["title"]) + (0.2 * _sim(artist, c["artist"]) if artist else 0.2 * 0.7)
    if duration and duration > 0 and c.get("duration"):
        d = abs(duration - c["duration"])
        s += 0.2 if d <= 3 else 0.12 if d <= 8 else 0.04 if d <= 20 else 0.0
    else:
        s += 0.08
    return s + (0.15 if c.get("synced") else 0.0)


def lyrics_ovh(artist, title):
    if not (artist and title):
        return None
    try:
        data = _http("https://api.lyrics.ovh/v1/%s/%s" % (urllib.parse.quote(artist, safe=""), urllib.parse.quote(title, safe="")), timeout=10)
        raw = (data.get("lyrics") or "").replace("\r\n", "\n").strip()
        return {"source": "lyrics.ovh", "artist": artist, "title": title, "duration": 0.0, "synced": False, "raw": raw} if len(raw) > 40 else None
    except Exception:
        return None


# ------------------------------------------------------------------ YouTube subtitles (through yt-dlp)
def _vtt_to_lines(text):
    out, prev = [], ""
    for block in re.split(r"\n\s*\n", text):
        m = re.search(r"(\d+):(\d{2}):(\d{2})[.,](\d{3}) --> ", block) or re.search(r"(\d{2}):(\d{2})[.,](\d{3}) --> ", block)
        if not m:
            continue
        g = m.groups()
        t = (int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000.0) if len(g) == 4 else (int(g[0]) * 60 + int(g[1]) + int(g[2]) / 1000.0)
        body = block[m.end():].split("\n", 1)[1:] and block[m.end():].split("\n", 1)[1] or ""
        rolling = bool(re.search(r"<\d{2}:\d{2}|<c[ >.]", body))                   # auto-captions repeat the previous line: keep only the new one
        lines = [re.sub(r"<[^>]+>", "", ln).strip() for ln in body.split("\n")]
        lines = [ln for ln in lines if ln]
        txt = (lines[-1] if rolling else " ".join(lines)) if lines else ""
        if txt and txt != prev:
            out.append((t, txt))
            prev = txt
    return out


def _json3_to_lines(text):
    out, prev = [], ""
    try:
        events = json.loads(text).get("events", [])
    except ValueError:
        return out
    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        txt = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
        if txt and txt != prev and not (prev and prev.endswith(txt)):
            out.append((ev.get("tStartMs", 0) / 1000.0, txt))
            prev = txt
    return out


def youtube_captions(artist, title, langs=("en",), stop=None, timeout=100):
    """Subtitles of the best-matching YouTube lyric video as LRC text ('' if none / yt-dlp missing)."""
    if not shutil.which("yt-dlp") or not title:
        return ""
    tmp = tempfile.mkdtemp(prefix="rofpalys_sub_")
    try:
        sl = ",".join("%s.*" % l for l in list(langs) + ["en"]) + ",.*-orig"
        cmd = ["yt-dlp", "--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", sl, "--sub-format", "json3/vtt",
               "--socket-timeout", "15", "--no-warnings", "--match-filter", "duration<=900", "-o", os.path.join(tmp, "%(id)s.%(ext)s"), "--",
               "ytsearch1:%s %s lyrics" % (artist, title)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout)
        except Exception:
            return ""
        if stop and stop():
            return ""
        files = sorted(os.listdir(tmp), key=lambda f: (not f.endswith(".json3"), ".orig" in f or "-orig" in f, f))   # json3 first, original language first
        for f in files:
            try:
                with open(os.path.join(tmp, f), encoding="utf-8", errors="replace") as fh:
                    data = fh.read()
            except OSError:
                continue
            lines = _json3_to_lines(data) if f.endswith(".json3") else _vtt_to_lines(data) if f.endswith(".vtt") else []
            if len(lines) >= 4:
                return to_lrc(lines)
        return ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ the public entry points
_CK = [None, False]


def _ck():
    """The brain (rofpalys_CyroKayAI_lyric.py), or None when the file is missing / broken: the classic code below then works as before."""
    if not _CK[1]:
        _CK[1] = True
        try:
            import rofpalys_CyroKayAI_lyric as ck
            _CK[0] = ck
        except Exception:
            _CK[0] = None
    return _CK[0]


def is_cyrokay(source):
    return "CyroKayAI" in (source or "")


CK_CURRENT = 3                                      # the CyroKayAI generation that makes lyrics now (rofpalys_CyroKayAI_ears.ALGO_N)


def ck_version(source):
    """0 = not made by CyroKayAI, 1 = CyroKayAI 1 (its source reads 'CyroKayAI · LRCLIB'), 2+ = 'CyroKayAI 3 · syncedlyrics' ..."""
    m = re.search(r"CyroKayAI (\d+)", source or "")
    return int(m.group(1)) if m else (1 if "CyroKayAI" in (source or "") else 0)


def is_current(source):
    """True when the lyrics were made by the current CyroKayAI; anything older is made again once (the automatic deep reset)."""
    return ck_version(source) >= CK_CURRENT


def fetch_best(artist, title, duration, allow_youtube=True, langs=("en",), stop=None, path=None, progress=None):
    """(raw, source, synced) of the best lyrics for the song that is playing: CyroKayAI first (creator check -> internet check -> fetch -> fit to the
    music -> melody markers; no lyrics at all -> a melody-only track), the classic search if CyroKayAI is not available.
    `path` is the audio file (default: the song the player is playing now, when its name matches artist/title)."""
    ck = _ck() if os.environ.get("ROFPALYS_CYROKAY", "1") != "0" else None
    if ck is not None:
        try:
            r = ck.auto_lyrics(path or ck.playing_path(artist, title), artist, title, duration, allow_youtube, langs, stop, progress)
            if r and r.get("raw"):
                return r["raw"], r["source"], bool(r["synced"])
            if r and (r.get("stopped") or r.get("online_done")):
                return "", "", False
        except Exception as e:
            ck.log("auto_lyrics failed: %r" % (e,))
    return fetch_best_classic(artist, title, duration, allow_youtube, langs, stop)


def fit_to_song(raw, path=None, stop=None):
    """Lyrics the user picked by hand (or loaded from a file) -> fitted to the real recording by CyroKayAI. (raw, confidence or None)."""
    ck = _ck()
    if ck is None or not raw:
        return raw, None
    try:
        r = ck.fit_raw(raw, path or ck.playing_path("", ""), stop=stop)
        if r and r.get("raw"):
            return r["raw"], r.get("confidence")
    except Exception as e:
        ck.log("fit_to_song failed: %r" % (e,))
    return raw, None


def fetch_best_classic(artist, title, duration, allow_youtube=True, langs=("en",), stop=None):
    """(raw, source, synced) of the best lyrics found, or ('', '', False)."""
    stop = stop or (lambda: False)
    c = lrclib_exact(artist, title, duration)
    if c and c["synced"]:
        return c["raw"], "LRCLIB", True
    cands = lrclib_search(artist, title, duration) if not stop() else []
    good = [x for x in cands if x["score"] >= 0.62]
    synced = [x for x in good if x["synced"]]
    if synced:
        return synced[0]["raw"], "LRCLIB", True
    plain = c or (good[0] if good else None)
    if allow_youtube and not stop():
        raw = youtube_captions(artist, title, langs, stop)
        if raw and not plain:                               # captions only when there is nothing better: official text beats auto-captions
            return raw, "YouTube captions", True
    if plain:
        return plain["raw"], "LRCLIB", False
    o = lyrics_ovh(artist, title) if not stop() else None
    return (o["raw"], "lyrics.ovh", False) if o else ("", "", False)


def search_candidates(artist, title, duration, youtube=False, langs=("en",)):
    """For the 'find lyrics' dialog: a list of candidates the user can pick from (best first)."""
    out = lrclib_search(artist, title, duration)[:10]
    ck = _ck()
    pv = getattr(ck, "PV", None) if ck is not None else None
    if pv is not None:                                      # the first provider that answers (syncedlyrics by default) goes to the top of the list
        try:
            q = {"artist": artist, "title": title, "album": "", "duration": duration, "path": ""}
            for name in pv.order():
                if name == "lrcdl":
                    continue                                # lrcdl needs the audio file: it works in the automatic chain, not in the dialog
                R = pv.fetch(name, q, "synced")
                if R["raw"]:
                    out.insert(0, {"source": name, "artist": artist, "title": title, "duration": R["duration"], "synced": True, "raw": R["raw"], "score": 1.0})
                    break
        except Exception:
            pass
    o = lyrics_ovh(artist, title)
    if o:
        out.append(o)
    if youtube:
        raw = youtube_captions(artist, title, langs)
        if raw:
            out.append({"source": "YouTube captions", "artist": artist, "title": title, "duration": 0.0, "synced": True, "raw": raw})
    return out

# END-OF-FILE rofpalys_lyrics.py

