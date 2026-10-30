#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - main launcher. File name here: rofpalys.py  (so phones can download/open it)
# Install it as:  cp rofpalys.py $PREFIX/bin/rofpalys
#
# Copyright (C) 2026 rofpalys-nagiryu
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details. You should have received a copy of the GNU General Public
# License along with this program. If not, see <https://www.gnu.org/licenses/>.
"""Rofpalys launcher = the PARENT file. It finds every other file, checks that none was cut off, installs them and starts the program.

  rofpalys.py                 this file  (installed as the command  rofpalys)
  CORE FILES (required)       rofpalys_library / _sleep / _lyrics / _CyroKayAI_* (9 files, below) / _queue / _effects / _spectrum / _stats / _playlists / _alarm /
                              _control / _engine / _media / _tui / _gui_base / _gui   .py       -> the list is MODULES below
  THE LYRIC BRAIN (CyroKayAI 3)  rofpalys_CyroKayAI_lyric.py  = the conductor: creator check, internet check, fitting every line to the real voice, 🎶 / 🎵 markers
                              _ears (listening: voice / melody / notes / tempo)   _text (syllables, silences, word times)   _learn (teaches a voice
                              detector on the song itself)   _memory (what it learned from your songs and corrections)   _turbo (all processor cores)
                              _clock (steady song clock + Spotify-style scroll maths)   _view (the Tk screen that draws the live lyrics)
                              _providers (where the lyrics come from: syncedlyrics first, then lrcdl, lyriq, librelyrics; each judged by the audio fit).
                              rofpalys_lyrics.py asks the brain first; this launcher only installs the files and runs  rofpalys lyrics ...
  SUPPORT FILES (optional)    rofpalys_analytics.py (+ _calc, _text) = the statistics recorder and its tamper-evident log, rofpalys_theme.py = the three looks
                              (Classic / Modern / Cyberpunk: colours AND shapes AND type - the whole window is built again when you switch), rofpalys_gui_stats_charts.py
                              = the drawing parts of the Statistics page (a menu item in the sidebar, right under Visual). Without them the player still starts;
                              it just has no statistics and only the Classic look.  Commands:  rofpalys stats ...   rofpalys theme ...
  FEATURE FILES (optional)    rofpalys_gui_playlists.py, rofpalys_gui_queue.py, rofpalys_gui_stats.py, rofpalys_gui_theme.py, rofpalys_gui_effects.py,
                              rofpalys_gui_sleep.py, rofpalys_gui_lyrics.py ...  and any file YOU add: rofpalys_gui_<name>.py

Add a feature = add one file:  copy rofpalys_gui_template.py to rofpalys_gui_<name>.py, edit it, then  python ~/rofpalys.py install.
Nothing else has to change: the launcher discovers the file, checks it (its last line must be  # END-OF-FILE <its name>), installs it, and the
GUI loads it by itself.  List everything with  rofpalys features ,  check completeness with  rofpalys verify .
"""
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

VERSION = "5.8"
REPO_RAW = "https://raw.githubusercontent.com/rofpalys-nagiryu/rofpalys-/main/"
SELF = os.path.realpath(__file__)
MODULES = ("rofpalys_library.py", "rofpalys_sleep.py", "rofpalys_lyrics.py", "rofpalys_CyroKayAI_ears.py", "rofpalys_CyroKayAI_text.py", "rofpalys_CyroKayAI_turbo.py", "rofpalys_CyroKayAI_memory.py", "rofpalys_CyroKayAI_providers.py",
           "rofpalys_CyroKayAI_learn.py", "rofpalys_CyroKayAI_clock.py", "rofpalys_CyroKayAI_view.py", "rofpalys_CyroKayAI_lyric.py", "rofpalys_queue.py", "rofpalys_effects.py", "rofpalys_spectrum.py", "rofpalys_stats.py",
           "rofpalys_playlists.py", "rofpalys_alarm.py", "rofpalys_control.py", "rofpalys_engine.py", "rofpalys_media.py", "rofpalys_tui.py",
           "rofpalys_gui_base.py", "rofpalys_gui.py")        # REQUIRED files. Any other rofpalys_*.py (e.g. rofpalys_gui_playlists.py) is a feature file: found, checked and installed by itself
SUPPORT = ("rofpalys_theme.py", "rofpalys_analytics.py", "rofpalys_analytics_calc.py", "rofpalys_analytics_text.py", "rofpalys_gui_stats_charts.py")      # optional: the player starts without them
HOME = os.path.expanduser("~")
PREFIX = os.environ.get("PREFIX", "")
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.txt"
HELP = """Rofpalys %s - music player for Termux, Linux, macOS and Windows   (GPL-3.0-or-later)

  rofpalys                      terminal UI (whole library)
  rofpalys FILE|FOLDER|M3U ...  play songs from ANYWHERE (they join the list)
  rofpalys gui [FILE ...]       graphical UI with cover art, video and lyrics (needs a display; Termux: python-tkinter + X11/VNC)
  rofpalys media [reset]        show / delete the downloaded cover art and video cache
  rofpalys scan                 scan home + phone storage and print what was found
  rofpalys yt URL               download audio with yt-dlp and play it
  rofpalys doctor               check players, storage access, tools; suggests fixes
  rofpalys integrate            Termux: share a song/link from any app -> plays here; shortcuts for the Termux:Widget
  rofpalys ctl COMMAND          steer the running player: next, prev, toggle, vol +5, seek +10, sleep 30, queue FILE, fx slowed, lyrics sync ...   (rofpalys ctl help)
  rofpalys lyrics FILE ...      CyroKayAI: who made it -> internet -> listen -> fetch -> fit the lyrics to the real voice (🎶 / 🎵 for the melody)
  rofpalys lyrics melody|analyze|timeline|cut|all|bench|learn|forget|view|providers|reset|selftest   (rofpalys lyrics help)
  rofpalys lyrics providers [install]   lyric sources: syncedlyrics (first) -> lrcdl -> lyriq -> librelyrics -> built-in LRCLIB / YouTube / lyrics.ovh
  rofpalys now [--json]         what is playing right now
  rofpalys stats [PAGE]         statistics in the terminal: overview, songs, artists, days, hours, heatmap, log, records, quality, verify, export ...   (rofpalys stats help)
  rofpalys theme [NAME]         the look: classic (brown) | modern | cyberpunk - an open window follows at once (F6 in the window switches too)
  rofpalys daemon               player without a window: notification buttons, alarms and ctl keep working in the background
  rofpalys install [-y]         put all files in place by itself (modules, command, permissions) and check everything
  rofpalys verify               check that every installed file is complete (finds a paste that was cut off)
  rofpalys features             list the core files and the feature files (rofpalys_gui_<name>.py) and which are on
  rofpalys reset [-y] [--keep-favorites] [--keep-stats]   DEEP reset: delete everything Rofpalys stored (settings, favorites, lyrics + CyroKayAI measurements, caches, statistics history...); never your songs
  rofpalys update               fetch the newest files from GitHub
  rofpalys --license | --version | --help
""" % VERSION


def libdir():
    """Where the 4 module files live: next to this file, $ROFPALYS_HOME, $PREFIX/lib/rofpalys, ~/.local/share/rofpalys."""
    cands = [os.environ.get("ROFPALYS_HOME"), os.path.dirname(SELF), os.path.join(PREFIX, "lib", "rofpalys") if PREFIX else None,
             os.path.join(HOME, ".local", "share", "rofpalys")]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "rofpalys_engine.py")):
            return c
    return None


def install_dir():
    if PREFIX and os.access(os.path.join(PREFIX, "lib"), os.W_OK):
        return os.path.join(PREFIX, "lib", "rofpalys")
    return os.path.join(HOME, ".local", "share", "rofpalys")


def make_executable(path):
    try:
        mode = os.stat(path).st_mode
        if (mode & 0o111) != 0o111:
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return True
    except OSError:
        pass
    return False


def fix_permissions(d):
    """The equivalent of: chmod +x $PREFIX/bin/rofpalys  and the module files. Runs on every start (cheap)."""
    changed = [p for p in [SELF] + ([os.path.join(d, m) for m in MODULES] if d else []) if os.path.isfile(p) and make_executable(p)]
    if changed and "--quiet" not in sys.argv:
        print("[rofpalys] permissions set (chmod +x): " + ", ".join(os.path.basename(p) for p in changed))


def fetch(name, timeout=25):
    req = urllib.request.Request(REPO_RAW + name, headers={"User-Agent": "Rofpalys-updater/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------------ automatic install: finds the downloaded / pasted files and puts them in place
def bin_path():
    b = os.path.join(PREFIX, "bin") if PREFIX else ""
    if b and os.path.isdir(b) and os.access(b, os.W_OK):
        return os.path.join(b, "rofpalys")
    return os.path.join(HOME, ".local", "bin", "rofpalys")


def is_installed():
    return os.path.realpath(SELF) == os.path.realpath(bin_path())


_NAME = re.compile(r"^(rofpalys(?:_[A-Za-z0-9_]*[A-Za-z0-9])?)(?:[ _-]?\(\d+\))?\.py$")        # rofpalys.py, rofpalys_<anything>.py (capitals allowed: rofpalys_CyroKayAI_lyric.py), and copies like "name (1).py"

# MANIFEST-BEGIN (written by the release script: lines, bytes, sha256[:16] of each module of this release)
MANIFEST = {
    'rofpalys_CyroKayAI_clock.py': (360, 17645, '656b01e37d271021'),
    'rofpalys_CyroKayAI_ears.py': (663, 28849, 'c9c35c279c607b2a'),
    'rofpalys_CyroKayAI_learn.py': (327, 17038, 'b1edc1129a4480e5'),
    'rofpalys_CyroKayAI_lyric.py': (1561, 79577, '564b5de27f13d2bc'),
    'rofpalys_CyroKayAI_memory.py': (255, 10283, 'cde0ae65bee108bb'),
    'rofpalys_CyroKayAI_providers.py': (877, 41122, 'cbc31fc857c1734c'),
    'rofpalys_CyroKayAI_text.py': (109, 5352, 'ffbe6e488ca586fb'),
    'rofpalys_CyroKayAI_turbo.py': (193, 7473, '1234a55bdd5e63fd'),
    'rofpalys_CyroKayAI_view.py': (392, 18487, '165714b359ba9027'),
    'rofpalys_alarm.py': (139, 4420, '2b7914a29c27cb11'),
    'rofpalys_analytics.py': (1470, 66986, 'bb678a45f168f1c1'),
    'rofpalys_analytics_calc.py': (644, 28716, '1b31b645f7a9ecc6'),
    'rofpalys_analytics_text.py': (463, 30090, '7ddaa1ade0562c03'),
    'rofpalys_control.py': (372, 15188, 'f05ef99c5508e321'),
    'rofpalys_effects.py': (108, 3897, '2caaee0ecedfa7a8'),
    'rofpalys_engine.py': (1249, 51087, '3868b878fce4d2d4'),
    'rofpalys_gui.py': (1816, 85283, '87fb4ae3419d5475'),
    'rofpalys_gui_base.py': (1021, 59581, '7b01df09c3c9013d'),
    'rofpalys_gui_effects.py': (71, 3164, '4b6e65e83cf42d05'),
    'rofpalys_gui_lyrics.py': (270, 13617, '8c439a671b897ac1'),
    'rofpalys_gui_lyricview.py': (360, 14629, 'ed57aa52eae10ad7'),
    'rofpalys_gui_playlists.py': (262, 10691, '2528c43835f0687e'),
    'rofpalys_gui_queue.py': (132, 4960, 'a2c8bbb0f78b6dab'),
    'rofpalys_gui_sleep.py': (224, 11752, 'c846aa6ddd53f16d'),
    'rofpalys_gui_stats.py': (962, 50057, '42e10f7abba56f23'),
    'rofpalys_gui_stats_charts.py': (258, 13415, 'a0f6d5b5fd57bae6'),
    'rofpalys_gui_template.py': (40, 2863, '05bbf8bd18a1b8ad'),
    'rofpalys_gui_theme.py': (222, 12016, '268f7cc2689bc714'),
    'rofpalys_library.py': (414, 17670, 'b606b29b5e931380'),
    'rofpalys_lyrics.py': (455, 19255, '1adff1aae7a6b762'),
    'rofpalys_media.py': (768, 26684, 'a3d366e974e789e5'),
    'rofpalys_playlists.py': (210, 5990, '05d55e1b6ac911ec'),
    'rofpalys_queue.py': (87, 2403, '8adecdd25eefd72e'),
    'rofpalys_sleep.py': (227, 9811, 'd3df24d66c1d5e6e'),
    'rofpalys_spectrum.py': (139, 4718, '291280a9d1979b29'),
    'rofpalys_stats.py': (127, 4435, '8c1eea720668640f'),
    'rofpalys_theme.py': (525, 26240, 'c54c73aac21053fa'),
    'rofpalys_tui.py': (673, 26513, 'e30bf0a6edc44a54'),
}
# MANIFEST-END


def find_sources():
    """{'rofpalys_gui.py': [(mtime, path), ...newest first]} - every copy found next to this script, in the current folder, home and Downloads."""
    dirs = [os.path.dirname(SELF), os.getcwd(), HOME, os.path.join(HOME, "storage", "downloads"), os.path.join(HOME, "storage", "shared", "Download"),
            os.path.join(HOME, "Downloads")]
    seen, found = set(), {}
    for d in dirs:
        d = os.path.realpath(d)
        if d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for f in names:
            m = _NAME.match(f)
            if not m:
                continue
            path = os.path.join(d, f)
            try:
                mt = os.path.getmtime(path)
            except OSError:
                continue
            found.setdefault(m.group(1) + ".py", []).append((mt, path))
    for k in found:
        found[k].sort(reverse=True)
    return found


def inspect(path, name):
    """('ok' | 'modified' | 'cut' | 'broken', explanation).
    cut = the file stops early (typical when a long paste into nano is cut off) - it may still be valid Python, so it is detected by
    the END-OF-FILE marker and by the line count of the release."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return "broken", str(e)
    lines, sha = data.count(b"\n"), hashlib.sha256(data).hexdigest()[:16]
    exp = MANIFEST.get(name)
    if exp and sha == exp[2]:
        return "ok", ""
    if exp and hashlib.sha256(data.replace(b"\r\n", b"\n").rstrip() + b"\n").hexdigest()[:16] == exp[2]:
        return "ok", ""                                                        # only blank lines at the end / Windows line ends differ: copying and downloading add those
    try:
        compile(data, path, "exec")
    except SyntaxError as e:
        return "broken", "syntax error at line %s - the file has a pasting mistake or is cut off (%d lines%s)" % (e.lineno, lines, (", release: %d" % exp[0]) if exp else "")
    if (b"END-OF-FILE " + name.encode()) not in data.rstrip()[-300:]:
        return "cut", "the file stops early: %d lines%s - the paste was cut off" % (lines, (", the release has %d" % exp[0]) if exp else "")
    if exp:
        return "modified", "differs from this release (%d lines, release: %d) - edited or from another version" % (lines, exp[0])
    return "ok", ""


def _put(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    make_executable(dest)


def read_feature_meta(path):
    """FEATURE = {...} of a feature file, read WITHOUT running it (None if there is none)."""
    import ast
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "FEATURE" for t in node.targets):
                return ast.literal_eval(node.value)
    except Exception:
        pass
    return None


def cmd_features(d):
    """What is installed: the required core files and every feature file (rofpalys_gui_<name>.py ...) with its title, version and state."""
    if d is None:
        print("Rofpalys is not installed here.  Run:  python rofpalys.py install")
        return 1
    print("Rofpalys %s - program folder: %s\n" % (VERSION, d))
    print("CORE FILES (required)")
    for n in MODULES:
        st = "ok" if os.path.isfile(os.path.join(d, n)) and inspect(os.path.join(d, n), n)[0] in ("ok", "modified") else "PROBLEM"
        print("  %-8s %s" % (st, n))
    print("\nSUPPORT FILES (optional: without them there are no statistics and only the Classic look)")
    for n in SUPPORT:
        have = os.path.isfile(os.path.join(d, n))
        st = inspect(os.path.join(d, n), n)[0] if have else "absent"
        print("  %-8s %s" % ({"ok": "ok", "modified": "ok", "absent": "absent", "cut": "CUT OFF", "broken": "CUT OFF"}[st], n))
    print("\nFEATURE FILES (optional: add a file here and it is used the next time you start the program)")
    feats = sorted(f for f in os.listdir(d) if re.match(r"^rofpalys_[A-Za-z0-9_]+\.py$", f) and f not in MODULES and f not in SUPPORT)
    for f in feats:
        meta = read_feature_meta(os.path.join(d, f)) or {}
        st, why = inspect(os.path.join(d, f), f)
        state = "CUT OFF" if st in ("cut", "broken") else ("off" if meta.get("enabled") is False else "on")
        print("  %-8s %-28s v%-5s %s" % (state, f, meta.get("version", "?"), meta.get("title", "(no FEATURE info)")))
    if not feats:
        print("  (none)")
    print("\nAdd a feature: copy rofpalys_gui_template.py to rofpalys_gui_<name>.py, edit it, run  python ~/rofpalys.py install")
    return 0


def cmd_verify(d):
    """Are the installed files complete? (Catches a paste that was cut off.)"""
    if d is None:
        print("Rofpalys: no installed modules found.  Run:  python rofpalys.py install")
        return 1
    bad = 0
    print("Checking %s" % d)
    extras = sorted({f for f in os.listdir(d) if re.match(r"^rofpalys_[A-Za-z0-9_]+\.py$", f)} | set(MANIFEST)) if os.path.isdir(d) else []
    for name in list(MODULES) + [n for n in extras if n not in MODULES]:
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            if name in MODULES:
                print("  MISSING   %s" % name)
                bad += 1
            else:
                print("  absent    %s   (optional %s file - not installed)" % (name, "support" if name in SUPPORT else "feature"))
            continue
        st, why = inspect(p, name)
        print("  %-9s %s%s%s" % ({"ok": "ok", "modified": "changed", "cut": "CUT OFF", "broken": "BROKEN"}[st], name, "" if name in MODULES else ("   (support)" if name in SUPPORT else "   (feature)"), ("   " + why) if why else ""))
        bad += st in ("cut", "broken")
    if bad:
        print("\nFix: download the marked file(s) again (tap the file card, do not paste), put it in Downloads or ~, then run:  python ~/rofpalys.py install")
    return 1 if bad else 0


def cmd_install(args=(), auto=False):
    """Does by itself what used to be typed by hand: move the module files into the lib folder, install the command into bin, chmod +x.
    Every file is checked first; a cut-off copy is never installed (an older complete copy is used if there is one)."""
    yes = "-y" in args or "--yes" in args
    found, target, bp = find_sources(), install_dir(), bin_path()
    problems, done, warns = [], [], []
    names = list(MODULES) + sorted(n for n in found if n not in MODULES and n != "rofpalys.py")      # feature files are picked up automatically
    for name in names:
        chosen, errs = None, []
        for mt, src in found.get(name, []):
            st, why = inspect(src, name)
            if st in ("ok", "modified"):
                chosen = src
                if st == "modified":
                    warns.append("%s: %s" % (name, why))
                break
            errs.append("%s: %s" % (src, why))
        if chosen:
            dest = os.path.join(target, name)
            if os.path.realpath(chosen) != os.path.realpath(dest):
                _put(chosen, dest)
                done.append(name)
                if os.path.dirname(os.path.realpath(chosen)) == os.path.realpath(HOME):      # like the old `mv ~/rofpalys_*.py ...`
                    try:
                        os.remove(chosen)
                    except OSError:
                        pass
        else:
            have = os.path.join(target, name)
            if errs:
                problems.append("%s - %s" % (name, "; ".join(errs)))
            elif not os.path.isfile(have) and name in MODULES:
                problems.append("%s: not found (looked in %s, ~, Downloads)" % (name, os.path.dirname(SELF)))
            if os.path.isfile(have) and errs:
                st, why = inspect(have, name)
                if st in ("cut", "broken"):
                    problems.append("%s: the INSTALLED copy is also bad (%s)" % (name, why))
    cands = list(found.get("rofpalys.py", []))
    if SELF.endswith(".py") and not is_installed():
        cands.append((os.path.getmtime(SELF), SELF))
    for mt, src in sorted(cands, reverse=True):
        st, why = inspect(src, "rofpalys.py")
        if st in ("ok", "modified"):
            if os.path.realpath(src) != os.path.realpath(bp):
                _put(src, bp)
                done.append("rofpalys (command)")
            break
        problems.append("rofpalys.py (%s): %s" % (src, why))
    make_executable(bp)
    for m in names:
        make_executable(os.path.join(target, m))
    if done:
        print("[rofpalys] installed: " + ", ".join(done))
        print("           modules -> %s\n           command -> %s" % (target, bp))
    for w in warns:
        print("[rofpalys] note: " + w)
    if problems:
        print("[rofpalys] PROBLEMS - these files are incomplete. Download them again (tap the file card instead of pasting), then run  python rofpalys.py install :")
        for pr in problems:
            print("   - " + pr)
        return 1
    if not done:
        print("[rofpalys] everything is already installed and up to date.")
    if not auto:
        missing = []
        for tool, pkg in (("mpv", "mpv"), ("ffmpeg", "ffmpeg"), ("yt-dlp", "yt-dlp")):
            if not shutil.which(tool):
                missing.append(pkg)
        try:
            import tkinter  # noqa: F401
        except ImportError:
            missing.append("python-tkinter")
        if missing and shutil.which("pkg"):
            ok = yes
            if not yes:
                try:
                    ok = input("Install missing tools (%s) with pkg now? [Y/n] " % " ".join(missing)).strip().lower() in ("", "y", "yes")
                except (EOFError, KeyboardInterrupt):
                    ok = False
            if ok:
                subprocess.call(["pkg", "install", "-y"] + missing)
        elif missing:
            print("[rofpalys] optional tools missing: %s" % ", ".join(missing))
        sys.path.insert(0, target)
        cmd_doctor(target)
    elif shutil.which("pkg"):
        print("           (tools like mpv/ffmpeg/yt-dlp:  rofpalys install   - it offers to install them)")
    return 0

def start_recorder(surface):
    """Start the statistics recorder (rofpalys_analytics.py) for this program: 'gui', 'tui' or 'daemon'. Silent and harmless when the file is missing or anything goes wrong:
    the music must never depend on its statistics."""
    if os.environ.get("ROFPALYS_NO_STATS"):
        return None
    try:
        import rofpalys_analytics as AN
        import rofpalys_engine as E
        return AN.start(E, surface)
    except Exception:
        return None


def cmd_daemon(d):
    """The player without a window: the control socket, the notification buttons and the alarms keep working (start it with `nohup rofpalys daemon &`)."""
    import signal
    sys.path.insert(0, d)
    import rofpalys_alarm as AL
    import rofpalys_control as CT
    import rofpalys_engine as E
    import rofpalys_stats as ST
    E.load_favorites()
    E.load_settings()
    ST.load()
    E.refresh_playlist()
    E.scan_library_async()
    on = CT.start(E, notify=E.notify_controls)
    if not on["socket"]:
        print("Another Rofpalys is already running (the control socket is taken). Close it first, or just use:  rofpalys ctl ...")
        return 1
    start_recorder("daemon")                               # statistics: what the daemon plays and what you do through ctl and the notification buttons
    AL.start(E.alarm_fire)
    stop = []
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *a: stop.append(1))
    print("Rofpalys daemon is running (notification buttons: %s). Steer it with:  rofpalys ctl help   |   Ctrl+C stops it." % ("on" if on["notification"] else "off"))
    print("Termux tip: run  termux-wake-lock  so Android does not put it to sleep (needed for alarms).")
    try:
        while not stop:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        AL.stop()
        CT.stop_server()
        E.shutdown()
    return 0


def cmd_reset(d, args):
    """Deep reset from the terminal. Deletes only what Rofpalys created for itself (see rofpalys_engine.reset_everything)."""
    sys.path.insert(0, d)
    import rofpalys_engine as E
    import rofpalys_library as lib
    pidf = os.path.join(lib.CACHE_DIR, "gui.pid")
    try:
        with open(pidf) as f:
            pid = int(f.read().strip() or 0)
        if pid and pid != os.getpid() and os.name != "nt":
            os.kill(pid, 0)
            print("The Rofpalys window is still open (pid %d). Close it first - otherwise it saves its old state again when it closes." % pid)
            return 1
    except (OSError, ValueError):
        pass
    keep = "--keep-favorites" in args
    keep_stats = "--keep-stats" in args
    an_dir = os.path.join(lib.CONFIG_DIR, "analytics")
    if os.path.isdir(an_dir) and not keep_stats:
        try:
            import rofpalys_analytics as AN
            if AN.status()["recording_elsewhere"]:
                print("A Rofpalys program (window, terminal player or daemon) is still open and writing statistics. Close it first.")
                return 1
        except Exception:
            pass
    targets = [p for p in (os.path.join(lib.CONFIG_DIR, n) for n in ("rof_settings.json", "gui.json", "rof_favorites.json", "theme.json")) if os.path.isfile(p)]
    size = 0
    for root, _, files in os.walk(lib.CACHE_DIR):
        size += sum(os.path.getsize(os.path.join(root, f)) for f in files if os.path.exists(os.path.join(root, f)))
    print("DEEP RESET will delete:")
    for p in targets:
        if keep and p.endswith("rof_favorites.json"):
            continue
        print("   " + p)
    print("   %s   (lyrics, CyroKayAI measurements, covers, videos, library cache - %.1f MB)" % (lib.CACHE_DIR, size / 1048576.0))
    if os.path.isdir(an_dir):
        an_size = sum(os.path.getsize(os.path.join(r_, f_)) for r_, _, fs_ in os.walk(an_dir) for f_ in fs_ if os.path.exists(os.path.join(r_, f_)))
        print("   %s   (%s - %.1f MB)" % (an_dir, "statistics history: KEPT because of --keep-stats" if keep_stats else "ALL statistics history (the tamper-evident log); keep it with --keep-stats", an_size / 1048576.0))
    print("NOT touched: your songs, your own .lrc files, the audio in Music/ROFPALys, the Rofpalys program files.")
    if not ("-y" in args or "--yes" in args):
        try:
            if input("Type RESET to continue: ").strip() != "RESET":
                print("Cancelled.")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
    removed = E.reset_everything(keep_favorites=keep)
    if os.path.isdir(an_dir) and not keep_stats:
        try:
            shutil.rmtree(an_dir)
            removed = list(removed or []) + [an_dir]
        except OSError as e:
            print("could not remove %s: %s" % (an_dir, e))
    tj = os.path.join(lib.CONFIG_DIR, "theme.json")
    if os.path.isfile(tj):
        try:
            os.remove(tj)
            removed = list(removed or []) + [tj]
        except OSError:
            pass
    print("Done: %d item(s) removed. Start Rofpalys again - it begins like the first time." % len(removed))
    return 0


def cmd_update():
    d = libdir() or install_dir()
    os.makedirs(d, exist_ok=True)
    print("Updating from", REPO_RAW)
    ok = 0
    for name in ("rofpalys.py",) + MODULES + SUPPORT:
        try:
            data = fetch(name)
            compile(data, name, "exec")                    # never install a file that is not valid Python
            if b"rofpalys" not in data.lower():
                raise ValueError("does not look like a Rofpalys file")
        except Exception as e:
            if name not in SUPPORT:                        # an optional file that is not in the repository (yet) is no news
                print("  skip %-20s %s" % (name, e))
            continue
        dest = SELF if name == "rofpalys.py" else os.path.join(d, name)
        try:
            if os.path.exists(dest):
                shutil.copy2(dest, dest + ".bak")
            with open(dest + ".part", "wb") as f:
                f.write(data)
            os.replace(dest + ".part", dest)
            make_executable(dest)
            ok += 1
            print("  ok   %s" % name)
        except OSError as e:
            print("  FAIL %-20s %s" % (name, e))
    try:                                                   # GNU license text next to the code
        data = urllib.request.urlopen(LICENSE_URL, timeout=15).read()
        with open(os.path.join(d, "COPYING"), "wb") as f:
            f.write(data)
    except Exception:
        pass
    print("%d file(s) updated. (old versions kept as *.bak)" % ok)
    return 0 if ok else 1


def cmd_license(d):
    print("Rofpalys %s - Copyright (C) 2026 rofpalys-nagiryu" % VERSION)
    print("Licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later).")
    print("This is free software: you may redistribute and modify it under the terms of the GPL.")
    print("There is NO WARRANTY, to the extent permitted by law.")
    print("Full text: " + LICENSE_URL)
    if d and os.path.isfile(os.path.join(d, "COPYING")):
        print("Local copy: " + os.path.join(d, "COPYING"))
    else:
        print("Get a local copy with:  rofpalys update")
    return 0


def cmd_integrate():
    """Termux: 'Share -> Termux' from any app runs ~/bin/termux-file-editor (files) and ~/bin/termux-url-opener (links)."""
    import rofpalys_library as lib
    if not lib.IS_TERMUX:
        print("integrate is for Termux only. On Linux/macOS/Windows, set Rofpalys as the 'open with' app for audio files:  rofpalys %f")
        return 1
    sh = os.path.join(PREFIX, "bin", "sh")
    binp = os.path.join(HOME, "bin")
    os.makedirs(binp, exist_ok=True)
    scripts = os.path.join(HOME, ".shortcuts")             # Termux:Widget shows every script in this folder as a button
    os.makedirs(scripts, exist_ok=True)
    for label, body in (("Rofpalys Play-Pause", "rofpalys ctl toggle"), ("Rofpalys Next", "rofpalys ctl next"), ("Rofpalys Previous", "rofpalys ctl prev"),
                        ("Rofpalys Sleep 30 min", "rofpalys ctl sleep 30"), ("Rofpalys Volume up", "rofpalys ctl vol +10"), ("Rofpalys Volume down", "rofpalys ctl vol -10")):
        p = os.path.join(scripts, label)
        if os.path.exists(p) and "rofpalys-hook" not in open(p, errors="replace").read():
            continue
        with open(p, "w") as f:
            f.write("#!%s\n# rofpalys-hook\n%s\n" % (sh, body))
        make_executable(p)
    print("  ok   %s  (Termux:Widget buttons: Play-Pause, Next, Previous, Sleep 30, Volume)" % scripts)
    hooks = {"termux-file-editor": 'exec rofpalys play "$@"',
             "termux-url-opener": 'case "$1" in\n  http*|*youtu*) exec rofpalys yt "$1" ;;\n  *) exec rofpalys play "$@" ;;\nesac'}
    for name, body in hooks.items():
        p = os.path.join(binp, name)
        if os.path.exists(p) and "rofpalys-hook" not in open(p, errors="replace").read():
            print("  skip %s (you already have your own; backup not touched)" % p)
            continue
        with open(p, "w") as f:
            f.write("#!%s\n# rofpalys-hook\n%s\n" % (sh, body))
        make_executable(p)
        print("  ok   " + p)
    print("Now in any app: Share -> Termux. Audio files open in Rofpalys; YouTube links download and play.")
    return 0


def cmd_doctor(d):
    import platform
    import rofpalys_library as lib
    import rofpalys_engine as E
    print("Rofpalys %s | Python %s | %s%s" % (VERSION, platform.python_version(), sys.platform, " (Termux)" if lib.IS_TERMUX else ""))
    cmd_verify(d)
    print("modules : %s" % d)
    print("config  : %s" % lib.CONFIG_DIR)
    names = [e["name"] for e in E.AVAILABLE_ENGINES]
    print("players : %s" % (", ".join(names) or "NONE"))
    if not names:
        print("   -> install one:  pkg install mpv   (Termux)   |   sudo apt install mpv   |   brew install mpv")
    elif "mpv" not in names and "ffplay" not in names and "VLC" not in names:
        print("   -> only basic players found: no seek. Better:  pkg install mpv")
    print("seek    : %s" % ("yes" if any(e.get("seek") or e["name"] == "PyGame" for e in E.AVAILABLE_ENGINES) else "no (needs mpv/ffplay/VLC/mplayer/PyGame)"))
    print("ffprobe : %s" % ("ok" if shutil.which("ffprobe") else "missing -> no song length;  pkg install ffmpeg"))
    print("yt-dlp  : %s" % ("ok" if shutil.which("yt-dlp") else "missing -> no auto video / audio download;  pkg install yt-dlp"))
    print("control : %s%s" % ("socket ok" if hasattr(__import__("socket"), "AF_UNIX") else "no unix sockets here (rofpalys ctl is off)",
                              "; notification buttons ready (termux-notification found)" if shutil.which("termux-notification") else "; notification buttons need the Termux:API app + pkg install termux-api"))
    print("effects : %s" % ("mpv/ffplay found: equalizer, speed, slowed+reverb work" if ("mpv" in names or "ffplay" in names) else "need mpv (pkg install mpv) or ffplay"))
    print("spectrum: %s" % ("real audio visualizer ready (ffmpeg)" if shutil.which("ffmpeg") else "needs ffmpeg for the real visualizer; the simulation is used"))
    print("lyrics  : safety net LRCLIB + lyrics.ovh online%s" % ("; YouTube captions via yt-dlp" if shutil.which("yt-dlp") else " (install yt-dlp for YouTube captions)"))
    try:
        import rofpalys_CyroKayAI_providers as PV
        rows = PV.status()
        print("providers: %s" % "  >  ".join("%s %s" % (r["name"], ("ok" + (" " + r["version"] if r["version"] else "")) if r["installed"] else ("needs Python %d.%d+" % PV.MIN_PY[r["name"]]) if not r["python_ok"] else "MISSING") for r in rows))
        if any(not r["installed"] and r["python_ok"] for r in rows):
            print("          -> install the missing ones:  python ~/rofpalys.py lyrics providers install")
    except ImportError:
        print("providers: rofpalys_CyroKayAI_providers.py missing -> only the built-in LRCLIB / lyrics.ovh;  python ~/rofpalys.py install")
    try:
        import rofpalys_CyroKayAI_lyric as CK
        print("cyrokay : brain v%s | voice detector: %s | ffprobe (creator tags): %s | internet: %s | self-test: %s" % (
            CK.__version__, "full (numpy)" if CK.np is not None else "basic - for the full one: pkg install python-numpy", "ok" if shutil.which("ffprobe") else "missing (pkg install ffmpeg)",
            "online" if CK.internet_ok(force=True) else "offline", "OK" if CK.selftest(False) else "FAILED"))
        if CK.np is None:
            sb = os.path.join(PREFIX, "bin") if PREFIX else ""
            mine = bool(sb) and os.path.realpath(sys.executable).startswith(os.path.realpath(sb))
            print("          numpy    : missing for %s" % sys.executable)
            if PREFIX and not mine:
                print("          -> this is not Termux's own python (pyenv / venv): 'pkg install python-numpy' installs numpy for Termux's python, which this one cannot see.")
                print("             Either  pkg install python-numpy python-tkinter  and use Termux's python (pyenv global system),  or  pip install numpy  into this one (it compiles: slow).")
        try:
            import rofpalys_CyroKayAI_turbo as TB
            print("          processor: %s" % TB.describe())
        except ImportError:
            print("          processor: rofpalys_CyroKayAI_turbo.py missing -> single core")
        try:
            import rofpalys_CyroKayAI_memory as MEM
            print("          memory   : %s" % MEM.summary())
        except ImportError:
            print("          memory   : rofpalys_CyroKayAI_memory.py missing -> nothing is learned between songs")
        if not shutil.which("ffmpeg"):
            print("          -> without ffmpeg CyroKayAI cannot listen to the song: lyrics keep the times of the file, markers still work;  pkg install ffmpeg")
    except ImportError:
        print("cyrokay : rofpalys_CyroKayAI_lyric.py missing -> lyrics work the old way, without the exact sync;  python ~/rofpalys.py install")
    try:
        import rofpalys_analytics as AN
        print("stats   : %s" % AN.describe())
        print("          rofpalys stats  |  rofpalys stats verify  |  rofpalys stats export csv FILE  |  page: Statistik in the sidebar (under Visual), the chart button or F7")
    except ImportError:
        print("stats   : rofpalys_analytics.py (+ _calc, _text) missing -> no statistics;  python ~/rofpalys.py install")
    except Exception as e:
        print("stats   : problem reading the statistics: %r" % (e,))
    try:
        import rofpalys_theme as TH
        print("look    : %s  (colours + shapes + type; rofpalys theme classic|modern|cyberpunk; window: palette button or F6)" % TH.INFO[TH.current()]["name"])
    except ImportError:
        print("look    : rofpalys_theme.py missing -> only the Classic look;  python ~/rofpalys.py install")
    print("ffmpeg  : %s" % ("ok (cover conversion + video playback)" if shutil.which("ffmpeg") else "missing -> no cover art / video in the GUI;  pkg install ffmpeg"))
    try:
        import PIL  # noqa: F401
        print("pillow  : ok (faster cover scaling)")
    except ImportError:
        print("pillow  : not installed (optional; ffmpeg is used instead)")
    try:
        import tkinter  # noqa: F401
        print("tkinter : ok (GUI available, display: %s)" % (os.environ.get("DISPLAY") or "none"))
    except ImportError:
        print("tkinter : missing -> GUI off;  pkg install python-tkinter")
    if lib.IS_TERMUX:
        print("storage : %s" % ("ok" if os.path.isdir(os.path.join(HOME, "storage")) else "NOT linked -> run: termux-setup-storage"))
        print("volume  : %s" % ("termux-volume ok" if shutil.which("termux-volume") else "install Termux:API app + pkg install termux-api for the volume keys"))
    E.load_settings()
    t0 = time.time()
    roots = E._roots()
    print("scan    : roots = %s" % ", ".join(roots))
    n = len(lib.scan(roots, lib.AUDIO_EXTS, E.min_size_kb * 1024, skip_names=E.exclude_dirs))
    print("          %d songs found in %.1fs" % (n, time.time() - t0))
    return 0


def main(argv):
    d = libdir()
    fix_permissions(d)                                     # chmod +x on every start, even for --version
    if "--version" in argv or "-V" in argv:
        print("Rofpalys " + VERSION)
        return 0
    if argv[:1] in (["--help"], ["-h"], ["help"]):
        print(HELP)
        return 0
    if argv[:1] == ["--license"] or argv[:1] == ["license"]:
        return cmd_license(d)
    if argv[:1] == ["update"]:
        return cmd_update()
    if argv[:1] == ["install"]:
        return cmd_install(argv[1:])
    if not is_installed() and not os.environ.get("ROFPALYS_NO_AUTO") and SELF.endswith(".py"):
        rc = cmd_install(auto=True)                        # first run from a downloaded file: set everything up, then carry on
        if rc != 0:
            return rc
        bp = bin_path()
        try:
            os.execv(sys.executable, [sys.executable, bp] + argv)
        except OSError:
            pass
        d = libdir()
    if d is None:
        print("Rofpalys: module files not found (rofpalys_engine.py, ...).")
        print("Download all the files into one folder (Downloads or ~) and run:  python rofpalys.py install")
        return 1
    sys.path.insert(0, d)
    gone = [m for m in MODULES if not os.path.isfile(os.path.join(d, m))]
    if gone and argv[:1] not in (["verify"], ["reset"]):                       # a friendly message instead of a Python traceback
        print("Rofpalys: %d file(s) are missing in %s:\n   %s" % (len(gone), d, ", ".join(gone)))
        print("Download them again (tap the file card), put them in Downloads or ~, then run:  python ~/rofpalys.py install")
        return 1
    cmd, rest = (argv[0], argv[1:]) if argv and argv[0] in ("gui", "tui", "play", "scan", "yt", "doctor", "integrate", "media", "reset", "verify", "ctl", "now", "daemon", "features", "lyrics", "stats", "theme") else (None, argv)
    if cmd == "doctor":
        return cmd_doctor(d)
    if cmd == "integrate":
        return cmd_integrate()
    if cmd == "reset":
        return cmd_reset(d, rest)
    if cmd in ("ctl", "now"):
        import rofpalys_control as CT
        return CT.ctl_main((["now"] if cmd == "now" else []) + rest)
    if cmd == "daemon":
        return cmd_daemon(d)
    if cmd == "verify":
        return cmd_verify(d)
    if cmd == "features":
        return cmd_features(d)
    if cmd in ("stats", "theme"):
        mod = "rofpalys_analytics" if cmd == "stats" else "rofpalys_theme"
        try:
            M_ = __import__(mod)
        except ImportError as e:
            print("%s.py (or a file it needs) is missing: %s\nDownload it again (tap the file card), put it in Downloads or ~, then run:  python ~/rofpalys.py install" % (mod, e))
            return 1
        return M_.cli(rest)
    if cmd == "lyrics":
        try:
            import rofpalys_CyroKayAI_lyric as CK
        except ImportError:
            print("rofpalys_CyroKayAI_lyric.py is missing.  Download it again (tap the file card), put it in Downloads or ~, then run:  python ~/rofpalys.py install")
            return 1
        return CK.cli(rest)
    import rofpalys_library as lib
    if cmd == "scan":
        import rofpalys_engine as E
        E.load_settings()
        t0 = time.time()
        found = E.scan_library_sync()
        print("%d songs in %.1fs" % (len(found), time.time() - t0))
        for p in sorted(found)[:15]:
            print("  " + p)
        if len(found) > 15:
            print("  ... and %d more" % (len(found) - 15))
        if not found and lib.storage_hint():
            print("Hint: " + lib.storage_hint())
        return 0
    if cmd == "media":
        import rofpalys_media as M
        if rest[:1] == ["reset"]:
            M.reset_all()
            print("Downloaded cover art and video deleted (your own files were not touched).")
        a, v = M.cache_info()
        print("Cover art cache: %.1f MB | Video cache: %.1f MB | %s" % (a, v, M.MEDIA_DIR))
        return 0
    if cmd == "yt":
        if not rest:
            print("usage: rofpalys yt URL")
            return 1
        import rofpalys_tui
        start_recorder("tui")
        rofpalys_tui.run([], yt=rest[0])
        return 0
    paths, skipped = lib.resolve_inputs([a for a in rest if not a.startswith("--")])
    for s in skipped:
        print("skipped (not an audio file / folder / unreachable): " + s)
    if cmd == "gui":
        import rofpalys_gui
        if not hasattr(rofpalys_gui, "main"):
            print("rofpalys_gui.py is incomplete (cut off while pasting).  Check with:  rofpalys verify")
            return 1
        start_recorder("gui")
        return rofpalys_gui.main(paths)
    import rofpalys_tui
    if not hasattr(rofpalys_tui, "run"):
        print("rofpalys_tui.py is incomplete (cut off while pasting).  Check with:  rofpalys verify")
        return 1
    start_recorder("tui")
    rofpalys_tui.run(paths)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:                                 # e.g.  rofpalys ctl help | head
        sys.exit(0)

# END-OF-FILE rofpalys.py

