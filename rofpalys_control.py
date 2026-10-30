#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - remote control: `rofpalys ctl next`, `rofpalys now`, Termux notification with Prev / Play-Pause / Next buttons
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The running player (terminal UI, GUI or `rofpalys daemon`) opens a small local socket. Anything on the same phone/computer can then
steer it: the command line, Termux:Widget shortcuts, Tasker, a notification button, a script. Only the same user can connect."""
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time

import rofpalys_library as lib
import rofpalys_lyrics as LY
import rofpalys_sleep as SL

SOCK = os.path.join(lib.CACHE_DIR, "control.sock")
NOTIFY_ID = "7407"
HELP = """rofpalys ctl COMMAND [ARGS]      (the player must be running: rofpalys, rofpalys gui or rofpalys daemon)
  toggle | play | pause | resume | stop | next | prev
  play FILE            play a song from anywhere
  seek +10 | -10 | 90  jump (seconds, relative or absolute)
  vol 50 | +5 | -5     volume in percent
  mode 0-4 | next      0 single, 1 repeat one, 2 sequential, 3 loop all, 4 shuffle
  fav                  add / remove the current song from favorites
  sleep 30 | 02.00 | 00:00 [zone] | off     sleep timer (minutes, hours.minutes, or until a clock time)
  queue FILE | playnext FILE | clearqueue   Up next
  fx normal|bass|vocal|treble|lofi|slowed|nightcore | speed 1.25 | reverb off|light|hall | norm on|off
  lyrics               what CyroKayAI found out about the lyrics of this song (creator, internet, sync %)
  lyrics sync          check the creator + internet again, fetch and fit the lyrics to the voice now
  lyrics melody        melody-only track (🎶 / 🎵 following the music) instead of lyrics
  lyrics reset         delete saved lyrics + CyroKayAI measurements (deep reset of the lyric side), then fetch again
  lyrics skip on|off   skip the extra music part that the lyrics do not know (only when a cut plan exists)
  now [--json]         what is playing
  scan                 look for new songs"""


def _bin():
    prefix = os.environ.get("PREFIX", "")
    for c in (os.path.join(prefix, "bin", "rofpalys") if prefix else "", shutil.which("rofpalys") or ""):
        if c and os.path.isfile(c):
            return c
    return ""


def now(E):
    path = E.playing_song_name or ""
    artist, title = LY.guess(path) if path else ("", "")
    try:
        import rofpalys_queue as Q
        qn = len(Q.upnext)
    except Exception:
        qn = 0
    try:
        import rofpalys_effects as FX
        fx = FX.label()
    except Exception:
        fx = "off"
    sync = {}
    try:
        import rofpalys_CyroKayAI_lyric as CK
        R = CK.last(path) if path else None
        if R:
            sync = {"creator": (R.get("ident") or {}).get("artist", ""), "verified": bool(R.get("verified")), "online": bool(R.get("online")),
                    "sync": R.get("confidence"), "mode": R.get("mode")}
    except Exception:
        pass
    return {"ok": True, "lyrics_sync": sync, "playing": bool(E.is_playing and not E.is_paused), "paused": bool(E.is_paused), "path": path, "title": title or os.path.basename(path),
            "artist": artist, "pos": round(E.current_time_seconds, 1), "dur": round(E.total_time_seconds, 1) if E.duration_known else 0, "volume": E.volume,
            "mode": E.play_mode, "mode_name": E.get_mode_string(), "fav": path in E.favorites, "sleep_left": int(SL.remaining()) if SL.active() else 0,
            "queue": qn, "fx": fx, "lyrics": E.lyrics_source}


def _num(arg, cur, lo, hi):
    """'+5' / '-5' relative, '50' absolute."""
    v = float(arg)
    if arg.strip()[0] in "+-":
        v = cur + v
    return max(lo, min(hi, v))


def handle(E, line):
    """Run one command line, return the reply dict. Raises nothing."""
    try:
        parts = shlex.split(line)
    except ValueError:
        return {"ok": False, "error": "bad quotes"}
    if not parts:
        return {"ok": False, "error": "empty"}
    cmd, args = parts[0].lower(), parts[1:]
    try:
        if cmd in ("now", "status"):
            return now(E)
        if cmd == "toggle":
            E.toggle_play()
        elif cmd == "play":
            if args:
                paths, _ = lib.resolve_inputs([" ".join(args)])
                if not paths:
                    return {"ok": False, "error": "not an audio file"}
                E.add_external(paths)
                E.play_song(paths[0])
            else:
                E.resume() if E.is_paused else (E.toggle_play() if not E.is_playing else None)
        elif cmd == "pause":
            E.pause()
        elif cmd == "resume":
            E.resume()
        elif cmd == "stop":
            E.stop()
        elif cmd == "next":
            E.step(1)
        elif cmd in ("prev", "previous"):
            E.step(-1)
        elif cmd == "seek" and args:
            E.seek(_num(args[0], E.get_position(), 0, 36000))
        elif cmd in ("vol", "volume") and args:
            E.set_volume(_num(args[0], E.volume, 0, 100))
            E.save_settings()
        elif cmd == "mode":
            E.play_mode = (E.play_mode + 1) % 5 if (not args or args[0] == "next") else int(args[0]) % 5
            E.save_settings()
        elif cmd in ("fav", "like"):
            E.toggle_favorite()
        elif cmd == "sleep" and args:
            if args[0].lower() in ("off", "0", "stop", "cancel"):
                E.sleep_cancel()
            elif ":" in args[0] or (len(args) > 1) or (args[0].isdigit() and len(args[0]) == 4):
                hh, mm = SL.parse_clock(args[0])
                E.sleep_start_until(hh, mm, args[1] if len(args) > 1 else E.sleep_zone)
            else:
                E.sleep_start_duration(SL.parse_duration(args[0]))
        elif cmd == "queue" and args:
            paths, _ = lib.resolve_inputs([" ".join(args)])
            E.queue_add(paths)
        elif cmd == "playnext" and args:
            paths, _ = lib.resolve_inputs([" ".join(args)])
            E.queue_add(paths, front=True)
        elif cmd == "clearqueue":
            E.queue_clear()
        elif cmd == "fx" and args:
            E.fx_apply(preset=args[0])
        elif cmd == "speed" and args:
            E.fx_apply(speed=float(args[0]))
        elif cmd == "reverb" and args:
            E.fx_apply(reverb=args[0])
        elif cmd in ("norm", "normalize") and args:
            E.fx_apply(normalize=args[0].lower() in ("on", "1", "yes", "true"))
        elif cmd == "scan":
            E.scan_library_async()
        elif cmd in ("lyrics", "lyric", "lirik"):
            return _lyrics_cmd(E, args)
        else:
            return {"ok": False, "error": "unknown command: " + cmd}
    except (ValueError, IndexError) as e:
        return {"ok": False, "error": "bad argument (%s)" % e}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    return {"ok": True}


def _lyrics_cmd(E, args):
    """ctl lyrics [sync | melody | reset | skip on|off]  - the work runs in a thread, so the control socket answers at once."""
    try:
        import rofpalys_CyroKayAI_lyric as CK
    except Exception:
        return {"ok": False, "error": "rofpalys_CyroKayAI_lyric.py is not installed (python ~/rofpalys.py install)"}
    sub = args[0].lower() if args else ""
    path = E.playing_song_name or ""
    if sub in ("", "status", "info"):
        R = CK.last(path) if path else None
        return {"ok": True, "text": CK.describe(R) if R else "No CyroKayAI result for this song yet. Run:  rofpalys ctl lyrics sync"}
    if sub == "skip":
        CK.SKIP["on"] = bool(args[1:]) and args[1].lower() in ("on", "1", "yes", "true")
        return {"ok": True, "text": "skipping the extra music part: " + ("on" if CK.SKIP["on"] else "off")}
    if sub == "reset":
        n = CK.reset_cache()
        E.reset_lyrics()
        return {"ok": True, "text": "deleted %d file(s); the lyrics of this song are made again now" % n}
    if sub in ("sync", "melody"):
        if not path:
            return {"ok": False, "error": "nothing is playing"}
        threading.Thread(target=lambda: CK.sync_playing(E, melody=(sub == "melody")), daemon=True).start()
        return {"ok": True, "text": "CyroKayAI is working on it (creator -> internet -> listen -> fit). Check the result with:  rofpalys ctl lyrics"}
    return {"ok": False, "error": "unknown: lyrics " + sub}


# ------------------------------------------------------------------ server (inside the running player)
_server = {"sock": None, "thread": None}


def serve(E):
    """Start listening. Returns True if the socket is open (False on systems without unix sockets)."""
    if not hasattr(socket, "AF_UNIX") or _server["sock"] is not None:
        return _server["sock"] is not None
    try:
        os.makedirs(os.path.dirname(SOCK), exist_ok=True)
        if os.path.exists(SOCK):
            try:                                                    # a socket that nobody answers is a leftover of a crash
                c = socket.socket(socket.AF_UNIX)
                c.settimeout(0.5)
                c.connect(SOCK)
                c.close()
                return False                                        # another player is running: it keeps the control
            except OSError:
                os.remove(SOCK)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(SOCK)
        os.chmod(SOCK, 0o600)
        s.listen(4)
    except OSError:
        return False
    _server["sock"] = s

    def loop():
        while _server["sock"] is s:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            threading.Thread(target=_client, args=(E, conn), daemon=True).start()
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    _server["thread"] = t
    return True


def _client(E, conn):
    try:
        conn.settimeout(3)
        buf = b""
        while b"\n" not in buf and len(buf) < 4096:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buf += chunk
        line = buf.split(b"\n", 1)[0].decode("utf-8", "replace").strip()
        if line.startswith("{"):
            try:
                d = json.loads(line)
                line = " ".join([d.get("cmd", "")] + [shlex.quote(str(a)) for a in d.get("args", [])])
            except ValueError:
                pass
        conn.sendall((json.dumps(handle(E, line), ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError:
        pass
    finally:
        conn.close()


def stop_server():
    s, _server["sock"] = _server["sock"], None
    if s is not None:
        try:
            s.close()
            os.remove(SOCK)
        except OSError:
            pass


# ------------------------------------------------------------------ client (`rofpalys ctl ...`)
def request(line, timeout=3.0):
    if not hasattr(socket, "AF_UNIX"):
        return {"ok": False, "error": "this system has no unix sockets"}
    try:
        c = socket.socket(socket.AF_UNIX)
        c.settimeout(timeout)
        c.connect(SOCK)
        c.sendall((line + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = c.recv(4096)
            if not chunk:
                break
            data += chunk
        c.close()
        return json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": "Rofpalys is not running. Start it first:  rofpalys   |   rofpalys gui   |   rofpalys daemon"}


def fmt_now(d):
    if not d.get("path"):
        return "Nothing is playing."
    t = lambda s: "%d:%02d" % (int(s) // 60, int(s) % 60)
    state = "paused" if d["paused"] else ("playing" if d["playing"] else "stopped")
    left = ("   sleep in %s" % SL.fmt_left(d["sleep_left"])) if d.get("sleep_left") else ""
    ls = d.get("lyrics_sync") or {}
    lyr = ("   lyrics: %s%s" % (d.get("lyrics") or "-", (" %d%%" % round(ls["sync"] * 100)) if ls.get("sync") is not None else "")) if d.get("lyrics") else ""
    return "%s  %s%s   %s / %s   vol %d%%   %s   fx: %s   queue: %d%s%s" % (state, (d["artist"] + " - ") if d["artist"] else "", d["title"], t(d["pos"]), t(d["dur"]),
                                                                             d["volume"], d["mode_name"], d["fx"], d["queue"], left, lyr)


def ctl_main(argv):
    """Entry point for `rofpalys ctl ...` and `rofpalys now`. Returns the exit code."""
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(HELP)
        return 0
    as_json = "--json" in argv
    line = " ".join(shlex.quote(a) for a in argv if a != "--json")
    r = request(line)
    if not r.get("ok"):
        print(r.get("error", "failed"))
        return 1
    if "path" in r:
        print(json.dumps(r, ensure_ascii=False) if as_json else fmt_now(r))
    elif r.get("text"):
        print(r["text"])
    return 0


# ------------------------------------------------------------------ Termux notification with media buttons
def notify_available():
    return bool(shutil.which("termux-notification") and _bin())


def notify_loop(E):
    """Keeps one ongoing notification up to date (title, Prev / Play-Pause / Next buttons). Returns the thread or None."""
    if not notify_available():
        return None
    cmd = _bin()

    def send(path, paused):
        artist, title = LY.guess(path)
        args = ["termux-notification", "--id", NOTIFY_ID, "--ongoing", "--alert-once", "--priority", "low", "--group", "rofpalys",
                "--title", title or os.path.basename(path), "--content", (artist + "  ·  " if artist else "") + E.get_mode_string(),
                "--button1", "Prev", "--button1-action", "%s ctl prev" % cmd, "--button2", "Play" if paused else "Pause", "--button2-action", "%s ctl toggle" % cmd,
                "--button3", "Next", "--button3-action", "%s ctl next" % cmd]
        try:
            subprocess.run(args, capture_output=True, timeout=8)
        except Exception:
            pass

    def remove():
        try:
            subprocess.run(["termux-notification-remove", NOTIFY_ID], capture_output=True, timeout=8)
        except Exception:
            pass

    def loop():
        last, shown = None, False
        while not E.exit_flag:
            st = (E.playing_song_name, bool(E.is_paused), E.play_mode) if E.playing_song_name and E.is_playing else None
            if st != last:
                if st:
                    send(st[0], st[1])
                    shown = True
                elif shown:
                    remove()
                    shown = False
                last = st
            time.sleep(1.2)
        if shown:
            remove()
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def start(E, notify=True):
    """Start everything the running player offers to the outside. Returns what is active."""
    on = {"socket": serve(E)}
    on["notification"] = bool(notify and notify_loop(E))
    return on


# END-OF-FILE rofpalys_control.py

