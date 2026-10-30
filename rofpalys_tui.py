#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - terminal UI (curses): 19 animations, lyrics, visualizer
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
import math
import os
import random
import sys
import threading
import time

try:
    import curses
except ImportError:
    print("ERROR: the 'curses' module was not found.")
    print("Windows: pip install windows-curses     Others: install a Python build with curses.")
    sys.exit(1)

import rofpalys_alarm as AL
import rofpalys_control as CT
import rofpalys_effects as FX
import rofpalys_engine as E
import rofpalys_library as lib
import rofpalys_queue as Q
import rofpalys_sleep as SL
import rofpalys_stats as ST

tick = 0
current_anim_idx, last_anim_time = 0, 0.0
LOGO = ["╦═╗╔═╗╔═╗╔═╗╔═╗╦  ╦ ╦╔═╗", "╠╦╝║ ║╠╣ ╠═╝╠═╣║  ╚╦╝╚═╗", "╩╚═╚═╝╚  ╩  ╩ ╩╩═╝ ╩ ╚═╝"]


def hs(n):
    """Cheap deterministic hash (Python's hash(str) is slow and random per run)."""
    return (int(n) * 2654435761) & 0xFFFFFFFF


def safe(scr, y, x, text, attr, max_w=999):
    try:
        scr.addstr(y, x, text[:max_w], attr)
    except Exception:
        pass


def ac(pair, dim=True):
    if E.aura_mode:
        return curses.color_pair(3) | (curses.A_DIM if dim else curses.A_BOLD)
    return curses.color_pair(pair) | (curses.A_DIM if dim else curses.A_NORMAL)


# ================= 19 full-screen animations: fn(put, h, w, tk) =================
def a_rain(c, tail, ch=None):
    def f(put, h, w, tk):
        a = ac(c)
        for x in range(0, w, 2):
            dy = (tk // (1 + x % 3) + hs(x)) % (h + 8)
            for y in range(dy - tail, dy + 1):
                put(y, x, chr(random.randint(33, 126)), a)
    return f


def a_waves(put, h, w, tk):
    a = ac(11)
    for x in range(w):
        put(int((math.sin(x * .15 + tk * .4) + 1) / 2 * (h - 1)), x, "≈", a)
        put(int((math.cos(x * .1 - tk * .2) + 1) / 2 * (h - 1)), x, "≈", a)


def a_plasma(put, h, w, tk):
    a, chars = ac(14), " .-+*#%@"
    for y in range(h):
        sy = math.sin(y * .3 + tk * .3)
        for x in range(w):
            i = max(0, min(len(chars) - 1, int((math.sin(x * .1 + tk * .2) + sy + 2) / 4 * len(chars))))
            if chars[i] != ' ':
                put(y, x, chars[i], a)


def a_stars(put, h, w, tk):
    a = ac(15)
    for y in range(h):
        hy = hs(y)
        x = (hy - tk * (1 + hy % 3)) % w
        put(y, x, "★" if hs(x * y) % 5 == 0 else "·", a)


def a_dna(put, h, w, tk):
    a = ac(12)
    for x in range(w):
        s, c = math.sin(x * .1 + tk * .3), math.cos(x * .1 + tk * .3)
        w1, w2 = int((s + 1) / 2 * (h - 1)), int((c + 1) / 2 * (h - 1))
        if x % 4 == 0:
            for y in range(min(w1, w2) + 1, max(w1, w2)):
                put(y, x, "|", a)
        put(w1, x, "X" if w1 == w2 else ("/" if c > 0 else "\\"), a)
        if w2 != w1:
            put(w2, x, "\\" if c > 0 else "/", a)


def a_fire(put, h, w, tk):
    a, chars = ac(10), " .,:;+*#@"
    for x in range(w):
        inten = (math.sin(x * .3 + tk * .7) + math.cos(x * .5 - tk * 1.1) + 2) / 4
        hh = int(inten * h) + random.randint(0, 1)
        for y in range(h - hh, h):
            put(y, x, chars[min(len(chars) - 1, int(((y - (h - hh)) / max(1, hh)) * (len(chars) - 1)))], a)


def a_snow(put, h, w, tk):
    a = ac(2)
    for x in range(w):
        if hs(x) % 5:
            continue
        for y in range(h):
            drift = int(math.sin(tk * .1 + y * .5) * 4)
            if y == (tk // 3 + hs(x - drift)) % h:
                put(y, x, "❄" if hs(x * y) % 3 == 0 else "*", a)


def a_ripple(put, h, w, tk):
    a, cx, cy = ac(10), w // 2, h // 2
    for y in range(h):
        for x in range(w):
            v = math.sin(math.sqrt((x - cx) ** 2 + ((y - cy) * 3) ** 2) * .4 - tk * .6)
            if v > .4:
                put(y, x, "█" if v > .7 else "▓", a)


def a_eq(put, h, w, tk):
    a = ac(11)
    for x in range(w):
        top = h - int((math.sin(x * .2 + tk * .6) + math.cos(x * .4 - tk * .4) + 2) / 4 * h) - 1
        for y in range(top + 1, h):
            put(y, x, "█", a)
        put(top, x, "▄", a)


def a_rings(put, h, w, tk):
    a, cx, cy = ac(14), w // 2, h // 2
    for y in range(h):
        for x in range(w):
            if int(math.sqrt((x - cx) ** 2 + ((y - cy) * 2.5) ** 2) - tk * .8) % 12 == 0:
                put(y, x, "◎", a)


def a_sine2(put, h, w, tk):
    a1, a2, a3 = ac(15), ac(12), ac(11)
    for x in range(w):
        y1 = int(h // 2 + math.sin(x * .15 + tk * .3) * (h // 3))
        y2 = int(h // 2 + math.sin(x * .15 + tk * .3 + math.pi) * (h // 3))
        if x % 6 == 0:
            for y in range(min(y1, y2) + 1, max(y1, y2)):
                put(y, x, "|", a3)
        put(y1, x, "▤", a1)
        put(y2, x, "▥", a2)


def a_burst(put, h, w, tk):
    a, cx, cy = ac(2), w // 2, h // 2
    for y in range(h):
        for x in range(w):
            d = math.sqrt((x - cx) ** 2 + ((y - cy) * 2) ** 2)
            if int(d - tk * 2) % 15 == 0 and hs(int(math.atan2((y - cy) * 2, x - cx) * 10)) % 4 == 0:
                put(y, x, "✦" if hs(x) % 2 == 0 else ".", a)


def a_bubbles(put, h, w, tk):
    a = ac(13)
    for x in range(0, w, 4):
        put(h - ((tk // (2 + hs(x) % 3) + hs(x)) % (h + 5)), x, ["o", "O", "°", "0", "@"][hs(x) % 5], a)


def a_glitch(put, h, w, tk):
    a = ac(10)
    for y in range(h):
        if hs(tk + y) % 5 == 0:
            for x in range(w):
                if hs(tk + x + y) % 4 == 0:
                    put(y, x, random.choice(["█", "▓", "▒", "░", "≡"]), a)


def a_diag(put, h, w, tk):
    a1, a2 = ac(11), ac(14)
    for y in range(h):
        for x in range((tk - 2 * y) % 25, w, 25):
            put(y, x, "/", a1)
        for x in range((2 * y - tk) % 25, w, 25):
            put(y, x, "\\", a2)


def a_grid(put, h, w, tk):
    a = ac(15)
    for y in range(0, h, 3):
        for x in range(0, w, 4):
            p = math.sin(x * .1 + y * .2 + tk * .3)
            if p > .1:
                put(y, x, "┼" if p > .6 else "·", a)


def a_binary(put, h, w, tk):
    a = ac(12)
    for x in range(w):
        dp = (tk + hs(x)) % (h + 10)
        for y in range(dp - 5, dp + 1):
            put(y, x, "1" if random.random() > .5 else "0", a)


def a_fireworks(put, h, w, tk):
    r = tk % 15
    for i in range(2):
        cx, cy = hs((tk // 15) + i * 10) % w, hs((tk // 15) + i * 10 + 100) % (h // 2 + h // 4)
        a = ac(10 + i + (tk // 15) % 4)
        for y in range(max(0, cy - r // 2 - 2), min(h, cy + r // 2 + 3)):
            for x in range(max(0, cx - r - 2), min(w, cx + r + 3)):
                if abs(math.sqrt((x - cx) ** 2 + ((y - cy) * 2) ** 2) - r) < 1.0:
                    put(y, x, "✦" if hs(x + y) % 2 == 0 else "✧", a)


ANIMS = [a_rain(13, 2), a_waves, a_plasma, a_stars, a_dna, a_fire, a_snow, a_ripple, a_eq, a_rain(21, 3), a_rings, a_sine2, a_burst,
         a_bubbles, a_glitch, a_diag, a_grid, a_binary, a_fireworks]
TOTAL_ANIMATIONS = len(ANIMS)


def draw_background(scr, h, w):
    global current_anim_idx, last_anim_time

    def put(y, x, ch, attr):
        if 0 <= y < h and 0 <= x < w:
            try:
                scr.addstr(y, x, ch, attr)
            except Exception:
                pass
    playing = E.is_playing and not E.is_paused
    if playing and time.time() - last_anim_time > 5.0:
        current_anim_idx, last_anim_time = (current_anim_idx + 1) % TOTAL_ANIMATIONS, time.time()
    if not playing:                                       # idle: green-ish matrix rain
        base = ac([20, 21, 22, 23, 24, 25][(tick // 62) % 6], dim=False)
        for x in range(0, w, 2):
            head = ((tick * 3) // (1 + x % 2) + x * 11) % (h + 8)
            for dy in range(6):
                if random.random() > .05:
                    put(head - dy, x, chr(random.randint(33, 126)),
                        curses.color_pair(2) | curses.A_BOLD if dy == 0 else (base | curses.A_BOLD if dy == 1 else base))
        return
    ANIMS[current_anim_idx](put, h, w, tick)


# ================= small widgets =================
def progressbar(pct, width, tk):
    width = max(1, width)
    if pct < 0:                                           # unknown duration: bouncing block
        pos = (tk // 2) % (width * 2)
        pos = pos if pos < width else width * 2 - 1 - pos
        bar = ["░"] * width
        for i, ch in ((pos, "█"), (pos - 1, "▓"), (pos + 1, "▓")):
            if 0 <= i < width:
                bar[i] = ch
        return "".join(bar)
    blocks = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    fill = pct * width
    full = int(fill)
    if full >= width:
        return "█" * width
    return "█" * full + blocks[int((fill - full) * len(blocks))] + "░" * (width - full - 1)


def wave_eq(tk):
    bars = [' ', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    return " [" + "".join(bars[max(0, min(7, int((math.sin(tk * .4 + i * .8) + 1) / 2 * 7)))] for i in range(4)) + "]"


def draw_ui(scr):
    scr.erase()
    h, w = scr.getmaxyx()
    if E.anim_enabled:
        draw_background(scr, h, w)
    if h < 14 or w < 40:
        safe(scr, 0, 0, "Terminal window too small!", curses.color_pair(2) | curses.A_BOLD)
        return

    # --- layout that adapts to the terminal height (works with the phone keyboard open)
    logo_rows = 3 if h >= 24 else 1
    ctrl_rows = 5 if h >= 28 else (4 if h >= 27 else (3 if h >= 23 else 1))
    fixed = logo_rows + ctrl_rows + 9
    box_w = min(w - 4, 85)
    cw = box_w - 4
    sx = max(0, (w - box_w) // 2)

    BORDER = curses.color_pair(1) | (curses.A_BOLD if tick % 15 < 7 else curses.A_NORMAL)
    dyn = curses.color_pair(10 + (tick // 3) % 6) | curses.A_BOLD
    LOGO_C = dyn if E.is_playing and not E.is_paused else curses.color_pair(1) | curses.A_BOLD
    WB, NORMAL, DIM = curses.color_pair(2) | curses.A_BOLD, curses.color_pair(2), curses.color_pair(2) | curses.A_DIM
    ACTIVE, INFO_C, HEART, ALERT = curses.color_pair(3) | curses.A_BOLD, curses.color_pair(4) | curses.A_BOLD, curses.color_pair(5) | curses.A_BOLD, curses.color_pair(10) | curses.A_BOLD
    spinner = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'[tick % 10]

    # active synced lyric line
    act_idx, act_text = -1, ""
    if E.is_synced_lyrics and E.is_playing:
        for i, (sec, txt) in enumerate(E.synced_lyrics):
            if E.current_time_seconds >= sec:
                act_idx, act_text = i, txt
            else:
                break
    if act_text == "♪":                                   # instrumental part: no words, show the animated notes
        act_text = ("♪ " * (1 + (tick // 4) % 3)).strip()
    floating = E.ui_mode != 'lyrics' and E.is_playing and bool(act_text)
    banner = E.is_downloading or E.is_searching
    extra = (2 if banner else 0) + (2 if floating else 0)
    view = max(3, min(8, h - fixed - extra))
    box_h = fixed + extra + view
    sy = max(0, (h - box_h) // 2)
    for yy in range(sy, min(h, sy + box_h)):
        safe(scr, yy, sx, " " * box_w, curses.color_pair(2))
    row = sy

    def sep():
        nonlocal row
        safe(scr, row, sx, "╠" + "═" * (box_w - 2) + "╣", BORDER, box_w)
        row += 1

    def edges():
        safe(scr, row, sx, "║", BORDER, 1)
        safe(scr, row, sx + box_w - 1, "║", BORDER, 1)

    def line(text, attr, center=True):
        nonlocal row
        edges()
        safe(scr, row, sx + 2, (text.center(cw) if center else text.ljust(cw))[:cw], attr, cw)
        row += 1

    safe(scr, row, sx, "╔" + "═" * (box_w - 2) + "╗", BORDER, box_w)
    row += 1
    for ln in (LOGO if logo_rows == 3 else ["R O F P A L Y S   v" + E.__version__]):
        edges()
        safe(scr, row, sx + 1, ln.center(box_w - 2), LOGO_C, box_w - 2)
        row += 1
    sep()
    n = len(E.songs)
    tabs = (" [ PLAYLIST %d ] " % n if E.ui_mode == 'playlist' else "  PLAYLIST %d  " % n,
            " [ LYRICS ] " if E.ui_mode == 'lyrics' else "   LYRICS   ",
            " [ VISUALIZER ] " if E.ui_mode == 'visualizer' else "  VISUALIZER  ")
    line(" %s │ %s │ %s " % tabs, dyn | curses.A_BOLD)
    sep()
    if E.is_downloading:
        line("%s [YT-DLP] %s" % (spinner, E.dl_progress_text), ALERT, center=False)
        sep()
    elif E.is_searching:
        line("%s %s%s" % (spinner, E.t('search'), E.search_query) + ("█" if tick % 10 < 5 else "_"), INFO_C, center=False)
        sep()

    if E.ui_mode == 'playlist':
        if not E.songs:
            for i in range(view):
                msg = ""
                if i == view // 2:
                    msg = E.t('scanning') if E.scanning else E.t('empty')
                elif i == view // 2 + 1 and not E.scanning:
                    msg = lib.storage_hint()
                line(msg, DIM)
        win = max(0, min(E.selected_idx - view // 2, max(0, n - view)))
        for i in range(win, win + view) if E.songs else ():
            edges()
            if i < n:
                path = E.songs[i]
                name = E.title_of(path)
                active, fav = path == E.playing_song_name, path in E.favorites
                mw = max(4, cw - 20)
                shown = name[:mw]
                if active and len(name) > mw:
                    p = (tick // 3) % (len(name) + 4)
                    shown = (name + " • " + name)[p:p + mw]
                attr = WB if i == E.selected_idx else (ACTIVE if active else NORMAL)
                safe(scr, row, sx + 2, "➤ " if i == E.selected_idx else "  ", attr, 2)
                safe(scr, row, sx + 4, "♥ " if fav else "  ", HEART if fav else NORMAL, 2)
                safe(scr, row, sx + 6, "%02d. %-*s" % (i + 1, mw, shown), attr, mw + 4)
                if active and E.is_playing and not E.is_paused:
                    wv = wave_eq(tick)
                    safe(scr, row, sx + 10 + mw, wv, dyn, len(wv))
            row += 1
    elif E.ui_mode == 'lyrics':
        line(E.t('lyric_title'), INFO_C)
        if E.is_synced_lyrics and E.is_playing and time.time() - E.last_scroll_time > 3.0:
            E.lyrics_scroll = max(0, act_idx - (view - 1) // 2)
        for i in range(E.lyrics_scroll, E.lyrics_scroll + view - 1):
            if i < len(E.current_lyrics):
                if i == act_idx and E.is_playing:
                    edges()
                    txt = " %s " % E.current_lyrics[i]
                    pad = max(0, (cw - len(txt)) // 2)
                    safe(scr, row, sx + 2 + pad, txt, dyn | curses.A_REVERSE | curses.A_BOLD, cw - pad)
                    row += 1
                else:
                    line(E.current_lyrics[i], WB if E.is_synced_lyrics and i == act_idx + 1 else (DIM if E.is_synced_lyrics and i < act_idx else NORMAL))
            else:
                line("", NORMAL)
    else:
        line(E.t('visual_title'), dyn)
        vh = view - 1
        lv = E.get_levels(cw)                                # real levels of the song that is playing (None = simulate)
        for yv in range(vh):
            s = ""
            for b in range(cw):
                v = 0.0
                if lv:
                    v = min(1.0, lv[b] * 1.5) if E.x3_vis else lv[b]
                elif E.is_playing and not E.is_paused:
                    v = min(1.0, (math.sin(tick * .3 + b * .2) + math.cos(tick * .15 - b * .4) + 2) / 4 + random.random() * .3 * (math.sin(tick * .6) + 1)
                            + (math.sin(tick * .4) * .3 if b % 4 == 0 else 0.0))
                    v = min(1.0, v * 1.5) if E.x3_vis else v
                th = 1.0 - yv / vh
                if v >= th:
                    s += "█"
                elif v >= th - 1 / (vh * 2):
                    s += "▓"
                elif E.is_playing and (b + yv + tick) % 17 == 0:
                    s += "✧"
                elif E.is_playing and (b * yv - tick) % 29 == 0:
                    s += "·"
                else:
                    s += " "
            line(s, dyn)

    if floating:
        sep()
        txt = " 🎤 %s " % act_text
        if len(txt) > cw:
            p = (tick // 3) % len(act_text)
            txt = " 🎤 %s " % (act_text + " • " + act_text)[p:p + cw - 6]
        edges()
        safe(scr, row, sx + 2, txt.center(cw)[:cw], dyn | curses.A_REVERSE | curses.A_BOLD, cw)
        row += 1
    sep()
    flags = "%s%s%s%s%s%s" % ("[PAUSE]" if E.is_paused else "", "[AUTO-DJ]" if E.auto_dj else "", "[AURA]" if E.aura_mode else "",
                              "[X3]" if E.x3_vis else "", "[ANIM OFF]" if not E.anim_enabled else "", "[SCAN]" if E.scanning else "")
    if SL.active():
        flags += "[SLEEP %s]" % SL.fmt_left(SL.remaining())
    if FX.is_active():
        flags += "[FX %s]" % FX.label()
    if Q.upnext:
        flags += "[Q%d]" % len(Q.upnext)
    if E.ab_a is not None:
        flags += "[A-B]" if E.ab_b is not None else "[A-]"
    now = time.time()
    if E.engine_status_msg and now - E.engine_status_time < 4.0:
        line("⚠ " + E.engine_status_msg, ALERT)
    elif E.info_msg and now - E.info_time < 2.0:
        line(E.info_msg, INFO_C)
    else:
        title = E.title_of(E.playing_song_name) or E.t('no_music')
        line("[%s] %s [%s] %s" % (E.engine_name().upper(), title[:max(1, cw - 30)], E.get_mode_string(), flags), WB)
    line("%s  %s  %s" % (E.current_time_str, progressbar(E.progress_pct, cw - 16, tick), E.total_time_str), LOGO_C)
    sep()
    for k in ((1, 2, 3, 4, 5) if ctrl_rows == 5 else (1, 2, 3, 4) if ctrl_rows == 4 else (1, 2, 3) if ctrl_rows == 3 else (2,)):
        line(E.t('ctrl_%d' % k), NORMAL)
    safe(scr, row, sx, "╚" + "═" * (box_w - 2) + "╝", BORDER, box_w)




def _main(scr, paths, yt):
    global tick, current_anim_idx, last_anim_time
    E.load_favorites()
    E.load_settings()
    ST.load()                                         # listening statistics (shared with the GUI)
    E.refresh_playlist()
    if paths:
        E.add_external(paths)
        E.play_song(paths[0])
        E.selected_idx = E.songs.index(paths[0]) if paths[0] in E.songs else 0
    E.scan_library_async()
    CT.start(E, notify=E.notify_controls)
    AL.start(E.alarm_fire)
    if yt:
        threading.Thread(target=E.download_and_play_yt, args=(yt,), daemon=True).start()
    try:
        curses.curs_set(0)
    except Exception:
        pass
    scr.keypad(True)
    scr.timeout(80)
    curses.start_color()
    try:
        curses.use_default_colors()
    except Exception:
        pass

    def pair(n, fg):
        try:
            curses.init_pair(n, fg, -1)
        except Exception:
            pass
    for i, c in enumerate([curses.COLOR_CYAN, curses.COLOR_WHITE, curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_MAGENTA]):
        pair(i + 1, c)
    for i, c in enumerate([curses.COLOR_RED, curses.COLOR_BLUE, curses.COLOR_CYAN, curses.COLOR_GREEN, curses.COLOR_MAGENTA, curses.COLOR_YELLOW]):
        pair(i + 10, c)
        pair(i + 20, c)

    buf, buf_t = "", 0.0
    last_anim_time = time.time()
    try:
        while not E.exit_flag:
            draw_ui(scr)
            scr.refresh()
            tick += 1
            if buf and time.time() - buf_t > 0.8:
                buf = ""
            try:
                ch = scr.getch()
            except Exception:
                continue
            if ch == -1:
                continue
            if ch == curses.KEY_RESIZE:
                scr.clear()
                continue
            if E.is_searching:
                if ch in (27, 10, 13, curses.KEY_ENTER):
                    E.is_searching = False
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    E.search_query = E.search_query[:-1]
                    E.update_search()
                elif 32 <= ch <= 126:
                    E.search_query += chr(ch)
                    E.update_search()
                continue
            n = len(E.songs)
            if ch == curses.KEY_UP:
                if E.ui_mode == 'playlist' and E.selected_idx > 0:
                    E.selected_idx -= 1
                elif E.ui_mode == 'lyrics' and E.lyrics_scroll > 0:
                    E.lyrics_scroll -= 1
                    E.last_scroll_time = time.time()
                continue
            if ch == curses.KEY_DOWN:
                if E.ui_mode == 'playlist' and E.selected_idx < n - 1:
                    E.selected_idx += 1
                elif E.ui_mode == 'lyrics' and E.lyrics_scroll < max(0, len(E.current_lyrics) - 1):
                    E.lyrics_scroll += 1
                    E.last_scroll_time = time.time()
                continue
            if ch == curses.KEY_PPAGE:
                E.selected_idx = max(0, E.selected_idx - 8)
                continue
            if ch == curses.KEY_NPAGE:
                E.selected_idx = min(max(0, n - 1), E.selected_idx + 8)
                continue
            if ch == curses.KEY_LEFT:
                E.seek(E.get_position() - 10)
                continue
            if ch == curses.KEY_RIGHT:
                E.seek(E.get_position() + 10)
                continue
            if ch in (10, 13, curses.KEY_ENTER):
                if E.ui_mode == 'playlist' and E.songs:
                    E.play_song(E.songs[E.selected_idx])
                buf = ""
                continue
            if ch == 32:
                E.toggle_play()
                continue
            if 32 <= ch <= 126:
                buf += chr(ch)
                buf_t = time.time()
                low = buf.lower()
                if low == "7xz" and E.AVAILABLE_ENGINES:
                    E.ACTIVE_ENGINE_IDX = (E.ACTIVE_ENGINE_IDX + 1) % len(E.AVAILABLE_ENGINES)
                    buf = ""
                    continue
                if low in ("4a", "x3", "1b", "2e"):
                    if low == "4a":
                        E.aura_mode = not E.aura_mode
                    elif low == "x3":
                        E.x3_vis = not E.x3_vis
                    elif low == "1b":
                        current_anim_idx, last_anim_time = (current_anim_idx + 1) % TOTAL_ANIMATIONS, time.time()
                    else:
                        E.anim_enabled = not E.anim_enabled
                    E.save_settings()
                    buf = ""
                    continue
                if len(buf) != 1:
                    continue
                c = low
                if c == 'q':
                    break
                elif c == 'w' and E.ui_mode == 'playlist' and E.songs:
                    E.play_song(E.songs[E.selected_idx])
                elif c == 'f':
                    E.toggle_play()
                elif c in ('v', '/'):
                    E.is_searching, E.search_query = True, ""
                    E.update_search()
                elif c == 'p' and E.playing_song_name:
                    E.step(-1)
                elif c == 'n' and E.playing_song_name:
                    E.step(1)
                elif c == 'm':
                    E.play_mode = (E.play_mode + 1) % 5
                    E.save_settings()
                elif c == 'r':
                    E.deep_reset()
                    E.update_search()
                elif c == 'l' and E.ui_mode == 'playlist' and E.songs:
                    E.toggle_favorite(E.songs[E.selected_idx])
                elif c == 'z':
                    E.ui_mode = 'playlist' if E.ui_mode == 'lyrics' else 'lyrics'
                    E.last_scroll_time = 0.0
                elif c == 'c':
                    E.ui_mode = 'playlist' if E.ui_mode == 'visualizer' else 'visualizer'
                elif c == 'x':
                    i = E.SUPPORTED_LANGS.index(E.current_lang) if E.current_lang in E.SUPPORTED_LANGS else 0
                    E.current_lang = E.SUPPORTED_LANGS[(i + 1) % len(E.SUPPORTED_LANGS)]
                    E.save_settings()
                elif c == 'a':
                    E.auto_dj = not E.auto_dj
                    E.save_settings()
                elif c in ('+', '='):
                    E.change_volume(5)
                elif c == '-':
                    E.change_volume(-5)
                elif c == 's':
                    E.scan_library_async()
                elif c == 'e':                               # effects: normal -> bass -> vocal -> treble -> lofi -> slowed -> nightcore
                    E.fx_apply(preset=FX.PRESETS[(FX.PRESETS.index(FX.preset) + 1) % len(FX.PRESETS)])
                elif c == 'u' and E.ui_mode == 'playlist' and E.songs:
                    E.queue_add([E.songs[E.selected_idx]])      # add the selected song to Up next
                elif c == 'b':
                    E.ab_mark()                              # A-B repeat: set A, set B, clear
                elif c == 't':                               # sleep timer: off -> 15 -> 30 -> 45 -> 60 -> 120 minutes -> off
                    m = SL.cycle_preset()
                    E.info((E.t('sleep_on') % ("%d min" % m)) if m else E.t('sleep_off'))
                elif c == 'y':
                    curses.endwin()
                    print("\n=== DOWNLOAD AUDIO (yt-dlp) ===")
                    try:
                        url = input("URL: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        url = ""
                    if url:
                        threading.Thread(target=E.download_and_play_yt, args=(url,), daemon=True).start()
                    scr.clear()
                    scr.refresh()
                    try:
                        curses.curs_set(0)
                    except Exception:
                        pass
                    scr.keypad(True)
    finally:
        AL.stop()
        CT.stop_server()
        E.shutdown()


def run(paths=None, yt=None):
    if not E.AVAILABLE_ENGINES:
        print("WARNING: no audio player found. Install one:  pkg install mpv   (Termux)  |  apt install mpv  |  pip install pygame")
        print("The playlist and lyrics still work, but nothing will play.  (rofpalys doctor)")
        time.sleep(2)
    try:
        curses.wrapper(_main, list(paths or []), yt)
    except KeyboardInterrupt:
        E.shutdown()
    except Exception as e:
        E.shutdown()
        print("\nUnexpected error: %s\nThe program has stopped safely." % e)
        sys.exit(1)


if __name__ == "__main__":
    run(lib.resolve_inputs(sys.argv[1:])[0])

# END-OF-FILE rofpalys_tui.py

