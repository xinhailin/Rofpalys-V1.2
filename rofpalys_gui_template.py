#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature TEMPLATE. Copy this file to rofpalys_gui_<yourname>.py, set "enabled": True and fill it in.
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""HOW TO ADD A FEATURE (no other file has to change):
   1. cp ~/rofpalys_gui_template.py ~/rofpalys_gui_hello.py       (the name must start with rofpalys_gui_ and use a-z 0-9 _)
   2. edit FEATURE (name, title, order, enabled=True) and register() below
   3. python ~/rofpalys.py install        -> the file is checked, installed and loaded the next time the GUI starts
   4. the last line of your file must be   # END-OF-FILE rofpalys_gui_hello.py   (so a file that was cut off while pasting is noticed)
If your feature breaks, the window still opens: the error is written in ~/.cache/rofpalys/gui.log and shown in  ? > Features loaded.

What register(app) can do - every call is optional:
   app.add_texts(en={"hello": "Hello"}, id={"hello": "Halo"})        your own texts, used as  app.T("hello")
   app.add_nav(order, "hello", "hello", "note")                      a button in the sidebar (icon: any kind of draw_icon in rofpalys_gui_base.py)
   app.add_view("hello", build_fn(app) -> Frame, show_fn(app))       the page behind that button (parent of the Frame: app.main)
   app.add_chip(order, "hello", "hello", page_fn(app) -> rows)       a tab in the library; rows like {"kind": "song"/"group"/"header"/"action", ...}
   app.add_row_menu(fn(app, menu, item))                             entries in the right-click menu of a song
   app.add_group_menu(fn(app, menu, item))                           ... of a folder / artist / playlist row
   app.add_menu("hello", fn(app))                                    entry in the "..." menu
   app.add_toolbar(order, build_fn(app, bar) -> [widgets], style_fn) buttons in the Now Playing toolbar (lowest order = rightmost)
   app.add_head_button("hello", fn(app), ("folder", "artist"))       button in the header of a group page, only for those group kinds
   app.add_group_provider(fn(app) -> [groups])                       more folder-like groups
   app.add_poll(fn(app))        every 0.2 s       app.add_relabel(fn(app))    after a language change       app.add_build(fn(app))   after the window exists
Methods you put in the Mixin class become methods of the window (self.something). Engine functions: E.play_song, E.queue_add, E.fx_apply ..."""
from rofpalys_gui_base import *   # noqa: F401,F403

FEATURE = {"name": "template", "title": "Template (copy me)", "version": "1.0", "order": 100, "enabled": False}


class Mixin:
    def hello_show(self):
        self.msg(self.T("hello"))


def register(app):
    app.add_texts(en={"hello": "Hello from my feature"}, id={"hello": "Halo dari fiturku"})
    app.add_menu("hello", lambda a: a.hello_show())


# END-OF-FILE rofpalys_gui_template.py

