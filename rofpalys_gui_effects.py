#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: Sound effects + A-B repeat
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Equalizer presets, speed, slowed + reverb, nightcore, normalize (toolbar button) and the A-B repeat button.
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
from rofpalys_gui_base import *   # noqa: F401,F403

FEATURE = {"name": "effects", "title": "Sound effects + A-B repeat", "version": "1.0", "order": 20, "enabled": True}


class Mixin:
    def open_effects(self):
        if self.fx_win is not None:
            try:
                self.fx_win.lift()
                return
            except Exception:
                self.fx_win = None
        T = self.T
        top = self.popup(T("fx"), 660, 520)
        self.fx_win = top
        top.protocol("WM_DELETE_WINDOW", self.close_effects)
        self.btn(top, T("close"), self.close_effects, bg=BRN, fg=BLK).pack(side="bottom", anchor="e", padx=18, pady=12)
        body = self.scrollable(top)
        tk.Label(body, text=T("fx"), bg=PNL, fg=TXT, font=self.f_big, anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(body, text=T("fx_note") % E.engine_name(), bg=PNL, fg=DIM, font=self.f_small, anchor="w", justify="left", wraplength=600).pack(fill="x", padx=18)
        self.seg(body, T("fx_preset"), [(k, T("fx_" + k)) for k in FX.PRESETS], lambda: FX.preset, lambda v: (E.fx_apply(preset=v), self.style_toolbar()))
        self.seg(body, T("fx_speed"), [(sp, "%gx" % sp) for sp in FX.SPEEDS], lambda: FX.speed, lambda v: (E.fx_apply(speed=float(v)), self.style_toolbar()))
        self.seg(body, T("fx_reverb"), [(k, T("off") if k == "off" else T("fx_" + k)) for k in FX.REVERBS], lambda: FX.reverb, lambda v: (E.fx_apply(reverb=v), self.style_toolbar()))
        self.seg(body, T("fx_norm"), [(False, T("off")), (True, T("on"))], lambda: FX.normalize, lambda v: (E.fx_apply(normalize=(v == "True")), self.style_toolbar()))
        self.btn(body, T("fx_normal"), lambda: (E.fx_apply(preset="normal", speed=1.0, reverb="off", normalize=False), self.close_effects(), self.style_toolbar()), fg=RED).pack(anchor="w", padx=18, pady=14)

    def close_effects(self):
        try:
            if self.fx_win is not None:
                self.fx_win.destroy()
        except Exception:
            pass
        self.fx_win = None

    def ab_click(self):
        E.ab_mark()
        self.style_toolbar()


def build_fx(app, bar):
    app.b_fx = IconBtn(bar, "equalizer", app.open_effects, size=20, bg=PNL, pad=7)
    app.b_fx.pack(side="right")
    return [app.b_fx.cv]


def build_ab(app, bar):
    app.b_ab = IconBtn(bar, "ab", app.ab_click, size=20, bg=PNL, pad=7)
    app.b_ab.pack(side="right")
    return [app.b_ab.cv]


def style(app):
    app.b_fx.set(color=GOLD if FX.is_active() else DIM)
    app.b_ab.set(color=GOLD if E.ab_a is not None else DIM)


def register(app):
    app.fx_win = None
    app.add_toolbar(20, build_fx, style)
    app.add_toolbar(30, build_ab)


# END-OF-FILE rofpalys_gui_effects.py

