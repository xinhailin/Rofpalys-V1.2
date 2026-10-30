#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: Queue (Up next, recently played)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""The Queue page: what plays next, what you queued, what played before.
A feature file plugs into the window with register(app) and brings its methods in the Mixin class (see rofpalys_gui_template.py)."""
from rofpalys_gui_base import *   # noqa: F401,F403

FEATURE = {"name": "queue", "title": "Queue (Up next, recently played)", "version": "1.0", "order": 30, "enabled": True}


class Mixin:
    def queue_sig(self):
        return (E.playing_song_name, tuple(Q.upnext), len(Q.history))

    def show_queue(self):
        T, items, cur = self.T, [], E.playing_song_name
        self.lbl_qhead.configure(text=T("queue"))
        self.b_qclear.configure(text=T("queue_clear"))
        if cur:
            items += [self.header_item(T("queue_now")), self.song_item(cur)]
        if Q.upnext:
            items.append(self.header_item(T("queue_next")))
            for i, p in enumerate(Q.upnext):
                it = self.song_item(p)
                it["qi"] = i
                items.append(it)
        lst = E._playlist()
        ref = cur if cur in lst else E._ctx_song
        if ref in lst and len(lst) > 1:
            i0 = lst.index(ref) + 1
            nxt = [lst[(i0 + k) % len(lst)] for k in range(min(15, len(lst) - 1))]
            items.append(self.header_item(T("queue_ctx")))
            items += [self.song_item(p) for p in nxt]
        if Q.history:
            items.append(self.header_item(T("queue_hist")))
            items += [self.song_item(p) for p in reversed(Q.history[-20:])]
        self._qsig = self.queue_sig()
        self.qrows.set_items(items)

    def q_clear(self):
        E.queue_clear()
        self.show_queue()

    def q_activate(self, it):
        if it["kind"] != "song":
            return
        if "qi" in it:
            Q.remove(it["qi"])
        self.play(it["path"])
        self.show_queue()

    def q_menu(self, it, e):
        if it["kind"] != "song":
            return
        T, p = self.T, it["path"]
        m = tk.Menu(self.root, tearoff=0, bg=PNL2, fg=TXT, activebackground=BRN, activeforeground=BLK, bd=0, font=self.f_ui)
        m.add_command(label=T("play"), command=lambda: self.q_activate(it))
        if "qi" in it:
            qi = it["qi"]
            m.add_command(label=T("move_up"), command=lambda: (Q.move(qi, -1), self.show_queue()))
            m.add_command(label=T("move_down"), command=lambda: (Q.move(qi, 1), self.show_queue()))
            m.add_command(label=T("pl_delete"), command=lambda: (Q.remove(qi), self.show_queue()))
        else:
            m.add_command(label=T("add_queue"), command=lambda: (E.queue_add([p]), self.show_queue()))
        m.tk_popup(e.x_root, e.y_root)

    def queue_save_playlist(self):
        """Keep the queue (the song that plays + Up next) as a playlist - needs the playlists feature."""
        paths = ([E.playing_song_name] if E.playing_song_name else []) + list(Q.upnext)
        if hasattr(self, "pl_save_paths"):
            self.pl_save_paths(paths, "Queue")
        else:
            self.msg("playlists feature is not installed")


def build_view(app):
    qv = tk.Frame(app.main, bg=PNL)
    head = tk.Frame(qv, bg=PNL)
    head.pack(fill="x", padx=18, pady=(14, 6))
    app.lbl_qhead = tk.Label(head, text="", bg=PNL, fg=TXT, font=app.f_big, anchor="w")
    app.lbl_qhead.pack(side="left")
    app.b_qclear = app.btn(head, "", app.q_clear)
    app.b_qclear.pack(side="right")
    app.b_qsave = app.btn(head, "", app.queue_save_playlist)
    app.b_qsave.pack(side="right", padx=6)
    app.qrows = RowList(app, qv)
    app.qrows.frame.pack(fill="both", expand=True, padx=(8, 4), pady=(0, 6))
    app.qrows.on_activate = app.q_activate
    app.qrows.on_heart = lambda it: app.toggle_fav(it["path"])
    app.qrows.on_menu = app.q_menu
    return qv


def show_view(app):
    app.show_queue()


def poll(app):
    if app.view == "queue" and app.queue_sig() != app._qsig:
        app.show_queue()


def row_menu(app, m, it):
    p = it["path"]
    m.add_command(label=app.T("play_next"), command=lambda: E.queue_add([p], front=True))
    m.add_command(label=app.T("add_queue"), command=lambda: E.queue_add([p]))


def group_menu(app, m, it):
    paths = list(it.get("paths", []))
    m.add_command(label=app.T("add_all_queue"), command=lambda: E.queue_add(paths))


def relabel(app):
    app.lbl_qhead.configure(text=app.T("queue"))
    app.b_qclear.configure(text=app.T("queue_clear"))
    app.b_qsave.configure(text=app.T("pl_save_queue"))


def register(app):
    app._qsig = None
    app.add_nav(30, "queue", "queue", "queue")
    app.add_view("queue", build_view, show_view)
    app.add_row_menu(row_menu)
    app.add_group_menu(group_menu)
    app.add_poll(poll)
    app.add_relabel(relabel)


# END-OF-FILE rofpalys_gui_queue.py

