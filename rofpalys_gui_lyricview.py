#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: live lyrics that glide with the song (Spotify style) - CyroKayAI clock + view
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Two ways to see the smooth lyrics, both made by the same view (rofpalys_CyroKayAI_view.py):
  1. the button with the music note in the toolbar opens a window "Live lyrics";
  2. IN PLACE: the view is laid over the lyric area of Now Playing (Cover + lyrics). This file does not know how rofpalys_gui.py draws its lyrics, so it
     FINDS that area: the visible Text / Canvas / Label whose text contains lines of the current lyrics. If it finds nothing, or the lyrics have no
     timing, nothing is laid over and the old display stays as it was. Switch it off in the window (checkbox) or with:  rofpalys lyrics view off
What it shows is what is in the lyric cache of the song (CyroKayAI fitted lyrics, or your own .lrc next to the song). A feature file plugs into the
window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
import re

from rofpalys_gui_base import *   # noqa: F401,F403

try:
    import rofpalys_CyroKayAI_view as VW
    import rofpalys_CyroKayAI_clock as CL
except Exception:                                   # the brain's screen files are missing: this feature switches itself off
    VW = CL = None
try:
    import rofpalys_CyroKayAI_lyric as CK
except Exception:
    CK = None
try:
    import rofpalys_CyroKayAI_memory as MEM
except Exception:
    MEM = None
try:
    import rofpalys_CyroKayAI_ears as EA
except Exception:
    EA = None

FEATURE = {"name": "lyricview", "title": "Live lyrics: Spotify-style scrolling (CyroKayAI)", "version": "1.0", "order": 11, "enabled": True}


def _norm(s):
    return re.sub(r"[^\w]+", " ", (s or "").lower(), flags=re.U).strip()


def _widget_text(w):
    """The text a Text / Canvas / Label shows (capped): used only to recognise the lyric area."""
    try:
        cls = w.winfo_class()
        if cls == "Text":
            return _norm(w.get("1.0", "end")[:20000])
        if cls == "Canvas":
            parts = []
            for i in w.find_all()[:400]:
                if w.type(i) == "text":
                    parts.append(w.itemcget(i, "text"))
            return _norm(" ".join(parts)[:20000])
        if cls == "Label":
            return _norm(w.cget("text")[:2000])
    except Exception:
        pass
    return ""


def build_timeline(path, stop=None):
    """(Timeline, '') or (None, text key). Works from the lyric cache of the song, a .lrc next to it, or the last CyroKayAI result."""
    raw, src = LY.read_cache(path)
    if not raw:
        side = LY.sidecar(path)
        if side:
            try:
                with open(side, encoding="utf-8", errors="replace") as f:
                    raw, src = f.read(), "file"
            except OSError:
                raw = ""
    if not raw and CK is not None:
        R = CK.last(path)
        if R and R.get("raw"):
            raw, src = R["raw"], R.get("source", "")
    if not raw:
        return None, "lv_none"
    pairs, synced = LY.parse(raw)
    if not synced or len(pairs) < 2:
        return None, "lv_plain"
    A = None
    if EA is not None:
        try:
            A = EA.analyze(path, stop)                  # from the cache when CyroKayAI has fitted the song (instant), else listened to now (a few seconds)
        except Exception as e:
            log("lyricview analyze: %r" % (e,))
    lead = CK.LEAD_SEC if (CK is not None and "CyroKayAI" in (src or "")) else 0.0
    dur = A.duration if A is not None else (E.total_time_seconds if getattr(E, "duration_known", False) else None)
    return CL.Timeline(pairs, A, lead, dur, LY.NOTE_HI, LY.NOTE_LO, LY.is_note), ""


class Mixin:
    # ------------------------------------------------------------------ helpers
    def lv_enabled(self):
        if os.environ.get("ROFPALYS_LYRICVIEW", "") == "0":
            return False
        return bool(MEM.get_pref("view", True)) if MEM is not None else True

    def lv_getpos(self):
        try:
            return (float(E.current_time_seconds), bool(E.is_playing and not E.is_paused), E.playing_song_name or "")
        except Exception:
            return (0.0, False, "")

    def lv_lead(self, path):
        """Seconds added to the song time for this song: the user's own correction, else this device's typical one (negative shift = lyrics earlier)."""
        try:
            return -MEM.shift_for(path) if (MEM is not None and path) else 0.0
        except Exception:
            return 0.0

    def lv_new_view(self, parent, bg=None):
        fam = None
        try:
            fam = self.f_big.actual("family")
        except Exception:
            pass
        pal = {"bg": bg or PNL, "fg": TXT, "accent": GOLD, "dim": DIM, "hint": BRN2}
        return VW.LyricView(parent, self.lv_getpos, palette=pal, family=fam, on_seek=self.lv_seek, on_nudge=self.lv_nudge, emoji=emoji_ok())

    def lv_seek(self, sec):
        try:
            E.seek(max(0.0, float(sec)))
        except Exception as e:
            log("lyricview seek: %r" % (e,))

    def lv_nudge(self, d):
        """The user moved the lyrics of this song d seconds (+ = later). Remembered for the song; the typical value becomes this device's shift."""
        path = E.playing_song_name or ""
        if MEM is None or not path:
            return
        try:
            MEM.set_nudge(path, MEM.shift_for(path) + d)
            MEM.save()
        except Exception as e:
            log("lyricview nudge: %r" % (e,))
        self.lv_apply(lead_only=True)

    def lv_views(self):
        return [v for v in (self.lv_view, self.lv_over) if v is not None]

    def lv_apply(self, lead_only=False):
        """Hand the current timeline (or the message) to every view."""
        cur = E.playing_song_name or ""
        lead = self.lv_lead(cur)
        for v in self.lv_views():
            try:
                if lead_only:
                    v.set_lead(lead)
                elif self.lv_tl is not None:
                    v.set_lyrics(self.lv_tl, cur, lead)
                else:
                    v.set_lyrics(None, cur, lead)
                    v.set_message(self.T(self.lv_msg) if self.lv_msg else "")
            except Exception as e:
                log("lyricview apply: %r" % (e,))

    # ------------------------------------------------------------------ the window
    def lv_open_window(self):
        if VW is None or not VW.TK:
            return
        if self.lv_win is not None:
            try:
                self.lv_win.lift()
                return
            except Exception:
                self.lv_win = None
        top = self.popup(self.T("lv_title"), 760, 700)
        self.lv_win = top
        top.protocol("WM_DELETE_WINDOW", self.lv_close_window)
        bar = tk.Frame(top, bg=PNL)
        bar.pack(side="bottom", fill="x", padx=14, pady=(4, 10))
        self.lv_var = tk.BooleanVar(value=self.lv_enabled())
        tk.Checkbutton(bar, text=self.T("lv_on"), variable=self.lv_var, command=self.lv_toggle, bg=PNL, fg=DIM, selectcolor=PNL2, activebackground=PNL,
                       activeforeground=GOLD, bd=0, highlightthickness=0, font=self.f_small, anchor="w").pack(side="left")
        self.btn(bar, self.T("close"), self.lv_close_window, bg=BRN, fg=BLK).pack(side="right")
        tk.Label(top, text=self.T("lv_hint"), bg=PNL, fg=DIM, font=self.f_small, anchor="w", wraplength=700, justify="left").pack(side="bottom", fill="x", padx=16)
        self.lv_view = self.lv_new_view(top, PNL)
        self.lv_view.pack(fill="both", expand=True, padx=8, pady=(10, 4))
        self.lv_view.update_idletasks()
        self.lv_view.start()
        self.lv_sig = None                               # load (or reload) for the views right away
        self.lv_apply()

    def lv_close_window(self):
        try:
            if self.lv_view is not None:
                self.lv_view.stop()
            if self.lv_win is not None:
                self.lv_win.destroy()
        except Exception:
            pass
        self.lv_win = self.lv_view = None

    def lv_toggle(self):
        on = bool(self.lv_var.get())
        if MEM is not None:
            MEM.set_pref("view", on)
        if not on:
            self.lv_unmount()

    # ------------------------------------------------------------------ in place: find the lyric area of the main window and lie over it
    def lv_find_target(self, loose=False):
        tl = self.lv_tl
        if tl is None:
            return None
        lines = [_norm(r.text) for r in tl.rows if r.kind == "line"]
        lines = [x for x in lines if len(x) >= (14 if loose else 8)]
        need = 1 if (loose or len(lines) < 2) else 2
        if len(lines) < need:
            return None
        best, best_area = None, 0
        stack = [self.root]
        while stack:
            w = stack.pop()
            try:
                kids = w.winfo_children()
            except Exception:
                continue
            for k in kids:
                if isinstance(k, tk.Toplevel) or (VW is not None and isinstance(k, VW.LyricView)):
                    continue
                stack.append(k)
                try:
                    if k.winfo_class() not in ("Text", "Canvas", "Label") or not k.winfo_viewable():
                        continue
                    wd, ht = k.winfo_width(), k.winfo_height()
                    if wd < (200 if loose else 150) or ht < (120 if loose else 80):
                        continue
                    txt = _widget_text(k)
                except Exception:
                    continue
                if txt and sum(1 for x in lines if x in txt) >= need and wd * ht > best_area:
                    best, best_area = k, wd * ht
        return best

    def lv_mount(self, target):
        try:
            bg = target.cget("bg")
            r, g, b = [x >> 8 for x in target.winfo_rgb(bg)]
            bg = "#%02x%02x%02x" % (r, g, b)
        except Exception:
            bg = PNL
        v = self.lv_new_view(target.master, bg)
        v.place(in_=target, x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(v)                                         # (Canvas.lift would raise canvas items, not the widget)
        self.lv_over, self.lv_target = v, target
        v.update_idletasks()
        v.start()
        self.lv_apply()

    def lv_unmount(self):
        v, self.lv_over, self.lv_target = self.lv_over, None, None
        if v is not None:
            try:
                v.stop()
                v.destroy()
            except Exception:
                pass

    def lv_overlay_tick(self):
        now = time.time()
        if now < self.lv_next:
            return
        self.lv_next = now + 0.8
        if not self.lv_enabled() or self.lv_tl is None:
            if self.lv_over is not None:
                self.lv_unmount()
            return
        if self.lv_over is not None:
            t = self.lv_target
            try:
                alive = t is not None and t.winfo_exists()
                if alive and t.winfo_viewable():
                    tk.Misc.lift(self.lv_over)
                    if not self.lv_over.winfo_ismapped():
                        self.lv_over.place(in_=t, x=0, y=0, relwidth=1, relheight=1)
                    return
                if alive:                                          # the page is not shown right now (another page): keep the view, hide it
                    self.lv_over.place_forget()
                    return
            except Exception:
                pass
            self.lv_unmount()                                      # the lyric area was rebuilt: find it again
        loose = (now - self.lv_since) > 8.0
        t = self.lv_find_target(loose)
        if t is not None:
            self.lv_mount(t)

    # ------------------------------------------------------------------ the poll loop (main thread)
    def lv_sig_now(self):
        cur = E.playing_song_name or ""
        try:
            m = os.path.getmtime(LY.cache_path(cur)) if cur else 0
        except OSError:
            m = 0
        try:
            side = LY.sidecar(cur) if cur else ""
            m2 = os.path.getmtime(side) if side else 0
        except OSError:
            m2 = 0
        return (cur, m, m2)

    def lv_poll(self):
        if VW is None or not VW.TK:
            return
        try:
            sig = self.lv_sig_now()
            if sig != self.lv_sig and not self.lv_busy:
                self.lv_sig = sig
                path = sig[0]
                if sig[0] != (self.lv_sig_prev or ""):
                    self.lv_since = time.time()
                self.lv_sig_prev = sig[0]
                if not path:
                    self.lv_tl, self.lv_msg = None, "lv_nosong"
                    self.lv_apply()
                else:
                    self.lv_busy = True
                    self.lv_msg = "lv_loading"
                    if self.lv_tl is None:
                        self.lv_apply()

                    def work(sig=sig, path=path):
                        try:
                            res = build_timeline(path, lambda: (E.playing_song_name or "") != path)
                        except Exception as e:
                            log("lyricview build: %r" % (e,))
                            res = (None, "lv_none")
                        self.lv_ready = (sig, res)
                    threading.Thread(target=work, daemon=True).start()
            ready, self.lv_ready = self.lv_ready, None
            if ready is not None:
                self.lv_busy = False
                sig, (tl, msg) = ready
                if sig == self.lv_sig:
                    self.lv_tl, self.lv_msg = tl, msg
                    self.lv_apply()
            self.lv_overlay_tick()
        except Exception as e:
            log("lyricview poll: %r" % (e,))


def build_lyricview_button(app, bar):
    app.b_lyrview = IconBtn(bar, "note", app.lv_open_window, size=20, bg=PNL, pad=7)
    app.b_lyrview.pack(side="right")
    return [app.b_lyrview.cv]


def register(app):
    if VW is None or CL is None or not VW.TK:
        return
    app.lv_win = app.lv_view = app.lv_over = app.lv_target = None
    app.lv_tl, app.lv_msg, app.lv_sig, app.lv_sig_prev, app.lv_busy, app.lv_ready = None, "", None, "", False, None
    app.lv_next, app.lv_since = 0.0, time.time()
    app.add_toolbar(11, build_lyricview_button)
    app.add_poll(lambda a: a.lv_poll())


# END-OF-FILE rofpalys_gui_lyricview.py

