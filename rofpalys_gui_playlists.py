#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI feature: playlists = your own groups of songs
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Playlists page (a tab in the library), "Add to playlist" everywhere, select many songs with check boxes, save a queue / search result /
folder as a playlist, rename / duplicate / export / delete. The storage and logic are in rofpalys_playlists.py; this file is only the screen part."""
from rofpalys_gui_base import *   # noqa: F401,F403

FEATURE = {"name": "playlists", "title": "Playlists (your own groups of songs)", "version": "2.0", "order": 60, "enabled": True}
GROUP_KINDS = ("category", "folder", "artist", "mix")        # groups whose songs can be added to a playlist in one go


class Mixin:
    # ---- the groups shown in the library
    def refresh_playlists(self):
        out = []
        for p in PL.all_playlists():
            out.append({"id": "pl:" + p["id"], "kind": "playlist", "name": p["name"], "sub": "", "pid": p["id"], "paths": [x for x in p["paths"] if os.path.isfile(x)]})
        self.pls = out
        return out

    def pl_id(self):
        return self.group[3:] if self.group.startswith("pl:") else ""

    def pl_refresh(self):
        self.rebuild_groups()
        self.apply_filter()

    # ---- create / fill
    def pl_save_paths(self, paths, default=""):
        """New playlist that starts with these songs (asks for the name). Returns its id or None."""
        paths = list(dict.fromkeys(p for p in paths if p))
        if not paths:
            self.msg(self.T("pl_nothing"))
            return None
        name = simpledialog.askstring(self.T("new_playlist"), self.T("name_prompt"), parent=self.root, initialvalue=default)
        if not (name and name.strip()):
            return None
        pid = PL.create_from(name.strip(), paths)
        self.msg(self.T("pl_made_n") % len(paths))
        self.pl_refresh()
        return pid

    def pl_new(self):
        pid = self.pl_save_paths_empty()
        if pid:
            self.open_group("pl:" + pid)

    def pl_save_paths_empty(self):
        name = simpledialog.askstring(self.T("new_playlist"), self.T("name_prompt"), parent=self.root)
        if name and name.strip():
            pid = PL.create(name.strip())
            self.pl_refresh()
            return pid
        return None

    def pl_new_with(self, paths):
        return self.pl_save_paths(paths)

    def pl_add_paths(self, pid, paths):
        n = PL.add_group(pid, paths)
        self.msg(self.T("pl_added_n") % n)
        self.pl_refresh()

    def pl_add(self, pid, path):
        self.pl_add_paths(pid, [path])

    def pl_pick_menu(self, paths):
        """A small menu at the mouse: which playlist should these songs go to (or a new one)?"""
        paths = list(dict.fromkeys(p for p in paths if p))
        if not paths:
            self.msg(self.T("pl_nothing"))
            return
        m = tk.Menu(self.root, tearoff=0, bg=PNL2, fg=TXT, activebackground=BRN, activeforeground=BLK, bd=0, font=self.f_ui)
        pls = PL.all_playlists()
        for pl in pls:
            m.add_command(label="%s   (%d)" % (pl["name"], len(pl["paths"])), command=lambda pid=pl["id"]: self.pl_add_paths(pid, paths))
        if pls:
            m.add_separator()
        m.add_command(label=self.T("new_pl_with"), command=lambda: self.pl_save_paths(paths))
        m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())

    def pl_save_page(self):
        """Whatever list is on screen (search results, a folder, favorites, Home ...) becomes a playlist."""
        paths = [it["path"] for it in self.rows.items if it["kind"] == "song"]
        self.pl_save_paths(paths, self.lbl_head.cget("text") if self.lbl_head.cget("text") else "")

    # ---- inside a playlist
    def pl_remove(self, path):
        if self.pl_id():
            PL.remove(self.pl_id(), path)
            self.pl_refresh()

    def pl_move(self, path, delta):
        if self.pl_id():
            PL.move(self.pl_id(), path, delta)
            self.pl_refresh()

    def pl_rename(self):
        g = self.gmap.get(self.group)
        if not g or g["kind"] != "playlist":
            return
        name = simpledialog.askstring(self.T("pl_rename"), self.T("name_prompt"), parent=self.root, initialvalue=g["name"])
        if name and name.strip():
            PL.rename(self.pl_id(), name.strip())
            self.pl_refresh()

    def pl_dup(self):
        if self.pl_id():
            pid = PL.duplicate(self.pl_id())
            self.pl_refresh()
            if pid:
                self.open_group("pl:" + pid)

    def pl_delete(self):
        g = self.gmap.get(self.group)
        if g and g["kind"] == "playlist" and messagebox.askyesno("Rofpalys", "%s: %s ?" % (self.T("pl_delete"), g["name"]), parent=self.root):
            PL.delete(self.pl_id())
            self.group = ""
            self.pl_refresh()
            self.save_ui()

    def pl_export(self):
        g = self.gmap.get(self.group)
        if not g or g["kind"] != "playlist":
            return
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=HOME, initialfile=g["name"] + ".m3u", defaultextension=".m3u")
        if path:
            self.msg("%s: %s" % (self.T("pl_export"), os.path.basename(path)) if PL.export_m3u(self.pl_id(), path) else "export failed")

    def pl_import(self):
        path = filedialog.askopenfilename(parent=self.root, initialdir=HOME, filetypes=[("M3U", "*.m3u *.m3u8"), ("All", "*")])
        if path:
            pid, n = PL.import_m3u(path)
            self.msg("%d %s" % (n, self.T("songs")) if pid else "nothing found in that file")
            self.pl_refresh()
            if pid:
                self.open_group("pl:" + pid)

    # ---- select many songs (check boxes) and do something with them
    def pl_select_toggle(self):
        on = not self.rows.select_mode
        self.rows.set_select_mode(on)
        if on:
            self.sel_bar.pack(before=self.rows.frame, fill="x", padx=18, pady=(0, 6))
            self.pl_select_update()
        else:
            self.sel_bar.pack_forget()

    def pl_selected_paths(self):
        """The songs that are ticked (a ticked folder / artist / playlist counts with all its songs)."""
        out = []
        for it in self.rows.items:
            k = RowList.key_of(it)
            if k and k in self.rows.checked:
                out += [it["path"]] if it["kind"] == "song" else list(it.get("paths", []))
        return list(dict.fromkeys(out))

    def pl_select_update(self):
        self.lbl_sel.configure(text=self.T("sel_count") % len(self.pl_selected_paths()))

    def pl_sel_all(self):
        self.rows.check_all()
        self.pl_select_update()

    def pl_sel_to_playlist(self):
        self.pl_pick_menu(self.pl_selected_paths())

    def pl_sel_queue(self):
        paths = self.pl_selected_paths()
        if paths:
            E.queue_add(paths)
        else:
            self.msg(self.T("pl_nothing"))

    def pl_sel_play(self):
        paths = self.pl_selected_paths()
        if paths:
            E.queue_clear()
            E.queue_add(paths[1:])
            self.play(paths[0])
        else:
            self.msg(self.T("pl_nothing"))


# ------------------------------------------------------------------ plug-in parts
def page(app):
    return [{"kind": "action", "title": app.T("new_playlist"), "action": "new_playlist"}] + [app.group_item(g) for g in app.refresh_playlists()]


def provider(app):
    return app.refresh_playlists()


def row_menu(app, m, it):
    p = it["path"]
    sub = tk.Menu(m, tearoff=0, bg=PNL2, fg=TXT, activebackground=BRN, activeforeground=BLK, bd=0, font=app.f_ui)
    have = set(PL.containing(p))
    for pl in PL.all_playlists():
        sub.add_command(label=("✓ " if pl["id"] in have else "   ") + pl["name"], command=lambda pid=pl["id"]: app.pl_add(pid, p))
    sub.add_separator()
    sub.add_command(label=app.T("new_pl_with"), command=lambda: app.pl_save_paths([p]))
    m.add_cascade(label=app.T("add_to_pl"), menu=sub)
    if app.group.startswith("pl:") and not app.query():
        m.add_command(label=app.T("remove_from_pl"), command=lambda: app.pl_remove(p))
        m.add_command(label=app.T("move_up"), command=lambda: app.pl_move(p, -1))
        m.add_command(label=app.T("move_down"), command=lambda: app.pl_move(p, 1))
    m.add_command(label=app.T("sel_mode"), command=app.pl_select_toggle)


def group_menu(app, m, it):
    paths = list(it.get("paths", []))
    m.add_command(label=app.T("add_all_to_pl"), command=lambda: app.pl_pick_menu(paths))
    m.add_command(label=app.T("play_all"), command=lambda: (E.queue_clear(), E.queue_add(paths[1:]), app.play(paths[0])) if paths else None)


def build(app):
    bar = tk.Frame(app.lv, bg=PNL2)
    app.sel_bar = bar
    app.lbl_sel = tk.Label(bar, text="", bg=PNL2, fg=GOLD, font=app.f_ui, padx=10)
    app.lbl_sel.pack(side="left")
    app.sel_btns = []
    for key, cmd in (("sel_done", app.pl_select_toggle), ("play", app.pl_sel_play), ("add_queue", app.pl_sel_queue), ("add_to_pl", app.pl_sel_to_playlist), ("sel_all", app.pl_sel_all)):
        b = app.btn(bar, "", cmd, bg=PNL2, padx=10, pady=4)
        b.pack(side="right", padx=2, pady=3)
        app.sel_btns.append((b, key))
    app.rows.on_select = lambda it: app.pl_select_update()
    relabel(app)


def relabel(app):
    if hasattr(app, "sel_btns"):
        for b, key in app.sel_btns:
            b.configure(text=app.T(key))


def empty(app):
    return app.T("pl_empty") if app.group.startswith("pl:") else ""


def register(app):
    app.pls = []
    app.add_chip(60, "playlists", "playlists", page)
    app.add_action("new_playlist", lambda a: a.pl_new())
    app.add_group_provider(provider)
    app.add_kind_label("playlist", "playlist")
    app.add_row_menu(row_menu)
    app.add_group_menu(group_menu)
    for label_key, cmd, kinds in (("pl_rename", lambda a: a.pl_rename(), ("playlist",)), ("pl_dup", lambda a: a.pl_dup(), ("playlist",)),
                                  ("pl_export", lambda a: a.pl_export(), ("playlist",)), ("pl_delete", lambda a: a.pl_delete(), ("playlist",)),
                                  ("add_to_pl", lambda a: a.pl_pick_menu(a.gmap[a.group]["paths"]), GROUP_KINDS)):
        app.add_head_button(label_key, cmd, kinds)
    app.add_menu("pl_import", lambda a: a.pl_import())
    app.add_menu("sel_mode", lambda a: a.pl_select_toggle())
    app.add_menu("pl_save_page", lambda a: a.pl_save_page())
    app.add_empty_text(empty)
    app.add_relabel(relabel)
    app.add_build(build)


# END-OF-FILE rofpalys_gui_playlists.py

