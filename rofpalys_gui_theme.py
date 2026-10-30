#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: look & colours (Classic / Modern / Cyberpunk), changed while the window stays open
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""A palette button in the toolbar (and the key F6) opens three preview cards. Click one and the WHOLE window changes at once - colours, the form of buttons, menu,
lists and bars (square / rounded / cut corners), the type - no restart: the window is built again in the new look. The choice is remembered (rofpalys_theme.py keeps it in
<config>/theme.json). The same names work in the terminal:  rofpalys theme modern
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
import time

from rofpalys_gui_base import *   # noqa: F401,F403

try:
    import rofpalys_theme as TH
except Exception:
    TH = None
try:
    import rofpalys_analytics as AN
except Exception:
    AN = None

FEATURE = {"name": "theme", "title": "Look: Classic / Modern / Cyberpunk (colours + shapes + type)", "version": "2.0", "order": 12, "enabled": True}
_TXT = {"en": dict(title="Look and colours", sub="Pick a look. It changes at once and is remembered.", on="In use", use="Use this look", close="Close", key="Tip: F6 switches to the next look",
                   same="The whole window is built again in the new look (colours, shapes, type)."),
        "id": dict(title="Tampilan dan warna", sub="Pilih tampilan. Langsung berubah dan diingat.", on="Dipakai", use="Pakai tampilan ini", close="Tutup",
                   key="Tips: tombol F6 pindah ke tampilan berikutnya", same="Seluruh jendela dibangun ulang dengan tampilan baru (warna, bentuk, huruf).")}


def preview(cv, pal, x, y, w, h):
    """A small mock-up of the window in one look: its colours AND its shapes (never the current theme: every card shows its own)."""
    st = pal.get("STYLE") or {}
    shape, r = st.get("shape", "flat"), min(st.get("r", 0), 7)
    btn, chip = st.get("btn", "flat"), st.get("chip", "flat")
    nav = st.get("nav", "bar")
    draw_shape(cv, x, y, x + w, y + h, fill=pal["BLK"], outline=pal["BRN2"] if st.get("glow") else pal["GRID"], shape=shape, r=r + 2)
    sw = w * 0.22
    cv.create_rectangle(x + 2, y + 2, x + sw, y + h - 2, fill=pal["SIDE"], outline="")
    cv.create_rectangle(x + 10, y + 9, x + sw - 10, y + 15, fill=pal["TXT"] if st.get("logo") == "modern" else pal["GOLD"], outline="")                      # logo
    if st.get("logo") == "neon":
        cv.create_line(x + 10, y + 19, x + sw - 10, y + 19, fill=pal["INFO"], width=2)
    for k in range(4):
        iy = y + 26 + k * 15
        on = k == 0
        if nav == "bar":
            cv.create_rectangle(x + 4, iy, x + sw - 2, iy + 11, fill=pal["PNL"] if on else pal["SIDE"], outline="")
        elif nav == "pill":
            draw_shape(cv, x + 6, iy, x + sw - 5, iy + 11, fill=pal["HOVER"] if on else pal["SIDE"], shape="round", r=5)
        else:
            draw_shape(cv, x + 6, iy, x + sw - 5, iy + 11, fill=pal["HOVER"] if on else pal["SIDE"], shape="cut", r=4)
            if on:
                cv.create_rectangle(x + 4, iy + 1, x + 6, iy + 10, fill=pal["BRN2"], outline="")
        ix = x + 10
        if st.get("icons"):
            cv.create_oval(ix, iy + 3, ix + 5, iy + 8, fill=pal["GOLD"] if on else pal["DIM"], outline="")
            ix += 9
        cv.create_line(ix, iy + 5, ix + 14 - (k % 2) * 4, iy + 5, fill=pal["GOLD"] if on else pal["DIM"], width=2)
    px = x + sw + 8
    draw_shape(cv, px, y + 8, x + w - 8, y + h * 0.18, fill=pal["PNL2"], shape=shape, r=r)
    cv.create_text(px + 8, y + h * 0.09 + 4, text=("NOW PLAYING" if st.get("caps") else "Now Playing"), fill=pal["TXT"], anchor="w", font=("DejaVu Sans", 7, "bold"))
    rows = (y + h * 0.26, y + h * 0.26 + 17, y + h * 0.26 + 34)
    for k, ry in enumerate(rows):
        draw_shape(cv, px, ry, x + w - 8, ry + 14, fill=pal["HOVER"] if k == 1 else pal["ROW_HOVER"], outline=pal["BRN2"] if (k == 1 and st.get("glow")) else "", shape=shape, r=r)
        draw_shape(cv, px + 4, ry + 3, px + 12, ry + 11, fill=pal["PALETTE"][k % len(pal["PALETTE"])], shape=shape, r=2)
        cv.create_line(px + 18, ry + 7, px + 18 + 60 + k * 12, ry + 7, fill=pal["TXT"] if k == 1 else pal["DIM"], width=3)
    by = y + h - 26
    draw_shape(cv, px, by, x + w - 8, by + 18, fill=pal["SIDE"], shape=shape, r=r)
    if st.get("play") == "hex":
        cv.create_polygon(px + 5, by + 3, px + 14, by + 3, px + 17, by + 6, px + 17, by + 15, px + 8, by + 15, px + 5, by + 12, fill=pal["BLK"], outline=pal["GOLD"])
    else:
        cv.create_oval(px + 5, by + 3, px + 16, by + 14, fill=pal["GOLD"], outline="")
    tx0, tx1 = px + 24, x + w - 74
    kind = st.get("track", "flat")
    if kind == "seg":
        n = max(4, int((tx1 - tx0) // 6))
        for i in range(n):
            cv.create_rectangle(tx0 + i * 6, by + 7, tx0 + i * 6 + 4, by + 11, fill=pal["GOLD"] if i < n * 0.45 else pal["GRID"], outline="")
    else:
        mid = tx0 + (tx1 - tx0) * 0.45
        if kind == "round":
            draw_shape(cv, tx0, by + 7, tx1, by + 11, fill=pal["GRID"], shape="pill")
            draw_shape(cv, tx0, by + 7, mid, by + 11, fill=pal["GOLD"], shape="pill")
        else:
            cv.create_rectangle(tx0, by + 7, tx1, by + 11, fill=pal["GRID"], outline="")
            cv.create_rectangle(tx0, by + 7, mid, by + 11, fill=pal["BRN2"], outline="")
    bx0 = x + w - 62
    draw_shape(cv, bx0, y + h * 0.26 + 56, x + w - 12, y + h * 0.26 + 72, fill=pal["BRN"], outline=pal["INFO"] if st.get("glow") else "", shape=btn, r=5)
    cv.create_text(bx0 + 25, y + h * 0.26 + 64, text="OK", fill=pal["BLK"], font=("DejaVu Sans", 7, "bold"))
    draw_shape(cv, bx0 - 36, y + h * 0.26 + 56, bx0 - 6, y + h * 0.26 + 72, fill=pal["GOLD"] if chip != "flat" else pal["PNL2"], shape=chip, r=5)


class Mixin:
    def th_lang(self):
        return "id" if self.T("home") == "Beranda" else "en"

    def th_t(self, k):
        return _TXT[self.th_lang()].get(k, k)

    def th_open(self):
        if TH is None:
            return
        if self.th_win is not None:
            try:
                self.th_win.lift()
                return
            except Exception:
                self.th_win = None
        top = self.popup(self.th_t("title"), 700, 640)
        self.th_win = top
        top.protocol("WM_DELETE_WINDOW", self.th_close)
        self.btn(top, self.th_t("close"), self.th_close, bg=BRN, fg=BLK).pack(side="bottom", anchor="e", padx=18, pady=12)
        tk.Label(top, text=self.th_t("title"), bg=PNL, fg=TXT, font=self.f_big, anchor="w").pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(top, text=self.th_t("sub"), bg=PNL, fg=DIM, font=self.f_small, anchor="w").pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(top, text=self.th_t("key") + "     " + self.th_t("same"), bg=PNL, fg=DIM, font=self.f_small, anchor="w", wraplength=640, justify="left").pack(side="bottom", fill="x", padx=18)
        self.th_cards = {}
        for name in TH.names():
            cv = tk.Canvas(top, width=640, height=150, bg=PNL, highlightthickness=0, cursor="hand2")
            cv.pack(padx=18, pady=5)
            cv.bind("<Button-1>", lambda e, n=name: self.th_pick(n))
            self.th_cards[name] = cv
        self.th_draw()

    def th_draw(self):
        """Draw (again) the three cards. Each card shows its own palette; the frame and the label follow the CURRENT theme."""
        if self.th_win is None:
            return
        cur = TH.current()
        lang = self.th_lang()
        for name, cv in self.th_cards.items():
            try:
                cv.delete("all")
                cv.configure(bg=TH.get("PNL"))
                pal = TH.palette(name)
                on = name == cur
                cv.create_rectangle(1, 1, 639, 149, fill=TH.get("PNL2"), outline=TH.get("GOLD") if on else TH.get("GRID"), width=2 if on else 1)
                preview(cv, pal, 14, 14, 300, 122)
                fam = pick_family(pal["STYLE"]["display"], self.root)
                cv.create_text(336, 34, text=cap(TH.label(name, lang)) if pal["STYLE"]["caps"] else TH.label(name, lang), fill=TH.get("TXT"), anchor="w", font=(fam, self.f_big[1], "bold"))
                cv.create_text(336, 62, text=TH.describe(name, lang), fill=TH.get("DIM"), anchor="nw", width=290, font=self.f_small)
                for k, key in enumerate(("BRN", "GOLD", "ACC2", "INFO", "OK")):
                    draw_shape(cv, 336 + k * 26, 112, 336 + k * 26 + 18, 130, fill=pal[key], outline=pal["GRID"], shape="round" if pal["STYLE"]["shape"] == "round" else pal["STYLE"]["shape"], r=9 if pal["STYLE"]["shape"] == "round" else 5)
                if on:
                    cv.create_text(626, 22, text="✓ " + self.th_t("on"), fill=TH.get("GOLD"), anchor="e", font=self.f_small)
            except Exception:
                pass

    def th_apply(self, name, save_choice=True):
        """Switch the look: the palette + the style change everywhere, then the main window is built again in the new look. The theme card (this window) is opened again
        so that it shows the new shapes too."""
        old = TH.current()
        TH.switch(self.root, name, save_choice=save_choice, retint_main=False)
        if hasattr(self, "rebuild_ui"):
            self.rebuild_ui()
        else:                                                 # a window without rebuild_ui: colours only
            TH.retheme_tree(self.root, old, name)
        if self.th_win is not None:
            try:
                pos = "+%d+%d" % (self.th_win.winfo_x(), self.th_win.winfo_y())
                self.th_close()
                self.th_open()
                self.th_win.geometry(pos)
            except Exception as e:
                log("theme card: %r" % (e,))
        return old

    def th_pick(self, name):
        if TH is None or name == TH.current():
            return
        old = self.th_apply(name)
        if AN is not None and old != name:
            AN.note("theme", {"from": old, "to": name})

    def th_cycle(self, _e=None):
        if TH is None:
            return
        order = TH.names()
        self.th_pick(order[(order.index(TH.current()) + 1) % len(order)])

    def th_follow(self):
        """`rofpalys theme modern` in a terminal writes the choice into the file; the open window picks it up here (checked every two seconds)."""
        if TH is None or time.time() < self.th_next:
            return
        self.th_next = time.time() + 2.0
        if (os.environ.get("ROFPALYS_THEME") or "").strip():             # the environment wins over the file, so the file says nothing new
            return
        try:
            want = TH.saved_name()
            if want and want != TH.current():
                old = self.th_apply(want, save_choice=False)
                if AN is not None:
                    AN.note("theme", {"from": old, "to": want, "via": "command"})
        except Exception as e:
            log("theme follow: %r" % (e,))

    def th_close(self):
        try:
            if self.th_win is not None:
                self.th_win.destroy()
        finally:
            self.th_win = None


def build_theme_button(app, bar):
    app.b_theme = IconBtn(bar, "palette", app.th_open, size=20, bg=PNL, pad=7)
    app.b_theme.pack(side="right")
    return [app.b_theme.cv]


def register(app):
    app.th_win, app.th_cards, app.th_next = None, {}, 0.0
    if TH is None:                                   # rofpalys_theme.py is not installed: the window keeps the Classic look and has no palette button
        return
    app.add_toolbar(12, build_theme_button)
    app.add_poll(lambda a: a.th_follow())
    try:
        app.root.bind_all("<F6>", app.th_cycle)
    except Exception:
        pass
    TH.on_switch(lambda old, new, m: app.th_draw())          # (the cards are drawn again; the window itself is rebuilt by th_apply)


# END-OF-FILE rofpalys_gui_theme.py

