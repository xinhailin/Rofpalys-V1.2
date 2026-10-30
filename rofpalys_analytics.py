#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - statistics recorder: watches the player, keeps a tamper-evident log, answers `rofpalys stats`
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""What it does
  * A small thread looks at the player twice a second (song, position, paused, volume, mode, favourites, sleep timer, queue, effect, lyrics source) and writes
    every change as a RAW FACT into an append-only log:   <config>/analytics/log-YYYYMM.jsonl   (one JSON line per fact).
  * The log is tamper-evident: every line has a sequence number, the UTC time in ms, the UTC offset, the session id and a hash chained to the line before it
    (`rofpalys stats verify`; `rofpalys stats anchor` prints the newest hash so you can keep a copy somewhere else).
  * It survives a crash: lines are written with one call, important ones are fsynced, a half-written last line is quarantined (not deleted), and a session that
    never closed is closed at the next start from a heartbeat file (live.json) - the listening of the last seconds is not lost.
  * Time is measured from the song position and the monotonic clock, not from the wall clock alone; gaps (the phone sleeping) are recorded, never invented.
  * rofpalys_analytics_calc.py turns the facts into numbers (rules are plain constants there); rofpalys_analytics_text.py turns numbers into words.
  * The player does not have to know about it: start(E, "gui") from the launcher is enough. Other parts can add facts with note("what", {...}).
Everything stays on this device."""
import atexit
import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid

import rofpalys_analytics_calc as C
import rofpalys_analytics_text as X

try:
    import rofpalys_library as _lib
    _CFG = _lib.CONFIG_DIR
except Exception:
    _CFG = os.path.join(os.path.expanduser("~"), ".config", "rofpalys")

__version__ = "1.0"
SCHEMA = 1
INTERVAL, IDLE_INTERVAL = 0.5, 2.0       # how often the player is looked at: while a song plays / otherwise
GAP_MAX = 5.0                            # more than this between two looks = the program was held up: a recorded gap
CLOCK_TOL = 2.0                          # wall clock and monotonic clock may differ by this much per look before a clock change is recorded
MAX_RATE = 3.5                           # song seconds per real second that still count as normal playing (speed effects); more = a seek
FLUSH_S = 120.0                          # a long stretch of listening is written in pieces of at most this many seconds
STALL_MIN, STALL_GRACE = 2.5, 0.5        # the song position stood still for more than this many seconds while "playing" = stalled / buffering: that time is taken out again
HB_PLAY, HB_IDLE = 2.0, 10.0             # the heartbeat file (live.json) is rewritten this often
FSYNC_EVERY, SNAP_EVERY = 15.0, 600.0
BACKDATE_MAX = 2.5                       # a new song seen at 0..2.5 s started that long ago: the missed beginning is counted
VOL_QUIET = 1.5                          # a volume change is written once the slider has rested this long
SETTLE_S = 4.0                           # right after the start the program is still loading its favourites, volume and play mode: that is not something the person did
NEAR_END = (3.0, 0.02)                   # a song counts as 'reached the end' within max(3 s, 2 %) of its length
MAX_ERRORS = 20
SYNC_KINDS = ("sess", "end", "fin", "recover", "torn", "file", "clock", "gap")


def base_dir():
    return os.environ.get("ROFPALYS_ANALYTICS_DIR") or os.path.join(_CFG, "analytics")


class Clock:
    """The two clocks the recorder uses (tests replace this with a fake one)."""

    def wall(self):
        return int(time.time() * 1000)

    def mono(self):
        return time.monotonic()

    def offset(self, wall_ms):
        try:
            return int(time.localtime(wall_ms / 1000.0).tm_gmtoff // 60)
        except Exception:
            return int(-(time.altzone if time.daylight and time.localtime().tm_isdst > 0 else time.timezone) // 60)


def _h(prev, payload_json):
    return hashlib.sha256((prev + payload_json).encode("utf-8")).hexdigest()[:16]


def _dumps(o):
    return json.dumps(o, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------- the log on disk
_LOG_RE = re.compile(r"^log-(\d{6})\.jsonl$")


class Store:
    """The append-only log: monthly files, one JSON line per fact, hash-chained across the files."""

    def __init__(self, base):
        self.base = base
        self.fd = None
        self.name = None
        self.size = 0
        self.n = 0
        self.h = "0" * 16
        self.dirty = False
        self.last_sync = 0.0

    def path(self, name):
        return os.path.join(self.base, name)

    def files(self):
        try:
            return sorted(f for f in os.listdir(self.base) if _LOG_RE.match(f))
        except OSError:
            return []

    # -------------------------------------------------- reading
    def iter_records(self, start=None, stats=None):
        """Yield (record, file name, offset after the line). start = (file name, offset) skips everything before it. Lines that are not whole JSON, or the
        unterminated last line of a file, are skipped and counted in stats['bad'] / stats['torn']."""
        stats = stats if stats is not None else {}
        for name in self.files():
            if start and name < start[0]:
                continue
            try:
                f = open(self.path(name), "rb")
            except OSError:
                continue
            with f:
                if start and name == start[0]:
                    f.seek(start[1])
                    off = start[1]
                else:
                    off = 0
                for raw in f:
                    off += len(raw)
                    if not raw.endswith(b"\n"):
                        stats["torn"] = stats.get("torn", 0) + 1
                        continue
                    try:
                        rec = json.loads(raw.decode("utf-8"))
                        if not isinstance(rec, dict) or "k" not in rec:
                            raise ValueError
                    except ValueError:
                        stats["bad"] = stats.get("bad", 0) + 1
                        continue
                    yield rec, name, off

    # -------------------------------------------------- writing
    def open_for_write(self):
        """Find the newest record (n, hash), quarantine an unterminated last line. Returns the number of quarantined bytes."""
        os.makedirs(self.base, exist_ok=True)
        torn = 0
        names = self.files()
        for name in reversed(names):
            p = self.path(name)
            try:
                with open(p, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if data and not data.endswith(b"\n"):
                cut = data.rfind(b"\n") + 1
                tail = data[cut:]
                torn += len(tail)
                qd = os.path.join(self.base, "quarantine")
                os.makedirs(qd, exist_ok=True)
                with open(os.path.join(qd, "%s-%d.tail" % (name, int(time.time()))), "wb") as q:
                    q.write(tail)
                with open(p, "r+b") as f:
                    f.truncate(cut)
                data = data[:cut]
            lines = data.splitlines()
            for raw in reversed(lines[-50:]):
                try:
                    r = json.loads(raw.decode("utf-8"))
                    self.n, self.h = int(r["n"]), str(r["h"])
                    return torn
                except (ValueError, KeyError, TypeError):
                    continue
            if lines:
                continue
        return torn

    def _open(self, name):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = os.open(self.path(name), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        self.name = name
        self.size = os.fstat(self.fd).st_size

    def pos(self):
        return (self.name, self.size) if self.name else (None, 0)

    def append(self, t, z, s, k, d, at=None, month=None):
        """Write one record, return it (with n, p, h). Raises OSError when the disk refuses; then nothing was ingested."""
        name = "log-%s.jsonl" % (month or C.day_key(C.day_index(t, z))[:7].replace("-", ""))
        fresh = False
        if self.fd is None and self.name is not None:                       # an earlier write failed: cut off whatever half-line it left before writing on
            self.open_for_write()
            name = self.name if name < self.name else name
        if self.fd is None or name != self.name:
            if self.name and name < self.name:
                name = self.name                                            # a clock set back never writes into an older file
            self._open(name)
            fresh = self.size == 0
        if fresh:
            self._write(t, z, s, "file", {"v": SCHEMA, "app": "rofpalys", "analytics": __version__, "py": sys.version.split()[0], "os": sys.platform, "file": name})
        return self._write(t, z, s, k, d, at)

    def _write(self, t, z, s, k, d, at=None):
        payload = {"n": self.n + 1, "t": int(t), "z": int(z), "s": s, "k": k, "d": d}
        if at is not None:
            payload["at"] = int(at)
        pj = _dumps(payload)
        h = _h(self.h, pj)
        rec = dict(payload)
        rec["p"], rec["h"] = self.h, h
        line = (_dumps(rec) + "\n").encode("utf-8")
        try:
            wrote = os.write(self.fd, line)
            if wrote != len(line):
                raise OSError("short write (%d of %d bytes)" % (wrote, len(line)))
        except OSError:
            try:
                os.close(self.fd)                                           # the next append reopens the file and removes the half-written line
            except OSError:
                pass
            self.fd = None
            raise
        self.n, self.h = payload["n"], h
        self.size += len(line)
        self.dirty = True
        return rec

    def sync(self):
        if self.fd is not None and self.dirty:
            try:
                os.fsync(self.fd)
            except OSError:
                pass
            self.dirty = False
        self.last_sync = time.monotonic()

    def close(self):
        self.sync()
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None

    # -------------------------------------------------- the saved summary
    def snapshot_path(self):
        return self.path("state.json")

    def save_snapshot(self, agg):
        name, off = self.pos()
        if name is None:
            return False
        try:
            tmp = self.snapshot_path() + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"at": {"file": name, "off": off, "n": agg.head["n"], "h": agg.head["h"]}, "agg": agg.state()}, f, separators=(",", ":"))
            os.replace(tmp, self.snapshot_path())
            return True
        except (OSError, ValueError, TypeError):
            return False

    def load_agg(self, use_snapshot=True):
        """(Agg, how). The saved summary is used only when the log still has, at the place it points to, exactly the record it was made at."""
        agg, start, how = None, None, "replay"
        if use_snapshot:
            try:
                with open(self.snapshot_path(), encoding="utf-8") as f:
                    snap = json.load(f)
                at = snap["at"]
                with open(self.path(at["file"]), "rb") as lf:
                    lf.seek(max(0, at["off"] - 600))
                    chunk = lf.read(min(600, at["off"]))
                last = chunk.rstrip(b"\n").split(b"\n")[-1]
                r = json.loads(last.decode("utf-8"))
                if int(r["n"]) == int(at["n"]) and r["h"] == at["h"] and chunk.endswith(b"\n"):
                    agg = C.Agg.from_state(snap["agg"])
                    start, how = (at["file"], at["off"]), "snapshot"
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                agg = None
        if agg is None:
            agg = C.Agg()
        st = {}
        for rec, _name, _off in self.iter_records(start, st):
            agg.ingest(rec)
        agg.q["torn"] = max(agg.q["torn"], 0)
        return agg, how

    # -------------------------------------------------- audit
    def verify(self, deep=False, anchor=None):
        """Walk the whole chain. {"ok", "records", "files", "errors", "warnings", "head", "n", "first", "last", "deep"}"""
        res = {"ok": True, "records": 0, "files": 0, "errors": [], "warnings": [], "head": "", "n": 0, "first": 0, "last": 0, "deep": None, "anchor": None}
        prev_h, prev_n, last_t = "0" * 16, 0, 0
        anchors = {}
        for name in self.files():
            res["files"] += 1
            try:
                f = open(self.path(name), "rb")
            except OSError as e:
                res["errors"].append("%s: cannot be read (%s)" % (name, e))
                continue
            with f:
                for ln, raw in enumerate(f, 1):
                    where = "%s:%d" % (name, ln)
                    if not raw.endswith(b"\n"):
                        res["warnings"].append("%s: last line unfinished (a crash while writing); it is quarantined at the next start" % where)
                        continue
                    try:
                        rec = json.loads(raw.decode("utf-8"))
                        h, p = rec.pop("h"), rec.pop("p")
                        n = int(rec["n"])
                    except (ValueError, KeyError, TypeError):
                        res["errors"].append("%s: not a valid record" % where)
                        continue
                    res["records"] += 1
                    if n != prev_n + 1:
                        res["errors"].append("%s: sequence jumps from %d to %d (lines missing or inserted)" % (where, prev_n, n))
                    if p != prev_h:
                        res["errors"].append("%s: chain broken (the record before it is not the one it was written after)" % where)
                    if _h(p, _dumps(rec)) != h:
                        res["errors"].append("%s: record n=%d was changed after it was written" % (where, n))
                    t = int(rec.get("at") or rec.get("t") or 0)
                    if not rec.get("at") and last_t and t < last_t - 1000:
                        res["warnings"].append("%s: time goes back by %d s (system clock was set back)" % (where, (last_t - t) // 1000))
                    if not rec.get("at"):
                        last_t = max(last_t, t) if t >= last_t else t
                    if not res["first"]:
                        res["first"] = t
                    res["last"] = max(res["last"], t)
                    anchors[n] = h
                    prev_h, prev_n = h, n
        res["head"], res["n"] = prev_h, prev_n
        if anchor:
            try:
                an, ah = anchor.split(":", 1)
                res["anchor"] = anchors.get(int(an)) == ah
                if not res["anchor"]:
                    res["errors"].append("anchor %s does not match the log (record %s has another hash or is gone)" % (anchor, an))
            except ValueError:
                res["errors"].append("anchor must look like  N:HASH  (see `rofpalys stats anchor`)")
        if deep:
            full, _ = self.load_agg(use_snapshot=False)
            try:
                snap, how = self.load_agg(use_snapshot=True)
                same = _dumps(snap.state()) == _dumps(full.state())
            except Exception:
                same = False
            res["deep"] = same
            if not same:
                res["errors"].append("the saved summary differs from a fresh calculation from the log (it is rebuilt automatically at the next start)")
        res["ok"] = not res["errors"]
        return res


# ---------------------------------------------------------------- a lock so that only one recorder writes
def _lock(path):
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return -1
    try:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return fd
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        return None


def _guess(path):
    try:
        import rofpalys_lyrics as LY
        a, t = LY.guess(path)
        return a or "", t or ""
    except Exception:
        b = os.path.splitext(os.path.basename(path))[0]
        if " - " in b:
            a, t = b.split(" - ", 1)
            return a.strip(), t.strip()
        return "", b


# ---------------------------------------------------------------- the recorder
class Recorder:
    def __init__(self, E=None, surface="?", base=None, clock=None, interval=INTERVAL, settle=None):
        self.E, self.surface, self.base = E, surface, base or base_dir()
        self.settle = SETTLE_S if settle is None else settle
        self.clock = clock or Clock()
        self.interval = interval
        self.store = Store(self.base)
        self.lock = threading.RLock()
        self.agg = C.Agg()
        self.how = ""
        self.sid = ""
        self.state = "idle"             # idle | running | readonly | stopped
        self.errors = []
        self.degraded = ""
        self.cur = None                 # the play that is running: dict
        self.prev = None                # the other things last seen
        self.r_ref = 1.0                # song seconds per real second (speed effects)
        self.counter = 0
        self.lockfd = None
        self._thread = None
        self._stop = threading.Event()
        self._m_prev = self._w_prev = None
        self._m_start = 0.0
        self._hb = self._snap_t = -1e9
        self._snap_n = 0
        self._vol = None
        self._favs = None
        self.started = 0

    # -------------------------------------------------- life cycle
    def _err(self, where, e):
        self.errors.append("%s: %r" % (where, e))
        del self.errors[:-MAX_ERRORS]

    def start(self, thread=True):
        with self.lock:
            if self.state == "running":
                return True
            try:
                os.makedirs(self.base, exist_ok=True)
            except OSError as e:
                self._err("mkdir", e)
                self.state = "readonly"
                return False
            self.lockfd = _lock(os.path.join(self.base, "lock"))
            if self.lockfd is None or self.lockfd < 0:
                self.lockfd = None
                self.state = "readonly"
                try:
                    self.agg, self.how = self.store.load_agg()
                except Exception as e:
                    self._err("load", e)
                return False
            try:
                torn = self.store.open_for_write()
                self.agg, self.how = self.store.load_agg()
            except Exception as e:
                self._err("open", e)
                self.state = "readonly"
                self._unlock()
                return False
            self.sid = uuid.uuid4().hex[:8]
            self.state = "running"
            self._m_start = self.clock.mono()
            self.started = self.clock.wall()
            self._recover()
            if torn:
                self._emit("torn", {"bytes": torn})
            self._emit("sess", {"surface": self.surface, "pid": os.getpid(), "ver": self._ver(), "py": sys.version.split()[0], "os": sys.platform, "analytics": __version__}, sync=True)
            self._write_live(force=True)
            if thread:
                self._stop.clear()
                self._thread = threading.Thread(target=self._loop, name="rofpalys-analytics", daemon=True)
                self._thread.start()
            return True

    def _ver(self):
        try:
            import rofpalys_library as lib
            return str(getattr(lib, "VERSION", "") or "")
        except Exception:
            return ""

    def _unlock(self):
        if self.lockfd is not None:
            try:
                os.close(self.lockfd)
            except OSError:
                pass
            self.lockfd = None

    def stop(self, why="exit"):
        with self.lock:
            if self.state != "running":
                return
            self._stop.set()
            try:
                if self.cur is not None:
                    self._end_play("finished" if self._near_end(self.cur) else "quit")
                self._emit("end", {"why": why, "up": round(self.clock.mono() - self._m_start, 1)}, sync=True)
                self.store.save_snapshot(self.agg)
                self._write_live(closed=True)
            except Exception as e:
                self._err("stop", e)
            self.state = "stopped"
            self.store.close()
            self._unlock()

    def _loop(self):
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval if (self.cur is not None and self.cur["was"]) else max(self.interval, IDLE_INTERVAL))

    # -------------------------------------------------- writing facts
    def _emit(self, k, d, at=None, sid=None, z=None, sync=False):
        w = self.clock.wall()
        zz = self.clock.offset(w) if z is None else z
        try:
            rec = self.store.append(w, zz, sid or self.sid, k, d, at)
        except OSError as e:
            self.degraded = "the log cannot be written: %s" % e
            self._err("write", e)
            return None
        self.degraded = ""
        self.agg.ingest(rec)
        if sync or k in SYNC_KINDS:
            self.store.sync()
        return rec

    def note(self, what, data=None):
        """Add a fact from outside (a window opened, a setting changed ...). Never raises."""
        try:
            with self.lock:
                if self.state != "running":
                    return
                d = {"what": str(what)[:40]}
                for a, b in (data or {}).items():
                    d[str(a)[:30]] = b if isinstance(b, (int, float, bool)) or b is None else str(b)[:120]
                self._emit("ui", d)
        except Exception as e:
            self._err("note", e)

    # -------------------------------------------------- crash recovery
    def _read_live(self):
        try:
            with open(os.path.join(self.base, "live.json"), encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else None
        except (OSError, ValueError):
            return None

    def _recover(self):
        """Close what an earlier run left open (it was killed): the last stretch of listening from the heartbeat file, its plays, the session itself."""
        live = self._read_live()
        stale = [sid for sid in self.agg.so if sid != self.sid]
        plays = [(pid, p) for pid, p in self.agg.pl.items() if p["sid"] != self.sid]
        if not stale and not plays:
            return
        for sid in sorted(set(stale + [p["sid"] for _, p in plays])):
            so = self.agg.so.get(sid)
            at = so["last"] if so else (live or {}).get("t", 0)
            mine = live is not None and live.get("sid") == sid and not live.get("closed")
            z = (live or {}).get("z", self.clock.offset(self.clock.wall())) if mine else (so["z"] if so else 0)
            if mine:
                at = max(at, int(live.get("t", 0)))
                seg = live.get("seg")
                if seg and seg.get("d", 0) > 0 and seg.get("id") in self.agg.pl:
                    self._emit("seg", {"id": seg["id"], "a": seg["a"], "d": round(seg["d"], 3), "p0": seg.get("p0", 0), "p1": seg.get("p1", 0), "q": "live"}, at=at, sid=sid, z=z)
            for pid, p in [(a, b) for a, b in list(self.agg.pl.items()) if b["sid"] == sid]:
                pos = (live.get("play") or {}).get("maxpos", 0) if mine and (live.get("play") or {}).get("id") == pid else 0
                self._emit("fin", {"id": pid, "why": "crash", "pos": pos, "dur": p["dur"]}, at=at, sid=sid, z=z)
            if so is not None:
                self._emit("end", {"why": "recovered"}, at=at, sid=sid, z=z, sync=True)

    # -------------------------------------------------- the player's state
    def _read(self):
        E = self.E
        g = lambda n, d=None: getattr(E, n, d)
        path = str(g("playing_song_name", "") or "")
        dur_known = bool(g("duration_known", False))
        st = {"path": path, "active": bool(g("is_playing", False)) and bool(path), "paused": bool(g("is_paused", False)), "pos": _f(g("current_time_seconds", 0)),
              "dur": _f(g("total_time_seconds", 0)) if dur_known else 0.0, "vol": g("volume", None), "mode": g("play_mode", None), "lyrics": g("lyrics_source", None)}
        try:
            st["favs"] = g("favorites", None)
            st["nfav"] = len(st["favs"]) if st["favs"] is not None else None
        except Exception:
            st["favs"], st["nfav"] = None, None
        for key, mod, fn in (("sleep", "rofpalys_sleep", lambda M: (bool(M.active()), int(M.remaining()) if M.active() else 0)),
                             ("queue", "rofpalys_queue", lambda M: len(M.upnext)), ("fx", "rofpalys_effects", lambda M: str(M.label()))):
            try:
                st[key] = fn(sys.modules[mod]) if mod in sys.modules else None
            except Exception:
                st[key] = None
        return st

    def tick(self):
        """One look at the player (the thread calls this; tests call it by hand)."""
        try:
            with self.lock:
                if self.state != "running":
                    return
                m, w = self.clock.mono(), self.clock.wall()
                st = self._read()
                self._clock_check(m, w)
                self._track(st, m, w)
                self._events(st, m)
                self._housekeeping(m)
                self._m_prev, self._w_prev = m, w
        except Exception as e:
            self._err("tick", e)

    def _clock_check(self, m, w):
        if self._m_prev is None:
            return
        dm, dw = m - self._m_prev, (w - self._w_prev) / 1000.0
        if abs(dw - dm) > CLOCK_TOL:
            self._emit("clock", {"delta": round(dw - dm, 3)})
            if self.cur is not None:
                self._close_seg(self.cur)
                self.cur["m"], self.cur["w"] = m, w                 # nothing is inferred across a clock change
                self.cur["pos"] = _f(getattr(self.E, "current_time_seconds", self.cur["pos"]), self.cur["pos"])
                self.cur["skipclock"] = True
            self._m_prev = m

    @staticmethod
    def _near_end(cur):
        d = cur["dur"]
        return d > 0 and cur["maxpos"] >= d - max(NEAR_END[0], NEAR_END[1] * d)

    def _track(self, st, m, w):
        cur = self.cur
        playing = st["active"] and not st["paused"]
        if cur is not None:
            if not st["active"] or st["path"] != cur["path"]:
                self._end_play("finished" if self._near_end(cur) else ("stopped" if not st["active"] else "left"))
                cur = None
            elif st["dur"] > 0 and self._near_end(cur) and st["pos"] < cur["pos"] - 1.0 and st["pos"] < 0.5 * st["dur"]:
                self._end_play("finished")                           # the same song again (repeat): a new play
                cur = None
        if cur is None:
            if playing:
                self._start_play(st, m, w)
            return
        self._advance(cur, st, playing, m, w)

    def _start_play(self, st, m, w):
        self.counter += 1
        pid = "%s-%d" % (self.sid, self.counter)
        path = st["path"]
        artist, title = _guess(path)
        favs = st.get("favs")
        try:
            fav = bool(favs is not None and path in favs)
        except Exception:
            fav = False
        self._emit("play", {"id": pid, "path": path, "title": title, "artist": artist, "folder": os.path.basename(os.path.dirname(path)), "dur": round(st["dur"], 2),
                            "vol": st["vol"], "mode": st["mode"], "fav": fav})
        pos = st["pos"]
        back = pos if pos < BACKDATE_MAX else 0.0                  # a song seen 1 s after it started was playing for that second already
        self.cur = {"pid": pid, "path": path, "dur": st["dur"], "pos": pos, "maxpos": pos, "m": m, "w": w, "was": True, "listen": 0.0, "t0": w, "frozen": 0.0,
                    "seg": {"a": w - int(back * 1000), "wall": back, "p0": pos - back, "p1": pos}}

    def _advance(self, cur, st, playing, m, w):
        pos, was = st["pos"], cur["was"]
        dm, dp = m - cur["m"], pos - cur["pos"]
        if st["dur"] > 0:
            cur["dur"] = st["dur"]
        if cur.pop("skipclock", False):
            dm = 0.0
            dp = 0.0
        seg = cur["seg"]
        if dm > GAP_MAX:
            self._close_seg(cur)
            self._emit("gap", {"id": cur["pid"], "a": cur["w"], "s": round(dm, 3)})
            if was and playing and 0 < dp <= dm * MAX_RATE + 1.0:
                wall = min(dm, dp / max(self.r_ref, 0.25))
                if wall >= 0.05:
                    self._emit_seg(cur, cur["w"], wall, cur["pos"], pos, "gap")
            cur["seg"] = {"a": w, "wall": 0.0, "p0": pos, "p1": pos} if playing else None
        else:
            hi = (dm * MAX_RATE + 1.0) if (was or playing) else 1.5
            if not (-0.4 <= dp <= hi):
                self._emit("seek", {"id": cur["pid"], "from": round(cur["pos"], 2), "to": round(pos, 2)})
                self._close_seg(cur)
                cur["frozen"] = 0.0
                cur["seg"] = {"a": w, "wall": 0.0, "p0": pos, "p1": pos} if playing else None
            elif was and playing:
                if seg is None:
                    seg = cur["seg"] = {"a": cur["w"], "wall": 0.0, "p0": cur["pos"], "p1": cur["pos"]}
                seg["wall"] += dm
                seg["p1"] += max(dp, 0.0)
                if dp > 0.02:
                    if cur["frozen"] > STALL_MIN:                           # the position moves again after standing still: that stand-still was not listening
                        seg["wall"] = max(0.0, seg["wall"] - (cur["frozen"] - STALL_GRACE))
                    cur["frozen"] = 0.0
                else:
                    cur["frozen"] += dm
            elif was and not playing:
                if seg is not None:
                    seg["wall"] += min(dm, max(dp, 0.0) / self.r_ref)
                    seg["p1"] += max(dp, 0.0)
                self._close_seg(cur)
            elif playing and not was:
                part = min(dm, max(dp, 0.0) / self.r_ref)
                cur["seg"] = {"a": w - int(part * 1000), "wall": part, "p0": pos - max(dp, 0.0), "p1": pos}
        if was and not playing:
            self._emit("pause", {"id": cur["pid"], "pos": round(pos, 2)})
        elif playing and not was:
            self._emit("resume", {"id": cur["pid"], "pos": round(pos, 2)})
        cur["pos"], cur["m"], cur["w"], cur["was"] = pos, m, w, playing
        cur["maxpos"] = max(cur["maxpos"], pos)
        if cur["seg"] is not None and cur["seg"]["wall"] >= FLUSH_S:
            self._close_seg(cur)
            cur["seg"] = {"a": w, "wall": 0.0, "p0": pos, "p1": pos}

    def _emit_seg(self, cur, a, wall, p0, p1, q):
        cur["listen"] += wall
        self._emit("seg", {"id": cur["pid"], "a": int(a), "d": round(wall, 3), "p0": round(p0, 2), "p1": round(p1, 2), "q": q})

    def _close_seg(self, cur):
        seg, cur["seg"] = cur.get("seg"), None
        if not seg:
            return
        if cur.get("frozen", 0.0) > STALL_MIN:                           # closed while the position stood still: that time was not listening
            seg["wall"] = max(0.0, seg["wall"] - (cur["frozen"] - STALL_GRACE))
        cur["frozen"] = 0.0
        wall, media = seg["wall"], max(0.0, seg["p1"] - seg["p0"])
        if wall >= 20.0 and media > 0:                                    # the speed (a speed effect makes the song run faster than the clock)
            ratio = media / wall
            if 0.4 <= ratio <= 3.0:
                self.r_ref = 0.7 * self.r_ref + 0.3 * ratio
        if wall >= 0.05:
            self._emit_seg(cur, seg["a"], wall, seg["p0"], seg["p1"], "live")

    def _end_play(self, why):
        cur = self.cur
        if cur is None:
            return
        if why == "finished" and cur["was"] and cur["seg"] is not None and cur["dur"] > 0:
            rem = cur["dur"] - cur["pos"]
            if 0 < rem <= 1.0:                                       # the last fraction of a second before the song ended by itself
                cur["seg"]["wall"] += rem / max(self.r_ref, 0.25)
                cur["seg"]["p1"] += rem
        self._close_seg(cur)
        self._emit("fin", {"id": cur["pid"], "why": why, "pos": round(cur["maxpos"], 2), "dur": round(cur["dur"], 2)}, sync=True)
        self.cur = None

    # -------------------------------------------------- everything else that can change
    def _events(self, st, m):
        p = self.prev
        if p is not None and self.settle > 0 and m - self._m_start < self.settle:
            p = self.prev = None                                     # still loading: look again, say nothing (plays are not affected - they are always recorded)
        if p is None:
            self.prev = {"mode": st["mode"], "lyrics": st["lyrics"], "sleep": st.get("sleep"), "queue": st.get("queue"), "fx": st.get("fx")}
            self._vol = {"from": st["vol"], "cur": st["vol"], "since": m, "dirty": False}
            try:
                self._favs = set(st["favs"]) if st.get("favs") is not None else None
            except Exception:
                self._favs = None
            return
        v = self._vol
        if st["vol"] is not None and v["cur"] is not None and abs(_f(st["vol"]) - _f(v["cur"])) > 0.01:
            v["cur"], v["since"], v["dirty"] = st["vol"], m, True
        elif v["dirty"] and m - v["since"] >= VOL_QUIET:
            if v["from"] != v["cur"]:
                self._emit("vol", {"from": round(_f(v["from"]), 1), "to": round(_f(v["cur"]), 1)})
            v["from"], v["dirty"] = v["cur"], False
        if st["mode"] != p["mode"] and st["mode"] is not None:
            name = ""
            try:
                name = str(self.E.get_mode_string())
            except Exception:
                pass
            self._emit("mode", {"from": p["mode"], "to": st["mode"], "name": name})
        if st["lyrics"] != p["lyrics"]:
            self._emit("lyrics", {"source": st["lyrics"] or "", "path": st["path"]})
        if st.get("sleep") is not None and st["sleep"] != p["sleep"] and (p["sleep"] is None or st["sleep"][0] != p["sleep"][0]):
            self._emit("sleep", {"on": st["sleep"][0], "left": st["sleep"][1]})
        if st.get("queue") is not None and st["queue"] != p["queue"]:
            self._emit("queue", {"n": st["queue"], "from": p["queue"]})
        if st.get("fx") is not None and st["fx"] != p["fx"] and p["fx"] is not None:
            self._emit("fx", {"label": st["fx"]})
        if st.get("nfav") is not None and self._favs is not None and st["nfav"] != len(self._favs):
            try:
                now = set(st["favs"])
                for path in sorted(now - self._favs):
                    self._emit("fav", {"path": path, "on": True})
                for path in sorted(self._favs - now):
                    self._emit("fav", {"path": path, "on": False})
                self._favs = now
            except Exception as e:
                self._err("fav", e)
        self.prev = {"mode": st["mode"], "lyrics": st["lyrics"], "sleep": st.get("sleep"), "queue": st.get("queue"), "fx": st.get("fx")}

    def _housekeeping(self, m):
        playing = self.cur is not None and self.cur["was"]
        if m - self._hb >= (HB_PLAY if playing else HB_IDLE):
            self._write_live()
            self._hb = m
        if self.store.dirty and m - self.store.last_sync >= FSYNC_EVERY:
            self.store.sync()
        if m - self._snap_t >= SNAP_EVERY:
            self._snap_t = m
            if self.agg.head["n"] - self._snap_n >= 20:
                if self.store.save_snapshot(self.agg):
                    self._snap_n = self.agg.head["n"]

    # -------------------------------------------------- what is happening right now
    def live(self):
        """What the summary does not hold yet: the running stretch of listening and the running play. Feeds calc.make_overlay."""
        with self.lock:
            return self._live_locked()

    def _live_locked(self):
        cur = self.cur
        out = {"sid": self.sid, "seg": None, "plays": []}
        if cur is None:
            return out
        extra = 0.0
        if cur["was"] and self._m_prev is not None:
            extra = max(0.0, min(self.clock.mono() - cur["m"], 2.0))      # the time since the last look (so a clock on screen runs smoothly)
        seg = cur["seg"]
        w = ((seg["wall"] + extra) if seg else 0.0)
        z = self.clock.offset(cur["w"])
        if seg:
            out["seg"] = {"a": seg["a"], "d": w, "z": z, "path": cur["path"], "id": cur["pid"], "p0": seg["p0"], "p1": seg["p1"] + extra}
        out["plays"].append({"path": cur["path"], "t": cur["t0"], "z": z, "dur": cur["dur"], "listened": cur["listen"] + w, "maxpos": cur["maxpos"], "id": cur["pid"]})
        return out

    def _write_live(self, force=False, closed=False):
        try:
            lv = self._live_locked()
            m = self.clock.mono()
            w = self.clock.wall()
            cur = self.cur
            doc = {"v": SCHEMA, "sid": self.sid, "pid": os.getpid(), "surface": self.surface, "t": w, "z": self.clock.offset(w), "started": self.started, "up": round(m - self._m_start, 1),
                   "closed": bool(closed), "playing": bool(cur and cur["was"]), "song": cur["path"] if cur else "", "pos": round(cur["pos"], 1) if cur else 0,
                   "dur": round(cur["dur"], 1) if cur else 0, "seg": lv["seg"], "plays": lv["plays"],
                   "play": ({"id": cur["pid"], "maxpos": round(cur["maxpos"], 2)} if cur else None), "n": self.store.n}
            tmp = os.path.join(self.base, "live.json.part")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, separators=(",", ":"))
            os.replace(tmp, os.path.join(self.base, "live.json"))
        except Exception as e:
            self._err("live", e)

    # -------------------------------------------------- questions (the window and the terminal use View)
    def view(self):
        return View(self)


# ---------------------------------------------------------------- the questions
class View:
    """Numbers for the window and the terminal. With a running recorder it sees the running listening and session too; without one it reads the log and
    the heartbeat file of another running Rofpalys (so `rofpalys stats` in a second terminal ticks in real time)."""

    def __init__(self, rec=None, base=None, now=None, offset=None):
        self.rec = rec
        self.base = base or (rec.base if rec else base_dir())
        self._agg = None
        self._now = now
        self._off = offset
        self.recording = bool(rec is not None and rec.state == "running")

    # -------------------------------------------------- plumbing
    def now_ms(self):
        if self._now is not None:
            return self._now
        return self.rec.clock.wall() if self.rec else Clock().wall()

    def z(self):
        if self._off is not None:
            return self._off
        return self.rec.clock.offset(self.now_ms()) if self.rec else Clock().offset(self.now_ms())

    def agg(self):
        if self.rec is not None:
            return self.rec.agg
        if self._agg is None:
            self._agg, _ = Store(self.base).load_agg()
        return self._agg

    def _live(self):
        if self.rec is not None:
            return self.rec._live_locked()
        try:
            with open(os.path.join(self.base, "live.json"), encoding="utf-8") as f:
                d = json.load(f)
            if d.get("closed") or self.now_ms() - int(d.get("t", 0)) > 30000:
                return {}
            seg = d.get("seg")
            if seg:
                seg = dict(seg, d=seg.get("d", 0) + max(0.0, min((self.now_ms() - d["t"]) / 1000.0, 5.0)) if d.get("playing") else seg.get("d", 0))
            return {"sid": d.get("sid"), "seg": seg, "plays": d.get("plays", []), "file": d}
        except (OSError, ValueError, TypeError):
            return {}

    def _run(self, fn):
        if self.rec is not None:
            with self.rec.lock:
                return fn(self.rec.agg, C.make_overlay(self.rec.agg, self.rec._live_locked(), self.now_ms(), self.z()))
        agg = self.agg()
        return fn(agg, C.make_overlay(agg, self._live(), self.now_ms(), self.z()))

    def today(self):
        return C.today_index(self.now_ms(), self.z())

    def span(self, period):
        agg = self.agg()
        return C.span(period, self.today(), agg.first_day())

    # -------------------------------------------------- the questions
    def overview(self):
        return self._run(lambda a, ov: C.overview(a, self.now_ms(), self.z(), ov))

    def rank(self, period="all", by="plays", level="song", rule="lastfm", n=20):
        a0, b0 = self.span(period)
        return self._run(lambda a, ov: C.rank(a, a0, b0, by, level, rule, n, ov))

    def series(self, days=14, end=None):
        t = self.today() if end is None else end
        return self._run(lambda a, ov: C.series(a, t - days + 1, t, ov))

    def totals(self, period="today"):
        a0, b0 = self.span(period)
        return self._run(lambda a, ov: C.totals(a, a0, b0, ov))

    def heat(self, period="90d"):
        a0, b0 = self.span(period)
        return self._run(lambda a, ov: C.heat(a, a0, b0, ov))

    def records(self):
        return self._run(lambda a, ov: C.records(a, self.today(), ov))

    def quality(self):
        return self._run(lambda a, ov: C.quality(a, ov))

    def song(self, path):
        return self._run(lambda a, ov: C.song_detail(a, path, self.today(), ov))

    def kinds(self, period="all"):
        a0, b0 = self.span(period)
        return self._run(lambda a, ov: C.activity_by_kind(a, a0, b0))

    def events(self, n=60, kinds=None):
        def f(a, ov):
            ev = a.recent if not kinds else [e for e in a.recent if e[2] in kinds]
            return list(ev[-n:])
        return self._run(f)

    def plays(self, n=50):
        return self._run(lambda a, ov: list(a.plays[-n:]))

    def today_plays(self):
        t = self.today()
        z = self.z()
        return self._run(lambda a, ov: [p for p in a.plays if C.day_index(p[0], p[1]) == t])

    def title(self, path):
        return self._run(lambda a, ov: (a.title_of(path), a.artist_of(path)))

    def now(self):
        """The live tab: what plays, how long this session is open, what it has listened, today's numbers."""
        def f(a, ov):
            lv = self.rec._live_locked() if self.rec else self._live()
            sid = lv.get("sid")
            so = a.so.get(sid) if sid else None
            cur = (lv.get("plays") or [None])[0]
            fl = lv.get("file") or {}
            r = {"recording": self.recording or bool(fl), "sid": sid, "playing": False, "path": "", "title": "", "artist": "", "pos": 0.0, "dur": 0.0, "listened_play": 0.0, "session_up": 0.0,
                 "session_listen": 0.0, "session_plays": 0, "surface": ""}
            if so is not None:
                r["session_up"] = max(0.0, (self.now_ms() - so["a"]) / 1000.0)
                r["session_plays"] = so["plays"]
                r["surface"] = so["surf"]
                seg = lv.get("seg")
                r["session_listen"] = so["listen"] + ((seg or {}).get("d", 0.0) if seg else 0.0)
            if cur:
                r["path"], r["listened_play"] = cur["path"], cur["listened"]
                r["title"], r["artist"] = a.title_of(cur["path"]), a.artist_of(cur["path"])
                if self.rec is not None and self.rec.cur is not None:
                    r["playing"], r["pos"], r["dur"] = bool(self.rec.cur["was"]), self.rec.cur["pos"], self.rec.cur["dur"]
                    if r["playing"] and self.rec._m_prev is not None:
                        r["pos"] += max(0.0, min(self.rec.clock.mono() - self.rec.cur["m"], 2.0)) * self.rec.r_ref
                elif fl:
                    r["playing"], r["pos"], r["dur"] = bool(fl.get("playing")), fl.get("pos", 0.0), fl.get("dur", 0.0)
            return r
        return self._run(f)


def verify(deep=False, anchor=None, base=None):
    return Store(base or base_dir()).verify(deep, anchor)


# ---------------------------------------------------------------- the one recorder of this program
_REC = None
_HOOKED = []


def recorder():
    return _REC


def start(E, surface="?", **kw):
    """Start recording this program (the launcher calls this for the window, the terminal player and the daemon). Safe to call twice, never raises."""
    global _REC
    try:
        if _REC is not None and _REC.state == "running":
            return _REC
        rec = Recorder(E, surface, **kw)
        rec.start()
        _REC = rec
        if not _HOOKED:
            _HOOKED.append(1)
            atexit.register(stop)
            _hook_signals()
        return rec
    except Exception:
        return _REC


def stop():
    try:
        if _REC is not None:
            _REC.stop()
    except Exception:
        pass


def note(what, data=None):
    """Add a fact from anywhere (does nothing when no recorder runs)."""
    try:
        if _REC is not None:
            _REC.note(what, data)
    except Exception:
        pass


def view():
    """A View of the running recorder, or - in another program - of the files."""
    return View(_REC if (_REC is not None and _REC.state == "running") else None)


def _hook_signals():
    """SIGTERM / SIGHUP (closing the terminal) end a program without running atexit: close the log first, then die the same way (only where nobody else listens)."""
    try:
        import signal
        if threading.current_thread() is not threading.main_thread():
            return
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is None or signal.getsignal(sig) not in (signal.SIG_DFL, None):
                continue

            def handler(num, frame, _sig=sig):
                stop()
                signal.signal(_sig, signal.SIG_DFL)
                os.kill(os.getpid(), _sig)
            signal.signal(sig, handler)
    except Exception:
        pass


def status(base=None):
    """For the doctor: is a recorder running (another program holds the lock), how big is the log, is the chain intact."""
    st = Store(base or base_dir())
    names = st.files()
    size = sum(os.path.getsize(st.path(n)) for n in names if os.path.exists(st.path(n)))
    probe = _lock(os.path.join(st.base, "lock")) if os.path.isdir(st.base) else -1
    running = probe is None
    if probe is not None and probe >= 0:
        os.close(probe)
    return {"dir": st.base, "files": len(names), "bytes": size, "recording_elsewhere": running, "here": _REC.state if _REC else "off", "errors": list(_REC.errors) if _REC else []}


def describe(lg=None):
    lg = lg or X.lang()
    s = status()
    v = verify()
    rec = s["here"] if s["here"] != "off" else ("another Rofpalys is recording" if s["recording_elsewhere"] else "not recording (no Rofpalys is open)")
    head = "analytics %s: %s - %d file(s), %.1f KB, chain %s (%d records) | recorder: %s" % (__version__, s["dir"], s["files"], s["bytes"] / 1024.0, "ok" if v["ok"] else "BROKEN", v["records"], rec)
    return head


# ---------------------------------------------------------------- export
def _csv(rows, head):
    import csv
    import io
    b = io.StringIO()
    w = csv.writer(b, lineterminator="\n")
    w.writerow(head)
    for r in rows:
        w.writerow(r)
    return b.getvalue()


def _iso(t, z):
    sign = "+" if z >= 0 else "-"
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime((t + z * 60000) / 1000.0)) + ".%03d%s%02d:%02d" % (t % 1000, sign, abs(z) // 60, abs(z) % 60)


def export(kind, dest, base=None):
    """kind: csv (a folder with plays.csv, days.csv, songs.csv, events.csv) or json (one file). Returns the list of files written."""
    st = Store(base or base_dir())
    col = C.Agg()
    col.all_plays = []
    col.on_play = col.all_plays.append
    for rec, _n, _o in st.iter_records():
        col.ingest(rec)
    ver = st.verify()
    out = []
    if kind == "json":
        doc = {"generated": _iso(int(time.time() * 1000), 0), "analytics": __version__, "rules_version": C.RULES_V,
               "rules": {"spotify_min_s": C.SP_MIN, "lastfm_min_s": C.LF_MIN, "lastfm_fraction": C.LF_FRAC, "lastfm_abs_s": C.LF_ABS, "completed_fraction": C.DONE_FRAC, "skip_s": C.SKIP_S,
                         "bout_gap_s": C.BOUT_GAP, "active_day_s": C.ACTIVE_DAY_S},
               "integrity": {"ok": ver["ok"], "records": ver["records"], "head": ver["head"], "n": ver["n"], "errors": ver["errors"]},
               "days": col.days, "songs": col.songs, "sessions": col.sessions, "plays": col.all_plays, "quality": col.q}
        d = os.path.abspath(dest)
        os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
        with open(d, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        return [d]
    os.makedirs(dest, exist_ok=True)
    rows = [[_iso(t, z), C.day_key(C.day_index(t, z)), path, col.title_of(path), col.artist_of(path), lis, why, ["not counted", "spotify", "lastfm"][tier], reach]
            for t, z, path, lis, why, tier, reach in col.all_plays]
    out.append(_write_text(os.path.join(dest, "plays.csv"), _csv(rows, ["start", "day", "path", "title", "artist", "listened_s", "ended", "counted_as", "reach_fraction"])))
    rows = []
    for k in sorted(col.days):
        d = col.days[k]
        v = [sum(x[i] for x in d["s"].values()) for i in range(5)]
        rows.append([k, round(d["l"], 2), round(d["o"], 2), v[0], v[1], v[2], v[3], v[4], d["ss"]] + [round(x, 1) for x in d["h"]])
    out.append(_write_text(os.path.join(dest, "days.csv"), _csv(rows, ["day", "listening_s", "open_s", "started", "plays_lastfm", "plays_spotify", "completed", "skipped", "sessions"] + ["h%02d" % i for i in range(24)])))
    first = col.first_day()
    t = max(col.days) if col.days else None
    rk = C.rank(col, first, C.key_index(t), n=0) if t else []
    out.append(_write_text(os.path.join(dest, "songs.csv"), _csv([[r["name"], r["title"], r["artist"], r["plays"], r["starts"], round(r["time"], 1), r["completed"], r["skipped"]] for r in rk],
                                                                   ["path", "title", "artist", "plays_lastfm", "started", "listening_s", "completed", "skipped"])))
    ev = []
    for rec, _n, _o in st.iter_records():
        ev.append([rec["n"], _iso(rec.get("at") or rec["t"], rec.get("z", 0)), rec.get("s", ""), rec["k"], _dumps(rec.get("d", {})), rec.get("h", "")])
    out.append(_write_text(os.path.join(dest, "events.csv"), _csv(ev, ["n", "time", "session", "kind", "data", "hash"])))
    return out


def _write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


# ---------------------------------------------------------------- the terminal
USAGE = {"en": """rofpalys stats [COMMAND] [OPTIONS]
  (nothing) | overview       today, week, month, year, all time + streaks + top songs / artists
  songs   [PERIOD]           ranking of songs      --top N   --by plays|time   --rule lastfm|spotify|starts|finished
  artists [PERIOD]           ranking of artists    folders [PERIOD]  ranking of folders
  days [N]                   day by day, the last N days (default 14): listening, Rofpalys open, plays
  hours [PERIOD]             listening per hour of the day          heatmap [PERIOD]   weekday x hour
  live                       real-time view (needs Rofpalys running; Ctrl+C ends)
  log [N]                    the last N events (play, pause, seek, volume, favourite, ...)    kinds [PERIOD]  what you did, by kind
  records                    personal bests          quality   how trustworthy the numbers are
  verify [--deep] [--anchor N:HASH]    check the hash chain (and recompute everything with --deep)       anchor   print the newest N:HASH to keep a copy
  export csv DIR | json FILE write the data out    define   how every number is counted
  status | selftest | reset --yes   (reset archives the log and starts a new one)
PERIOD: today yesterday week month 30d 90d year all        OPTIONS: --json  --lang id|en""",
         "id": """rofpalys stats [PERINTAH] [OPSI]
  (kosong) | overview        hari ini, minggu, bulan, tahun, sepanjang waktu + hari beruntun + lagu / artis teratas
  songs   [PERIODE]          peringkat lagu        --top N   --by plays|time   --rule lastfm|spotify|starts|finished
  artists [PERIODE]          peringkat artis       folders [PERIODE]  peringkat folder
  days [N]                   hari demi hari, N hari terakhir (default 14): mendengar, Rofpalys dibuka, putaran
  hours [PERIODE]            mendengar per jam dalam sehari          heatmap [PERIODE]   hari x jam
  live                       tampilan real-time (Rofpalys harus berjalan; Ctrl+C berhenti)
  log [N]                    N kejadian terakhir (putar, jeda, lompat, volume, favorit, ...)    kinds [PERIODE]  yang kamu lakukan, per jenis
  records                    rekor pribadi           quality   seberapa bisa dipercaya angkanya
  verify [--deep] [--anchor N:HASH]    cek rantai hash (dan hitung ulang semuanya dengan --deep)       anchor   cetak N:HASH terbaru untuk disimpan
  export csv FOLDER | json FILE   tulis datanya ke file    define   cara setiap angka dihitung
  status | selftest | reset --yes   (reset mengarsipkan log lalu memulai yang baru)
PERIODE: today yesterday week month 30d 90d year all       OPSI: --json  --lang id|en"""}
_PERIODS = {"today": "today", "yesterday": "yesterday", "week": "7d", "7d": "7d", "month": "month", "30d": "30d", "90d": "90d", "year": "year", "all": "all"}


def _opt(args, name, default=None, cast=str):
    if name in args:
        i = args.index(name)
        try:
            v = cast(args[i + 1])
        except (IndexError, ValueError):
            v = default
        del args[i:i + 2]
        return v
    return default


def _flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def cli(argv):
    args = list(argv)
    lg = _opt(args, "--lang", None) or X.lang()
    lg = "id" if str(lg).lower().startswith("id") else "en"
    js = _flag(args, "--json")
    top = _opt(args, "--top", 10, int)
    by = _opt(args, "--by", "plays")
    rule = _opt(args, "--rule", "lastfm")
    deep = _flag(args, "--deep")
    anchor = _opt(args, "--anchor", None)
    yes = _flag(args, "--yes")
    cmd = args.pop(0) if args and not args[0].startswith("-") else "overview"
    if cmd in ("help", "-h", "--help"):
        print(USAGE[lg])
        return 0
    period = _PERIODS.get(args[0], None) if args else None
    if rule not in C.RULES:
        rule = "lastfm"
    if by not in ("plays", "time"):
        by = "plays"
    v = View(None)
    out = lambda obj, text: print(json.dumps(obj, ensure_ascii=False, indent=1, default=str) if js else text)
    if cmd in ("overview", "summary"):
        ov = v.overview()
        ts = v.rank("all", "plays", "song", rule, 5)
        ta = v.rank("all", "plays", "artist", rule, 5)
        out({"overview": ov, "top_songs": ts, "top_artists": ta}, X.render_overview(ov, lg, ts, ta))
        if not ov["all"]["starts"] and not js:
            print(X.T(lg, "none"))
        return 0
    if cmd in ("songs", "artists", "folders"):
        level = {"songs": "song", "artists": "artist", "folders": "folder"}[cmd]
        rows = v.rank(period or "all", by, level, rule, top)
        out({"period": period or "all", "rows": rows}, X.render_rank(rows, lg, level=level))
        return 0
    if cmd == "days":
        n = int(args[0]) if args and args[0].isdigit() else 14
        rows = v.series(n)
        out({"days": rows}, X.render_days(rows, lg))
        return 0
    if cmd == "hours":
        t = v.totals(period or "30d")
        out({"hours": t["hours"], "open_hours": t["ohours"]}, X.render_hours(t, lg))
        return 0
    if cmd in ("heatmap", "heat"):
        hm = v.heat(period or "90d")
        out(hm, X.render_heat(hm, lg))
        return 0
    if cmd == "log":
        n = int(args[0]) if args and args[0].isdigit() else 40
        ev = v.events(n)
        out({"events": ev}, X.render_events(ev, lg, n))
        return 0
    if cmd == "kinds":
        k = v.kinds(period or "all")
        out(k, X.render_kinds(k, lg) or X.T(lg, "none"))
        return 0
    if cmd == "records":
        rc = v.records()
        out(rc, X.render_records(rc, lg))
        return 0
    if cmd == "quality":
        q = v.quality()
        ver = verify()
        ver["z"] = v.z()
        out({"quality": q, "integrity": ver}, X.render_quality(q, ver, lg))
        return 0 if ver["ok"] else 2
    if cmd == "verify":
        r = verify(deep, anchor)
        if js:
            print(json.dumps(r, indent=1))
        else:
            print("%s: %d record(s) in %d file(s); newest  n=%d  hash=%s" % ("OK" if r["ok"] else "PROBLEM", r["records"], r["files"], r["n"], r["head"]))
            if r["deep"] is not None:
                print("recomputed from the raw log: %s" % ("identical to the saved summary" if r["deep"] else "DIFFERENT"))
            for e in r["errors"]:
                print("  ERROR   " + e)
            for e in r["warnings"]:
                print("  warning " + e)
        return 0 if r["ok"] else 2
    if cmd == "anchor":
        r = verify()
        print("%d:%s" % (r["n"], r["head"]))
        if not js:
            print("Keep this line somewhere else (a note, an e-mail to yourself). Later:  rofpalys stats verify --anchor %d:%s" % (r["n"], r["head"]))
        return 0
    if cmd == "export":
        kind = args[0] if args else ""
        dest = args[1] if len(args) > 1 else ""
        if kind not in ("csv", "json") or not dest:
            print("usage: rofpalys stats export csv FOLDER | json FILE")
            return 1
        for f in export(kind, dest):
            print("written: " + f)
        return 0
    if cmd == "define":
        print(X.definitions(lg))
        return 0
    if cmd == "status":
        s = status()
        ver = verify()
        print(json.dumps(dict(s, chain_ok=ver["ok"], records=ver["records"], head=ver["head"]), indent=1))
        return 0
    if cmd == "selftest":
        return 0 if selftest() else 1
    if cmd == "reset":
        return _reset(yes, lg)
    if cmd == "live":
        return _live_cli(lg)
    print(USAGE[lg])
    return 1


def _reset(yes, lg):
    base = base_dir()
    if not yes:
        print("This moves the whole log and the summary into an archive folder and starts counting from zero.\nNothing is deleted. Run again with --yes." if lg == "en"
              else "Ini memindahkan seluruh log dan ringkasan ke folder arsip lalu mulai menghitung dari nol.\nTidak ada yang dihapus. Jalankan lagi dengan --yes.")
        return 1
    probe = _lock(os.path.join(base, "lock")) if os.path.isdir(base) else -1
    if probe is None:
        print("Rofpalys is running and writing to the log. Close it first." if lg == "en" else "Rofpalys sedang berjalan dan menulis ke log. Tutup dulu.")
        return 1
    try:
        names = [n for n in os.listdir(base) if _LOG_RE.match(n) or n in ("state.json", "live.json")]
        if not names:
            print("Nothing to archive." if lg == "en" else "Tidak ada yang diarsipkan.")
            return 0
        arc = os.path.join(base, "archive-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(arc)
        for n in names:
            os.replace(os.path.join(base, n), os.path.join(arc, n))
        print(("Archived %d file(s) to %s. A new log starts with the next run." if lg == "en" else "%d file diarsipkan ke %s. Log baru dimulai pada proses berikutnya.") % (len(names), arc))
        return 0
    finally:
        if probe is not None and probe >= 0:
            os.close(probe)


def _live_cli(lg):
    tty = sys.stdout.isatty()
    try:
        while True:
            v = View(None)
            n = v.now()
            t = v.totals("today")
            L = ["ROFPALYS  %s  %s" % (X.T(lg, "live").upper(), time.strftime("%H:%M:%S")), "─" * 60]
            if not n["recording"]:
                L.append("Rofpalys is not running." if lg == "en" else "Rofpalys tidak berjalan.")
            else:
                L.append("%s: %s" % (X.T(lg, "now_playing"), ((n["title"] + (" - " + n["artist"] if n["artist"] else "")) if n["title"] else X.T(lg, "nothing"))))
                if n["title"]:
                    L.append("   %s / %s   %s %s" % (X.fmt_mmss(n["pos"]), X.fmt_mmss(n["dur"]) if n["dur"] else "?", X.hbar((n["pos"] / n["dur"]) if n["dur"] else 0, 30), "▶" if n["playing"] else "‖"))
                L.append("%s: %s   %s %s   %s %d" % (X.T(lg, "session"), X.fmt_clock(n["session_up"]), X.T(lg, "heard"), X.fmt_clock(n["session_listen"]), X.T(lg, "songs"), n["session_plays"]))
            L.append("%s: %s %s   %s %s   %s %d   %s %d" % (X.T(lg, "today"), X.T(lg, "listening"), X.fmt_clock(t["listen"]), X.T(lg, "appopen"), X.fmt_clock(t["open"]), X.T(lg, "plays"), t["lastfm"], X.T(lg, "starts"), t["starts"]))
            sys.stdout.write(("\x1b[H\x1b[J" if tty else "") + "\n".join(L) + "\n")
            sys.stdout.flush()
            if not tty:
                return 0
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0


# ---------------------------------------------------------------- self test with a pretend player and a pretend clock
class _FakeClock:
    def __init__(self, wall=1_790_000_000_000, z=420):
        self.w, self.m, self.z = wall, 1000.0, z

    def wall(self):
        return int(self.w)

    def mono(self):
        return self.m

    def offset(self, w):
        return self.z

    def step(self, s, wall_extra=0.0):
        self.m += s
        self.w += (s + wall_extra) * 1000


class _FakeEngine:
    def __init__(self):
        self.playing_song_name, self.is_playing, self.is_paused = "", False, False
        self.current_time_seconds, self.total_time_seconds, self.duration_known = 0.0, 0.0, False
        self.volume, self.play_mode, self.favorites, self.lyrics_source = 50, 2, set(), ""
        self.exit_flag = False

    def get_mode_string(self):
        return "Sequential"


def selftest(verbose=True):
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="rofpalys-an-")
    ok = True

    def check(name, cond, extra=""):
        nonlocal ok
        ok = ok and bool(cond)
        if verbose:
            print("  [%s] %s %s" % ("ok" if cond else "FAIL", name, extra))
    try:
        clk, E = _FakeClock(), _FakeEngine()
        r = Recorder(E, "test", base=d, clock=clk, settle=0)
        check("recorder starts", r.start(thread=False))

        def run(sec, play=True, step=0.5):
            t = 0.0
            while t < sec - 1e-9:
                clk.step(step)
                if play and E.is_playing and not E.is_paused:
                    E.current_time_seconds += step
                r.tick()
                t += step
        E.playing_song_name, E.is_playing, E.total_time_seconds, E.duration_known = "/m/Alpha - Song One.mp3", True, 100.0, True
        run(60)                                                       # 60 s of a 100 s song
        E.is_paused = True
        run(30)                                                       # paused: not counted
        E.is_paused = False
        run(10)
        E.current_time_seconds = 20.0                                 # seek back
        run(10)
        E.volume = 70
        run(3)
        E.favorites.add(E.playing_song_name)
        run(1)
        E.playing_song_name, E.current_time_seconds, E.total_time_seconds = "/m/Beta - Song Two.mp3", 0.0, 40.0        # next song
        run(35)
        rr = r.view().totals("today")
        check("listening time is the audible time (60+10+10+3+1 s of song one + 35 s of song two, minus the seek)", 116.0 <= rr["listen"] <= 120.0, "%.1f" % rr["listen"])
        check("paused time (30 s) is not counted", rr["listen"] < 125)
        E.is_playing = False
        run(2, play=False)
        rr = r.view().totals("today")
        check("two songs started, both heard long enough", rr["starts"] == 2 and rr["spotify"] == 2, (rr["starts"], rr["spotify"], rr["lastfm"]))
        kinds = r.view().kinds("today")
        check("every kind of activity was recorded", all(kinds.get(k, 0) >= 1 for k in ("sess", "play", "pause", "resume", "seek", "vol", "fav", "fin")), kinds)
        r.note("test", {"x": 1})
        # crash: no stop(), a new recorder recovers it
        r._write_live(force=True)
        os.close(r.store.fd)
        r.store.fd = None
        r._unlock()
        r.state = "stopped"
        clk2 = _FakeClock(clk.w + 60000)
        r2 = Recorder(_FakeEngine(), "test", base=d, clock=clk2, settle=0)
        r2.start(thread=False)
        q = r2.view().quality()
        check("a killed session is closed as recovered", q["recovered"] == 1 and not [s for s in r2.agg.so if s != r2.sid], q["recovered"])
        r2.stop()
        res = Store(d).verify(deep=True)
        check("the hash chain verifies, deep recomputation equals the saved summary", res["ok"] and res["deep"], res["errors"][:2])
        # tamper
        p = os.path.join(d, Store(d).files()[0])
        raw = open(p, "rb").read()
        open(p, "wb").write(raw.replace(b'"to":70', b'"to":71', 1))
        check("an edited line is detected", not Store(d).verify()["ok"])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if verbose:
        print("analytics selftest:", "OK" if ok else "FAILED")
    return ok


# END-OF-FILE rofpalys_analytics.py

