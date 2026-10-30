#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: Find lyrics window + CyroKayAI (exact lyric sync)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Search LRCLIB / YouTube captions / other sources, pick the right lyrics, or load a file - and let CyroKayAI (rofpalys_CyroKayAI_lyric.py) do the
exact part: find out who made the song, check the internet, listen to the recording and fit every lyric line to the real voice.
Whatever you pick or load is fitted to the recording first. Lyrics that were saved before CyroKayAI existed are fitted once, in the background.
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
from rofpalys_gui_base import *   # noqa: F401,F403

try:
    import rofpalys_CyroKayAI_lyric as CK
except Exception:                                   # the window still works without the brain: it only loses the exact sync
    CK = None

FEATURE = {"name": "lyrics", "title": "Find lyrics window + CyroKayAI sync", "version": "2.1", "order": 10, "enabled": True}
_OLD_SOURCES = ("LRCLIB", "YouTube", "ovh", "cache")        # lyrics saved by older versions: fitted once, in the background


class Mixin:
    # ------------------------------------------------------------------ the window
    def open_lyrics_dialog(self):
        if self.lyr_win is not None:
            try:
                self.lyr_win.lift()
                return
            except Exception:
                self.lyr_win = None
        T = self.T
        top = self.popup(T("lyr_find"), 640, 720)
        self.lyr_win = top
        top.protocol("WM_DELETE_WINDOW", self.close_lyrics_dialog)
        self.btn(top, T("close"), self.close_lyrics_dialog, bg=BRN, fg=BLK).pack(side="bottom", anchor="e", padx=18, pady=12)
        t = M.current()
        a, ti = (t.artist, t.title) if t else LY.guess(E.playing_song_name or "")
        tk.Label(top, text=T("lyr_find"), bg=PNL, fg=TXT, font=self.f_big, anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        self.lbl_ly_src = tk.Label(top, text="", bg=PNL, fg=GOLD, font=self.f_small, anchor="w")
        self.lbl_ly_src.pack(fill="x", padx=18)
        self.ck_panel(top)
        for label, attr, val in ((T("lyr_artist"), "ly_artist", a), (T("lyr_title"), "ly_title", ti)):
            row = tk.Frame(top, bg=PNL)
            row.pack(fill="x", padx=18, pady=(6, 0))
            tk.Label(row, text=label, bg=PNL, fg=DIM, font=self.f_small, width=8, anchor="w").pack(side="left")
            var = tk.StringVar(value=val or "")
            setattr(self, attr, var)
            tk.Entry(row, textvariable=var, bg=PNL2, fg=TXT, insertbackground=GOLD, bd=0, highlightthickness=1, highlightbackground=PNL2,
                     highlightcolor=BRN2, font=self.f_ui, relief="flat").pack(side="left", fill="x", expand=True, ipady=6)
        row = tk.Frame(top, bg=PNL)
        row.pack(fill="x", padx=18, pady=8)
        self.btn(row, T("lyr_search"), lambda: self.ly_search(False), bg=GOLD, fg=BLK).pack(side="left")
        self.btn(row, T("lyr_yt"), lambda: self.ly_search(True)).pack(side="left", padx=6)
        lf = tk.Frame(top, bg=PNL)
        lf.pack(fill="both", expand=True, padx=18)
        sb = tk.Scrollbar(lf, bg=PNL2, troughcolor=PNL, bd=0, highlightthickness=0, width=10)
        self.ly_lb = tk.Listbox(lf, height=6, bg=PNL2, fg=TXT, selectbackground=BRN, selectforeground=BLK, bd=0, highlightthickness=0, activestyle="none",
                                font=self.f_ui, exportselection=False, yscrollcommand=sb.set)
        sb.config(command=self.ly_lb.yview)
        sb.pack(side="right", fill="y")
        self.ly_lb.pack(side="left", fill="both", expand=True)
        self.ly_lb.bind("<Double-Button-1>", lambda e: self.ly_use())
        self._ly_cands = []
        row2 = tk.Frame(top, bg=PNL)
        row2.pack(fill="x", padx=18, pady=8)
        self.btn(row2, T("lyr_use"), self.ly_use, bg=GOLD, fg=BLK).pack(side="left")
        self.btn(row2, T("lyr_file"), self.ly_file).pack(side="left", padx=6)
        self.btn(top, T("lyr_del"), self.ly_delete, fg=RED).pack(anchor="w", padx=18)
        self.lbl_ly_status = tk.Label(top, text="", bg=PNL, fg=DIM, font=self.f_small, anchor="w")
        self.lbl_ly_status.pack(fill="x", padx=18, pady=(6, 0))
        self.ly_src_refresh()
        self.ck_refresh()

    def close_lyrics_dialog(self):
        try:
            if self.lyr_win is not None:
                self.lyr_win.destroy()
        except Exception:
            pass
        self.lyr_win = None

    def ck_panel(self, top):
        """The CyroKayAI block: what it found out about the song that plays now, and the two buttons."""
        T = self.T
        box = tk.Frame(top, bg=PNL2)
        box.pack(fill="x", padx=18, pady=(8, 2))
        tk.Label(box, text=T("ck_title"), bg=PNL2, fg=GOLD, font=self.f_ui_b, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        self.lbl_ck = tk.Label(box, text="", bg=PNL2, fg=TXT, font=self.f_small, anchor="w", justify="left", wraplength=560)
        self.lbl_ck.pack(fill="x", padx=10)
        row = tk.Frame(box, bg=PNL2)
        row.pack(fill="x", padx=10, pady=8)
        self.btn(row, T("ck_auto"), lambda: self.ck_start(False), bg=GOLD, fg=BLK).pack(side="left")
        self.btn(row, "%s  %s/%s" % (T("ck_melody"), LY.NOTE_HI, LY.NOTE_LO), lambda: self.ck_start(True)).pack(side="left", padx=6)
        if CK is not None:
            self.var_skip = tk.BooleanVar(value=bool(CK.SKIP["on"]))
            tk.Checkbutton(box, text=T("ck_skip"), variable=self.var_skip, command=lambda: CK.SKIP.update(on=bool(self.var_skip.get())), bg=PNL2, fg=DIM,
                           selectcolor=PNL, activebackground=PNL2, activeforeground=GOLD, bd=0, highlightthickness=0, font=self.f_small, anchor="w",
                           wraplength=560, justify="left").pack(fill="x", padx=8, pady=(0, 8))

    def _lang(self):
        return "id" if self.T("home") == "Beranda" else "en"

    def ck_refresh(self):
        """Show the last CyroKayAI result for the song that plays now (or what it is doing)."""
        try:
            if self.lyr_win is None:
                return
            if CK is None:
                self.lbl_ck.configure(text=self.T("ck_missing"), fg=RED)
            elif self._ck_busy:
                self.lbl_ck.configure(text=self.T("ck_st_" + (self._ck_stage or "creator")), fg=GOLD)
            else:
                R = CK.last(E.playing_song_name or "")
                self.lbl_ck.configure(text=CK.describe(R, self._lang()) if R else self.T("ck_none"), fg=TXT if R else DIM)
        except Exception:
            pass

    def ly_src_refresh(self):
        try:
            self.lbl_ly_src.configure(text="%s:  %s" % (self.T("lyr_src"), E.lyrics_source or "-"))
        except Exception:
            pass

    def ly_cand_text(self, c):
        d = ("  ·  %d:%02d" % (int(c["duration"]) // 60, int(c["duration"]) % 60)) if c.get("duration") else ""
        return "%s - %s    [%s · %s%s]" % (c.get("artist", ""), c.get("title", ""), c["source"], "synced" if c.get("synced") else "text", d)

    # ------------------------------------------------------------------ CyroKayAI: the whole job (creator -> internet -> listen -> fetch -> fit)
    def ck_start(self, melody=False, quiet=False):
        if CK is None:
            if not quiet:
                self.ck_refresh()
            return
        if not E.playing_song_name:
            if not quiet and self.lyr_win is not None:
                self.lbl_ck.configure(text=self.T("ck_nosong"), fg=RED)
            return
        if self._ck_busy:
            return
        self._ck_busy, self._ck_stage = True, "creator"
        path = E.playing_song_name

        def work():
            try:
                R = CK.sync_playing(E, melody=melody, progress=lambda st: setattr(self, "_ck_stage", st), apply=False)
            except Exception as e:
                log("cyrokay: %r" % (e,))
                R = None
            self._ck_result = (path, R)
        threading.Thread(target=work, daemon=True).start()
        self.ck_refresh()

    def _fit_async(self, raw, source):
        """Lyrics the user picked or loaded: fit them to the recording (a worker thread), the poll loop then hands them to the player."""
        path = E.playing_song_name or ""
        if CK is None or not path:
            E.use_lyrics(raw, source)
            self.ly_src_refresh()
            return
        self.lbl_ly_status.configure(text=self.T("ck_working"), fg=GOLD)

        def work():
            try:
                fitted, conf = LY.fit_to_song(raw, path)
            except Exception as e:
                log("fit_to_song: %r" % (e,))
                fitted, conf = raw, None
            self._ly_apply = (path, fitted, source, conf)
        threading.Thread(target=work, daemon=True).start()

    def lyr_poll(self):
        """Called from the poll loop (main thread): show search results, hand finished work to the player, upgrade old saved lyrics once per song."""
        if CK is not None:
            CK.maybe_skip(E)
            if self._ck_busy:
                self.ck_refresh()
        res, self._ck_result = self._ck_result, None
        if res is not None:
            path, R = res
            self._ck_busy = False
            if R and R.get("raw") and not R.get("stopped") and E.playing_song_name == path:
                E.use_lyrics(R["raw"], R["source"])
            self.ly_src_refresh()
            self.ck_refresh()
        ap, self._ly_apply = self._ly_apply, None
        if ap is not None:
            path, raw, source, conf = ap
            if E.playing_song_name == path:
                E.use_lyrics(raw, ((CK.BRAND if CK is not None else "CyroKayAI") + " · " + source) if (conf is not None and "CyroKayAI" not in source) else source)
            try:
                if self.lyr_win is not None:
                    self.lbl_ly_status.configure(text=self.T("done") + ((" - %s %d%%" % (self.T("ck_fitted"), round(conf * 100))) if conf is not None else ""), fg=GOLD)
            except Exception:
                pass
            self.ly_src_refresh()
        cur = E.playing_song_name or ""
        if cur != self._ck_seen:                                    # a new song: if its lyrics are an older download, fit them once in the background
            self._ck_seen, self._ck_seen_t = cur, time.time()
        elif (CK is not None and cur and cur not in self._ck_tried and not self._ck_busy and time.time() - self._ck_seen_t > 3.0
              and E.lyrics_source and not LY.is_current(E.lyrics_source) and "melody" not in E.lyrics_source and any(k in E.lyrics_source for k in _OLD_SOURCES)):
            self._ck_tried.add(cur)
            self.ck_start(False, quiet=True)
        cands = self._lyr_pending
        if cands is None or self.lyr_win is None:
            return
        self._lyr_pending = None
        self._ly_cands = cands
        self.ly_lb.delete(0, "end")
        for c in cands:
            self.ly_lb.insert("end", self.ly_cand_text(c))
        if cands:
            self.ly_lb.selection_set(0)
        self.lbl_ly_status.configure(text="%d %s" % (len(cands), self.T("lyr_found")) if cands else self.T("lyr_none_found"), fg=DIM if cands else RED)

    # ------------------------------------------------------------------ manual search
    def ly_search(self, youtube=False):
        a, ti = self.ly_artist.get().strip(), self.ly_title.get().strip()
        if not ti:
            return
        self.lbl_ly_status.configure(text=self.T("loading"), fg=GOLD)
        dur = E.total_time_seconds if E.duration_known else -1.0
        langs = (E.current_lang,)

        def work():
            try:
                cands = LY.search_candidates(a, ti, dur, youtube=youtube, langs=langs)
            except Exception as e:
                log("lyrics search: %r" % (e,))
                cands = []
            self._lyr_pending = cands
        threading.Thread(target=work, daemon=True).start()

    def ly_use(self):
        sel = self.ly_lb.curselection()
        if sel and sel[0] < len(self._ly_cands):
            c = self._ly_cands[sel[0]]
            self._fit_async(c["raw"], c["source"])

    def ly_delete(self):
        E.reset_lyrics()
        self.lbl_ly_status.configure(text=self.T("loading"), fg=GOLD)
        self.ly_src_refresh()

    def ly_file(self):
        path = filedialog.askopenfilename(parent=self.lyr_win or self.root, initialdir=HOME, filetypes=[("Lyrics", "*.lrc *.txt"), ("All", "*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                self._fit_async(f.read(), "file")
        except OSError as e:
            self.lbl_ly_status.configure(text=str(e), fg=RED)


def build_lyrics_button(app, bar):
    app.b_lyrfind = IconBtn(bar, "lyrics", app.open_lyrics_dialog, size=20, bg=PNL, pad=7)
    app.b_lyrfind.pack(side="right")
    return [app.b_lyrfind.cv]


def register(app):
    app.lyr_win, app._lyr_pending, app._ly_cands = None, None, []
    app._ck_busy, app._ck_stage, app._ck_result, app._ly_apply = False, "", None, None
    app._ck_seen, app._ck_seen_t, app._ck_tried = "", 0.0, set()
    if not emoji_ok():                                              # a Tk that cannot draw emoji safely shows the markers as text notes instead
        LY.set_note_style("text")
    app.add_toolbar(10, build_lyrics_button)
    app.add_poll(lambda a: a.lyr_poll())


# END-OF-FILE rofpalys_gui_lyrics.py

