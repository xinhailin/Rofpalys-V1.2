#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: Sleep timer + wake-up alarm
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Moon button in Now Playing: timer by duration or until a clock time (any time zone), fade-out, and alarms.
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
from rofpalys_gui_base import *   # noqa: F401,F403

FEATURE = {"name": "sleep", "title": "Sleep timer + wake-up alarm", "version": "1.0", "order": 40, "enabled": True}


class Mixin:
    def open_sleep(self):
        if self.sleep_win is not None:
            try:
                self.sleep_win.lift()
                return
            except Exception:
                self.sleep_win = None
        T = self.T
        top = self.popup(T("sleep"), 560, 660)
        self.sleep_win = top
        top.protocol("WM_DELETE_WINDOW", self.close_sleep)
        self.btn(top, T("close"), self.close_sleep, bg=BRN, fg=BLK).pack(side="bottom", anchor="e", padx=18, pady=12)
        body = self.scrollable(top)
        tk.Label(body, text=T("sleep"), bg=PNL, fg=TXT, font=self.f_big, anchor="w").pack(fill="x", padx=18, pady=(14, 4))
        self.lbl_sl_state = tk.Label(body, text="", bg=PNL, fg=GOLD, font=self.f_ui, anchor="w", justify="left", wraplength=500)
        self.lbl_sl_state.pack(fill="x", padx=18)
        self.btn(body, T("sleep_stop"), self.sleep_stop, fg=RED).pack(anchor="w", padx=18, pady=(4, 8))
        tk.Label(body, text=T("sleep_dur"), bg=PNL, fg=TXT, font=self.f_title, anchor="w", wraplength=500, justify="left").pack(fill="x", padx=18, pady=(8, 2))
        row = tk.Frame(body, bg=PNL)
        row.pack(fill="x", padx=18)
        for mins, label in ((15, "15m"), (30, "30m"), (45, "45m"), (60, "1h"), (120, "2h"), (180, "3h"), (240, "4h")):
            self.btn(row, label, lambda m=mins: self.sleep_set(m * 60)).pack(side="left", padx=(0, 4), pady=2)
        row2 = tk.Frame(body, bg=PNL)
        row2.pack(fill="x", padx=18, pady=(6, 0))
        self.sl_dur = tk.StringVar(value="02.00")
        tk.Entry(row2, textvariable=self.sl_dur, width=9, bg=PNL2, fg=TXT, insertbackground=GOLD, bd=0, highlightthickness=1, highlightbackground=PNL2,
                 highlightcolor=BRN2, font=self.f_ui, relief="flat").pack(side="left", ipady=6)
        self.btn(row2, T("sleep_start"), self.sleep_custom, bg=GOLD, fg=BLK).pack(side="left", padx=8)
        tk.Label(body, text=T("sleep_hint"), bg=PNL, fg=DIM, font=self.f_small, anchor="w").pack(fill="x", padx=18, pady=(2, 8))
        tk.Label(body, text=T("sleep_until"), bg=PNL, fg=TXT, font=self.f_title, anchor="w").pack(fill="x", padx=18, pady=(10, 2))
        tk.Label(body, text=T("sleep_zone"), bg=PNL, fg=DIM, font=self.f_small, anchor="w").pack(fill="x", padx=18)
        zf = tk.Frame(body, bg=PNL)
        zf.pack(fill="x", padx=18)
        zsb = tk.Scrollbar(zf, bg=PNL2, troughcolor=PNL, bd=0, highlightthickness=0, width=10)
        self.sl_lb = tk.Listbox(zf, height=6, bg=PNL2, fg=TXT, selectbackground=BRN, selectforeground=BLK, bd=0, highlightthickness=0, activestyle="none",
                                font=self.f_ui, exportselection=False, yscrollcommand=zsb.set)
        zsb.config(command=self.sl_lb.yview)
        zsb.pack(side="right", fill="y")
        self.sl_lb.pack(side="left", fill="x", expand=True)
        keys = [z[0] for z in SL.ZONES]
        for k in keys:
            self.sl_lb.insert("end", SL.zone_label(k))
        cur = keys.index(E.sleep_zone) if E.sleep_zone in keys else 0
        self.sl_lb.selection_set(cur)
        self.sl_lb.see(cur)
        self.sl_lb.bind("<<ListboxSelect>>", lambda e: self.sleep_preview())
        row3 = tk.Frame(body, bg=PNL)
        row3.pack(fill="x", padx=18, pady=(8, 0))
        tk.Label(row3, text=T("clock_hint"), bg=PNL, fg=DIM, font=self.f_small).pack(side="left", padx=(0, 8))
        self.sl_clock = tk.StringVar(value="00:00")
        ce = tk.Entry(row3, textvariable=self.sl_clock, width=8, bg=PNL2, fg=TXT, insertbackground=GOLD, bd=0, highlightthickness=1, highlightbackground=PNL2,
                      highlightcolor=BRN2, font=self.f_ui, relief="flat")
        ce.pack(side="left", ipady=6)
        ce.bind("<KeyRelease>", lambda e: self.sleep_preview())
        self.btn(row3, T("sleep_start"), self.sleep_until, bg=GOLD, fg=BLK).pack(side="left", padx=8)
        self.lbl_sl_prev = tk.Label(body, text="", bg=PNL, fg=DIM, font=self.f_small, anchor="w", justify="left", wraplength=500)
        self.lbl_sl_prev.pack(fill="x", padx=18, pady=(6, 4))
        self.seg(body, T("sleep_finish"), [(False, T("sleep_cut")), (True, T("sleep_end"))], lambda: E.sleep_finish,
                 lambda v: E.sleep_set_finish(v == "True"))
        self.seg(body, T("fade"), [(True, T("on")), (False, T("off"))], lambda: E.sleep_fade, lambda v: (setattr(E, "sleep_fade", v == "True"), E.save_settings()))
        self.build_alarm_section(body)
        self.sleep_state_refresh()
        self.sleep_preview()

    def close_sleep(self):
        try:
            if self.sleep_win is not None:
                self.sleep_win.destroy()
        except Exception:
            pass
        self.sleep_win = None

    def sleep_state_refresh(self):
        T = self.T
        if SL.active():
            self.lbl_sl_state.configure(text="%s:  %s   (%s %s)" % (T("sleep_active"), SL.text, T("sleep_in"), SL.fmt_left(SL.remaining())), fg=GOLD)
        else:
            self.lbl_sl_state.configure(text=T("sleep_inactive"), fg=DIM)

    def sleep_zone_key(self):
        sel = self.sl_lb.curselection()
        return SL.ZONES[sel[0]][0] if sel else E.sleep_zone

    def sleep_preview(self):
        """Live line under the clock box: what time it is there now, when it will stop, how long that is."""
        T = self.T
        try:
            key = self.sleep_zone_key()
            self.sleep_state_refresh()
            try:
                hh, mm = SL.parse_clock(self.sl_clock.get())
            except ValueError:
                self.lbl_sl_prev.configure(text=T("sleep_bad"), fg=RED)
                return
            now = time.time()
            end = SL.next_occurrence(key, hh, mm, now)
            short = SL.zone(key)[2]
            left = int(end - now)
            self.lbl_sl_prev.configure(text="%s %s %s   →   %s %02d:%02d %s   (%s %dh %02dm)" % (T("sleep_now"), SL.wall_clock(key, now).strftime("%H:%M"), short,
                                                                                            T("sleep_ends"), hh, mm, short, T("sleep_in"), left // 3600, left // 60 % 60), fg=DIM)
        except Exception as e:
            log("sleep_preview: %r" % (e,))

    def sleep_set(self, seconds):
        E.sleep_start_duration(seconds)
        self.close_sleep()

    def sleep_custom(self):
        try:
            self.sleep_set(SL.parse_duration(self.sl_dur.get()))
        except ValueError:
            self.lbl_sl_prev.configure(text=self.T("sleep_bad"), fg=RED)

    def sleep_until(self):
        try:
            hh, mm = SL.parse_clock(self.sl_clock.get())
        except ValueError:
            self.lbl_sl_prev.configure(text=self.T("sleep_bad"), fg=RED)
            return
        E.sleep_start_until(hh, mm, self.sleep_zone_key())
        self.close_sleep()

    def sleep_stop(self):
        E.sleep_cancel()
        self.sleep_state_refresh()

    def build_alarm_section(self, body):
        T = self.T
        tk.Label(body, text=T("alarm"), bg=PNL, fg=TXT, font=self.f_title, anchor="w").pack(fill="x", padx=18, pady=(18, 2))
        row = tk.Frame(body, bg=PNL)
        row.pack(fill="x", padx=18, pady=(4, 0))
        tk.Label(row, text=T("alarm_time"), bg=PNL, fg=DIM, font=self.f_small).pack(side="left", padx=(0, 8))
        self.al_clock = tk.StringVar(value="06:30")
        tk.Entry(row, textvariable=self.al_clock, width=8, bg=PNL2, fg=TXT, insertbackground=GOLD, bd=0, highlightthickness=1, highlightbackground=PNL2,
                 highlightcolor=BRN2, font=self.f_ui, relief="flat").pack(side="left", ipady=6)
        self.seg(body, T("alarm_play"), [("song", T("alarm_song")), ("playlist", T("alarm_pl"))], lambda: self._al_target, lambda v: setattr(self, "_al_target", v))
        pls = PL.all_playlists()
        self._al_pls = [p["id"] for p in pls]
        self.al_lb = tk.Listbox(body, height=3, bg=PNL2, fg=TXT, selectbackground=BRN, selectforeground=BLK, bd=0, highlightthickness=0, activestyle="none",
                                font=self.f_ui, exportselection=False)
        for p in pls:
            self.al_lb.insert("end", p["name"])
        self.al_lb.pack(fill="x", padx=18, pady=(6, 0))
        self.seg(body, T("alarm_rep"), [("once", T("alarm_once")), ("daily", T("alarm_daily")), ("week", T("alarm_week"))], lambda: self._al_rep, lambda v: setattr(self, "_al_rep", v))
        self.btn(body, T("alarm_set"), self.alarm_set, bg=GOLD, fg=BLK).pack(anchor="w", padx=18, pady=8)
        self.al_list = tk.Frame(body, bg=PNL)
        self.al_list.pack(fill="x", padx=18)
        tk.Label(body, text=T("alarm_hint"), bg=PNL, fg=DIM, font=self.f_small, anchor="w", justify="left", wraplength=500).pack(fill="x", padx=18, pady=(6, 10))
        self.alarm_refresh()

    def alarm_refresh(self):
        for w in self.al_list.winfo_children():
            w.destroy()
        items = AL.all_alarms()
        if not items:
            tk.Label(self.al_list, text=self.T("alarm_none"), bg=PNL, fg=DIM, font=self.f_small, anchor="w").pack(fill="x")
        for a in items:
            r = tk.Frame(self.al_list, bg=PNL)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=AL.describe(a), bg=PNL, fg=TXT, font=self.f_small, anchor="w").pack(side="left")
            self.btn(r, "x", lambda aid=a["id"]: self.alarm_remove(aid), fg=RED, padx=8, pady=1).pack(side="right")

    def alarm_set(self):
        try:
            hh, mm = SL.parse_clock(self.al_clock.get())
        except ValueError:
            self.lbl_sl_prev.configure(text=self.T("sleep_bad"), fg=RED)
            return
        if self._al_target == "playlist":
            sel = self.al_lb.curselection()
            if not sel or sel[0] >= len(self._al_pls):
                self.lbl_sl_prev.configure(text=self.T("alarm_need_song"), fg=RED)
                return
            target = {"type": "playlist", "ref": self._al_pls[sel[0]]}
        else:
            if not E.playing_song_name:
                self.lbl_sl_prev.configure(text=self.T("alarm_need_song"), fg=RED)
                return
            target = {"type": "song", "ref": E.playing_song_name}
        days = {"once": (), "daily": range(7), "week": range(5)}[self._al_rep]
        AL.add(hh, mm, self.sleep_zone_key(), target, days)
        self.alarm_refresh()

    def alarm_remove(self, aid):
        AL.remove(aid)
        self.alarm_refresh()


def build_sleep(app, bar):
    app.lbl_sleep = tk.Label(bar, text="", bg=PNL, fg=GOLD, font=app.f_small, cursor="hand2")
    app.lbl_sleep.pack(side="right")
    app.lbl_sleep.bind("<Button-1>", lambda e: app.open_sleep())
    app.b_sleep = IconBtn(bar, "moon", app.open_sleep, size=20, bg=PNL, pad=7)
    app.b_sleep.pack(side="right")
    return [app.lbl_sleep, app.b_sleep.cv]


def poll(app):
    app.lbl_sleep.configure(text=(SL.fmt_left(SL.remaining()) + ("  " + SL.text if SL.kind == "until" else "")) if SL.active() else "")
    if app.sleep_win is not None:
        app.sleep_preview()


def register(app):
    app.sleep_win = None
    app._al_target, app._al_rep, app._al_pls = "song", "once", []
    app.add_toolbar(40, build_sleep)
    app.add_poll(poll)


# END-OF-FILE rofpalys_gui_sleep.py

