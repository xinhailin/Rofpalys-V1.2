#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - media: cover art + music video for the playing song (find locally, download automatically, cache, stream frames)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""No UI code here. The GUI asks for the current Track and reads its state; everything slow runs in background threads.

Cover art, in this order:  embedded in the file -> picture next to the song / album folder -> cache -> online (iTunes, then Deezer).
Video, in this order:      the song file itself (if it has video) -> video with the same name -> cache -> yt-dlp search.
Only the cache folder is ever deleted by the reset functions. Your own files are never touched."""
import collections
import difflib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import rofpalys_engine as E
import rofpalys_library as lib

MEDIA_DIR = os.path.join(lib.CACHE_DIR, "media")
ART_DIR, VID_DIR, SCALED_DIR = (os.path.join(MEDIA_DIR, n) for n in ("art", "video", "scaled"))
INDEX_FILE = os.path.join(MEDIA_DIR, "index.json")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
VID_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v")
FOLDER_ART = ("cover", "folder", "album", "front", "artwork", "albumart", "thumb")
NEG_TTL = 3 * 24 * 3600                                  # do not search again for 3 days after a miss (reset clears this)
_lock = threading.RLock()
_cur = None
_index = None
_meta = {}
_scaling = set()


def _noise_free(s):
    s = s.replace("_", " ")
    s = re.sub(r'[\(\[][^)\]]*(official|video|lyric|audio|mv|hd|4k|visuali[sz]er|remaster)[^)\]]*[\)\]]', '', s, flags=re.I)
    s = re.sub(r'^\s*\d{1,3}\s*[-._)]\s+', '', s)           # leading track number
    return re.sub(r'\s+', ' ', s).strip(" -")


def name_meta(path):
    """(artist, title) guessed from the file name: 'Artist - Title'."""
    base = _noise_free(os.path.splitext(os.path.basename(path))[0])
    if " - " in base:
        a, t = base.split(" - ", 1)
        return a.strip(), t.strip()
    return "", base


def song_meta(path, use_tags=True):
    """(artist, title): ID3/Vorbis tags via ffprobe when available, else the file name."""
    if path in _meta and (_meta[path][2] or not use_tags):
        return _meta[path][:2]
    artist, title = name_meta(path)
    tagged = False
    if use_tags and shutil.which("ffprobe"):
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist,album_artist", "-of", "json", path],
                                 capture_output=True, text=True, timeout=5).stdout
            tags = {k.lower(): v for k, v in (json.loads(out or "{}").get("format", {}).get("tags", {}) or {}).items()}
            ta, tt = (tags.get("artist") or tags.get("album_artist") or "").strip(), (tags.get("title") or "").strip()
            if ta and tt:
                artist, title = ta, tt
        except Exception:
            pass
    if use_tags:
        tagged = True
    _meta[path] = (artist, title, tagged)
    return artist, title


def _key(artist, title, path):
    raw = ("%s|%s" % (artist.lower(), title.lower())) if (artist or title) else os.path.basename(path).lower()
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


# ------------------------------------------------------------------ index (what was found / not found)
def _ensure_dirs():
    for d in (ART_DIR, VID_DIR, SCALED_DIR):
        os.makedirs(d, exist_ok=True)


def _idx():
    global _index
    with _lock:
        if _index is None:
            try:
                with open(INDEX_FILE, encoding="utf-8") as f:
                    _index = json.load(f)
            except (OSError, ValueError):
                _index = {}
        return _index


def _idx_set(key, **kw):
    with _lock:
        ent = _idx().setdefault(key, {})
        ent.update(kw)
        try:
            _ensure_dirs()
            with open(INDEX_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(_index, f)
            os.replace(INDEX_FILE + ".tmp", INDEX_FILE)
        except OSError:
            pass


def _recent(ts):
    return bool(ts) and time.time() - ts < NEG_TTL


# ------------------------------------------------------------------ the current track
class Track:
    def __init__(self, path):
        self.path = path
        self.artist, self.title = name_meta(path)          # fast guess now; refined with tags in the worker
        self.key = _key(self.artist, self.title, path)
        self.art, self.video, self.avg = "", "", ""
        self.art_state = self.video_state = "idle"          # idle | loading | ready | missing | off
        self.note, self.cancel, self.version = "", False, 0

    def bump(self):
        self.version += 1


def current():
    return _cur


def on_song(path):
    """Call whenever the playing song changes (None when playback ended)."""
    global _cur
    with _lock:
        if _cur is not None:
            _cur.cancel = True
        _cur = Track(path) if path else None
        t = _cur
    if t:
        threading.Thread(target=_pipeline, args=(t,), daemon=True).start()


def refresh():
    """Settings changed (or reset): run the search again for the current song."""
    t = _cur
    if t:
        on_song(t.path)


def _pipeline(t):
    try:
        t.artist, t.title = song_meta(t.path)
        t.key = _key(t.artist, t.title, t.path)
        t.bump()
        threading.Thread(target=_safe, args=(_art_job, t), daemon=True).start()
        _safe(_video_job, t)
    except Exception as e:
        t.note = "media: %s" % e
        t.bump()


def _safe(fn, t):
    try:
        fn(t)
    except Exception as e:
        t.note = "%s: %s" % (fn.__name__.strip("_"), e)
        if fn is _art_job and t.art_state in ("idle", "loading"):
            t.art_state = "missing"
        if fn is _video_job and t.video_state in ("idle", "loading"):
            t.video_state = "missing"
        t.bump()


# ------------------------------------------------------------------ small helpers
def _http(url, timeout=10, limit=12 * 1024 * 1024, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": E.USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit)
    return data if binary else json.loads(data.decode("utf-8", "replace"))


def _ratio(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() if a and b else 0.0


def _score(artist, title, r_artist, r_title):
    full = _ratio((artist + " " + title).strip(), (r_artist + " " + r_title).strip())
    part = 0.6 * _ratio(title, r_title) + 0.4 * (_ratio(artist, r_artist) if artist else 1.0)
    return max(full, part)


def _is_image(data):
    return data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF" or data[:3] == b"GIF"


def _list_dir(d):
    try:
        return {f.lower(): f for f in os.listdir(d)}
    except OSError:
        return {}


def _has_video_stream(path):
    if not shutil.which("ffprobe"):
        return False
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
                              "-of", "json", path], capture_output=True, text=True, timeout=6).stdout
        return any(not s.get("disposition", {}).get("attached_pic") for s in json.loads(out or "{}").get("streams", []))
    except Exception:
        return False


# ------------------------------------------------------------------ cover art
def _sidecar_art(path):
    d, base = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0].lower()
    names = _list_dir(d)
    for ext in IMG_EXTS:
        if base + ext in names:
            return os.path.join(d, names[base + ext])
    n_audio = sum(1 for f in names if f.endswith(E.AUDIO_EXTS))
    if n_audio <= 40:                                       # an album folder: cover.jpg belongs to the album, not to a mixed Downloads folder
        for n in FOLDER_ART:
            for ext in IMG_EXTS:
                if n + ext in names:
                    return os.path.join(d, names[n + ext])
    return ""


def _embedded_art(t):
    if not shutil.which("ffmpeg") or t.path.lower().endswith(VID_EXTS + (".webm", ".mka")):
        return ""
    _ensure_dirs()
    out = os.path.join(ART_DIR, t.key + "_emb.png")
    if os.path.isfile(out) and os.path.getsize(out) > 500:
        return out
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", t.path, "-an", "-frames:v", "1", out], capture_output=True, timeout=25)
    except Exception:
        pass
    if os.path.isfile(out) and os.path.getsize(out) > 500:
        return out
    try:
        os.remove(out)
    except OSError:
        pass
    return ""


def _find_art_url(t):
    q = ("%s %s" % (t.artist, t.title)).strip()
    best, best_url = 0.0, ""
    try:                                                    # 1) iTunes search: free, no key
        js = _http("https://itunes.apple.com/search?" + urllib.parse.urlencode({"term": q, "media": "music", "entity": "song", "limit": 8}))
        for r in js.get("results", []):
            sc = _score(t.artist, t.title, r.get("artistName", ""), r.get("trackName", ""))
            if sc > best and r.get("artworkUrl100"):
                best, best_url = sc, r["artworkUrl100"].replace("100x100bb", "600x600bb")
    except Exception:
        pass
    if best >= 0.6:
        return best_url
    try:                                                    # 2) Deezer search: free, no key
        js = _http("https://api.deezer.com/search?" + urllib.parse.urlencode({"q": q, "limit": 8}))
        for r in js.get("data", []):
            sc = _score(t.artist, t.title, (r.get("artist") or {}).get("name", ""), r.get("title", ""))
            cover = (r.get("album") or {}).get("cover_big") or (r.get("album") or {}).get("cover_medium")
            if sc > best and cover:
                best, best_url = sc, cover
    except Exception:
        pass
    return best_url if best >= 0.6 else ""


def _download_art(t):
    url = _find_art_url(t)
    if not url or t.cancel:
        return ""
    data = _http(url, timeout=15, binary=True)
    if not _is_image(data):
        return ""
    _ensure_dirs()
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    out = os.path.join(ART_DIR, t.key + ext)
    with open(out, "wb") as f:
        f.write(data)
    return out


def _art_job(t):
    mode = E.media_art
    if mode == "off":
        t.art_state = "off"
        t.bump()
        return
    p = _sidecar_art(t.path) or _embedded_art(t)
    if not p:
        ent = _idx().get(t.key, {})
        if ent.get("art") and os.path.isfile(os.path.join(ART_DIR, ent["art"])):
            p = os.path.join(ART_DIR, ent["art"])
    if not p and mode == "auto" and not _recent(_idx().get(t.key, {}).get("art_tried")):
        t.art_state = "loading"
        t.note = "cover art..."
        t.bump()
        p = _download_art(t)
        _idx_set(t.key, art=os.path.basename(p) if p else "", art_tried=0 if p else time.time())
    if t.cancel:
        return
    if p:
        t.art, t.art_state, t.note = p, "ready", ""
        t.avg = avg_color(p)
    else:
        t.art_state = "missing"
        t.note = "" if mode == "auto" else "no local cover (mode: local only)"
    t.bump()


# ------------------------------------------------------------------ video
def _local_video(t):
    p = t.path
    if p.lower().endswith(VID_EXTS + (".webm", ".mka", ".mp4")) and _has_video_stream(p):
        return p                                            # the song file is a music video itself
    d, base = os.path.dirname(p), os.path.splitext(os.path.basename(p))[0].lower()
    names = _list_dir(d)
    for ext in VID_EXTS:
        if base + ext in names:
            return os.path.join(d, names[base + ext])
    return ""


def _cached_video(t):
    ent = _idx().get(t.key, {})
    if ent.get("video") and os.path.isfile(os.path.join(VID_DIR, ent["video"])):
        return os.path.join(VID_DIR, ent["video"])
    return ""


def _download_video(t):
    if not shutil.which("yt-dlp"):
        t.note = "yt-dlp not installed (pkg install yt-dlp)"
        return ""
    if not shutil.which("ffmpeg"):
        t.note = "ffmpeg not installed (pkg install ffmpeg): video cannot be shown"
        return ""
    _ensure_dirs()
    h = E.video_quality
    fmt = "bv*[height<=%d][ext=mp4]/bv*[height<=%d]/b[height<=%d]" % (h, h, h)
    query = "ytsearch1:%s %s official music video" % (t.artist, t.title)
    cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "--newline", "-f", fmt, "--max-filesize", "%dM" % E.video_max_mb,
           "--match-filter", "duration<=900", "--socket-timeout", "15", "--retries", "2",
           "-o", os.path.join(VID_DIR, t.key + ".%(ext)s"), "--", query.strip()]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    t0 = time.time()
    for ln in proc.stdout:
        m = re.search(r"(\d+(?:\.\d+)?)%", ln)
        if m:
            t.note = "video %s%%" % m.group(1).split(".")[0]
            t.bump()
        if t.cancel or time.time() - t0 > 900:
            proc.kill()
            break
    proc.wait()
    found = [f for f in os.listdir(VID_DIR) if f.startswith(t.key + ".") and f.lower().endswith(VID_EXTS)]
    if t.cancel or not found:
        for f in os.listdir(VID_DIR):                       # leftovers (.part) of a cancelled / failed download
            if f.startswith(t.key + "."):
                try:
                    os.remove(os.path.join(VID_DIR, f))
                except OSError:
                    pass
        return ""
    best = max(found, key=lambda f: os.path.getsize(os.path.join(VID_DIR, f)))
    return os.path.join(VID_DIR, best)


def _video_job(t):
    mode = E.media_video
    if mode == "off":
        t.video_state = "off"
        t.bump()
        return
    if not E.media_prefer_video:                             # cover mode: do not even look for a video (saves data)
        t.video_state = "idle"
        t.bump()
        return
    p = _local_video(t) or _cached_video(t)
    if not p and mode == "auto" and not _recent(_idx().get(t.key, {}).get("video_tried")):
        t.video_state = "loading"
        t.note = "video..."
        t.bump()
        p = _download_video(t)
        if not t.cancel:
            _idx_set(t.key, video=os.path.basename(p) if p else "", video_tried=0 if p else time.time())
        if p:
            trim_cache()
    if t.cancel:
        return
    if p:
        t.video, t.video_state = p, "ready"
        if t.art_state != "loading":
            t.note = ""
    else:
        t.video_state = "missing"
        if not t.note.startswith(("yt-dlp", "ffmpeg")):
            t.note = ""
    t.bump()


# ------------------------------------------------------------------ images for the UI (Tk reads only PNG/GIF, so everything is converted)
def _pil():
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def scaled_path(src, size):
    try:
        mt = int(os.path.getmtime(src))
    except OSError:
        mt = 0
    return os.path.join(SCALED_DIR, hashlib.sha1(("%s|%d|%d" % (src, mt, size)).encode()).hexdigest()[:20] + ".png")


def _make_scaled(src, dst, size):
    _ensure_dirs()
    tmp = dst + ".tmp.png"
    try:
        Image = _pil()
        if Image is not None:
            im = Image.open(src).convert("RGB")
            im.thumbnail((size, size))
            im.save(tmp, "PNG")
        elif shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (size, size),
                            "-frames:v", "1", tmp], capture_output=True, timeout=30)
        else:
            return src if src.lower().endswith((".png", ".gif")) else ""
        if os.path.isfile(tmp) and os.path.getsize(tmp) > 100:
            os.replace(tmp, dst)
            return dst
    except Exception:
        pass
    try:
        os.remove(tmp)
    except OSError:
        pass
    return ""


def get_scaled(src, size):
    """Path of a PNG copy of `src` that fits size x size; '' while it is still being made (ask again later)."""
    if not src or not os.path.isfile(src):
        return ""
    dst = scaled_path(src, size)
    if os.path.isfile(dst):
        return dst
    with _lock:
        if dst in _scaling:
            return ""
        _scaling.add(dst)

    def work():
        try:
            _make_scaled(src, dst, size)
        finally:
            with _lock:
                _scaling.discard(dst)
    threading.Thread(target=work, daemon=True).start()
    return ""


def avg_color(src):
    """Average colour of the picture as '#rrggbb' ('' if it cannot be computed)."""
    try:
        Image = _pil()
        if Image is not None:
            r, g, b = Image.open(src).convert("RGB").resize((1, 1)).getpixel((0, 0))
        elif shutil.which("ffmpeg"):
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "scale=1:1", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, timeout=20).stdout
            if len(raw) < 3:
                return ""
            r, g, b = raw[0], raw[1], raw[2]
        else:
            return ""
        return "#%02x%02x%02x" % (r, g, b)
    except Exception:
        return ""


# ------------------------------------------------------------------ video playback = ffmpeg -> PPM frames (works in any Tk, no extra libraries)
def _tok(f):
    tok = b""
    while True:
        c = f.read(1)
        if not c:
            return None
        if c.isspace():
            if tok:
                return tok
            continue
        tok += c


class VideoStream:
    """Decodes a silent video to small PPM frames in a background thread. The audio comes from the song, so it is never touched."""

    def __init__(self):
        self.lock = threading.Lock()
        self.gen, self.seq = 0, 0
        self.frame, self.src = None, ""
        self.running = self.finished = False
        self.base, self.t0, self.size, self.error = 0.0, 0.0, (0, 0), ""
        self.proc = None

    def start(self, src, pos, w, h, fps=12):
        self.stop()
        w, h = max(64, int(w) // 2 * 2), max(64, int(h) // 2 * 2)
        with self.lock:
            self.gen += 1
            gen = self.gen
            self.src, self.base, self.t0, self.size = src, float(pos), time.time(), (w, h)
            self.running, self.finished, self.error, self.frame = True, False, "", None
        threading.Thread(target=self._run, args=(src, float(pos), w, h, fps, gen), daemon=True).start()

    def stop(self):
        with self.lock:
            self.gen += 1
            self.running = False
            p, self.proc = self.proc, None
        if p is not None:
            try:
                p.kill()
            except Exception:
                pass

    def expected_pos(self):
        return self.base + (time.time() - self.t0)

    def latest(self):
        with self.lock:
            return self.seq, self.frame

    def _run(self, src, pos, w, h, fps, gen):
        proc = None
        try:
            cmd = ["ffmpeg", "-v", "error", "-re", "-ss", "%.2f" % max(0.0, pos), "-i", src, "-an", "-sn",
                   "-vf", "fps=%d,scale=%d:%d:force_original_aspect_ratio=decrease" % (fps, w, h), "-f", "image2pipe", "-vcodec", "ppm", "-"]
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, **kw)
            with self.lock:
                if gen != self.gen:
                    proc.kill()
                    return
                self.proc = proc
            out = proc.stdout
            while True:
                if gen != self.gen:
                    return
                magic = _tok(out)
                if magic != b"P6":
                    break
                fw, fh, mx = _tok(out), _tok(out), _tok(out)
                if not (fw and fh and mx):
                    break
                n = int(fw) * int(fh) * 3
                data = out.read(n)
                if len(data) < n:
                    break
                with self.lock:
                    if gen != self.gen:
                        return
                    self.frame = (int(fw), int(fh), b"P6 %d %d 255\n" % (int(fw), int(fh)) + data)
                    self.seq += 1
        except Exception as e:
            self.error = str(e)
        finally:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            with self.lock:
                if gen == self.gen:
                    self.running, self.finished = False, True


# ------------------------------------------------------------------ cache management / reset
def _du(d):
    total = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def cache_info():
    """(art_mb, video_mb) used in the cache folder."""
    return (_du(ART_DIR) + _du(SCALED_DIR)) / 1048576.0, _du(VID_DIR) / 1048576.0


def trim_cache():
    """Keep the cache under the limit: oldest videos go first, then oldest scaled pictures. The playing video is kept."""
    limit = E.media_cache_mb * 1048576
    keep = _cur.video if _cur else ""
    for d in (VID_DIR, SCALED_DIR):
        if _du(MEDIA_DIR) <= limit:
            return
        files = []
        for f in os.listdir(d) if os.path.isdir(d) else []:
            p = os.path.join(d, f)
            if p != keep:
                try:
                    files.append((os.path.getmtime(p), p))
                except OSError:
                    pass
        for _, p in sorted(files):
            if _du(MEDIA_DIR) <= limit:
                return
            try:
                os.remove(p)
            except OSError:
                pass


def reset_song(path=None):
    """Forget (delete from the cache) the art and video of one song, then search again."""
    t = _cur if path is None else Track(path)
    if t is None:
        return 0
    n = 0
    t.cancel = True
    for d in (ART_DIR, VID_DIR):
        for f in os.listdir(d) if os.path.isdir(d) else []:
            if f.startswith(t.key):
                try:
                    os.remove(os.path.join(d, f))
                    n += 1
                except OSError:
                    pass
    for f in os.listdir(SCALED_DIR) if os.path.isdir(SCALED_DIR) else []:
        try:
            os.remove(os.path.join(SCALED_DIR, f))          # scaled copies are cheap to rebuild and are keyed by path, so drop them all
        except OSError:
            pass
    with _lock:
        _idx().pop(t.key, None)
        try:
            _ensure_dirs()
            with open(INDEX_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(_index, f)
            os.replace(INDEX_FILE + ".tmp", INDEX_FILE)
        except OSError:
            pass
    _meta.pop(t.path, None)
    _tres.pop(t.path, None)
    if _cur is not None and _cur.path == t.path:
        on_song(t.path)
    return n


def reset_all():
    """Delete every downloaded / extracted picture and video (the cache folder), then search again for the current song."""
    global _index
    t = _cur
    if t:
        t.cancel = True
    with _lock:
        shutil.rmtree(MEDIA_DIR, ignore_errors=True)
        _index = {}
        _meta.clear()
        _scaling.clear()
        _tres.clear()
    _ensure_dirs()
    if t:
        on_song(t.path)
    return True


# ------------------------------------------------------------------ thumbnails for song lists (every song gets its own picture, found in the background)
_tq, _tqset, _tres = collections.deque(), set(), {}          # queue / queued paths / path -> art file ('' = none)
_tcond = threading.Condition()
_tworker = None
thumb_version = 0                                            # +1 whenever a new picture was found (the GUI redraws its lists)


def _thumb_loop():
    global thumb_version
    while True:
        with _tcond:
            while not _tq:
                _tcond.wait()
            path = _tq.popleft()
            _tqset.discard(path)
        art, online = "", False
        try:
            art, online = _resolve_thumb(path)
        except Exception:
            pass
        _tres[path] = art
        thumb_version += 1
        if online:
            time.sleep(0.4)                                  # be gentle with the free cover-art services


def _resolve_thumb(path):
    artist, title = song_meta(path)
    t = Track(path)
    t.artist, t.title = artist, title
    t.key = _key(artist, title, path)
    mode = E.media_art
    if mode == "off":
        return "", False
    p = _sidecar_art(path) or _embedded_art(t)
    if not p:
        ent = _idx().get(t.key, {})
        if ent.get("art") and os.path.isfile(os.path.join(ART_DIR, ent["art"])):
            p = os.path.join(ART_DIR, ent["art"])
    if p or mode != "auto" or _recent(_idx().get(t.key, {}).get("art_tried")):
        return p, False
    p = _download_art(t)
    _idx_set(t.key, art=os.path.basename(p) if p else "", art_tried=0 if p else time.time())
    return p, True


def _queue_thumb(path):
    global _tworker
    with _tcond:
        if path in _tqset:
            try:
                _tq.remove(path)                             # asked again: it is on screen right now, so it moves to the front
            except ValueError:
                pass
        _tqset.add(path)
        _tq.appendleft(path)
        if _tworker is None:
            _tworker = threading.Thread(target=_thumb_loop, daemon=True)
            _tworker.start()
        _tcond.notify()


def art_of(path):
    """The original cover file of a song ('' if it has none or is not known yet - then it is looked up in the background)."""
    a = _tres.get(path)
    if a is None:
        _queue_thumb(path)
        return ""
    return a


def thumb(path, size):
    """A size x size PNG of the song's cover ('' while it is still being found / made)."""
    a = art_of(path)
    return get_scaled(a, size) if a else ""

# END-OF-FILE rofpalys_media.py

