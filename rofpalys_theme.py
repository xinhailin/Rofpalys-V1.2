#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - themes: Classic (brown), Modern (graphite + mint) and Cyberpunk (neon) - chosen at start, changeable while the window is open
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Three looks for the same program. A theme is a palette AND a style. The palette: the names the window already uses (BLK SIDE PNL PNL2 HOVER ROW_HOVER BRN BRN2
GOLD TXT DIM RED, PALETTE, COVER_SHADES) plus extra roles for the newer screens (OK WARN INFO ACC2 GRID CARD CARD2 NOWBG PH1 PH2 LYR). The style (STYLES): the SHAPES
and the TYPE of the look - square / rounded / cut corners, the way the sidebar marks the page you are on, icons in the menu, capital letters, the form of the play button,
the progress bar and its knob, glow lines, and the font families (each theme lists fonts in order of preference; the first one installed is used).

  at start     rofpalys_gui_base.py asks apply_to(globals()), so the whole window is built in the chosen theme
  while open   switch(root, "cyberpunk") changes the palette names AND the style in every loaded rofpalys module (also the file that was started directly). The
               main window is then BUILT AGAIN in the new look by the window itself (rebuild_ui), so nothing of the old look is left: colours, shapes and fonts all
               come from the new theme. Windows that are open at that moment (settings, lyrics ...) are re-coloured in place (every widget colour and every canvas
               item colour of the old palette becomes the matching colour of the new one; ttk styles are not touched) and take the new shapes when opened next.
  the choice   is saved in <config>/theme.json; the environment variable ROFPALYS_THEME=classic|modern|cyberpunk wins.
The palettes were checked with the WCAG contrast formula (text on every surface, button text on button colours): see check()."""
import json
import os
import sys

try:
    import rofpalys_library as _lib
    _CFG = _lib.CONFIG_DIR
except Exception:
    _CFG = os.path.join(os.path.expanduser("~"), ".config", "rofpalys")

__version__ = "2.0"
ORDER = ("classic", "modern", "cyberpunk")
PATH = os.path.join(_CFG, "theme.json")
INFO = {
    "classic": {"name": "Classic", "en": "Warm brown, square corners - the original look", "id": "Coklat hangat, sudut kotak - tampilan asli"},
    "modern": {"name": "Modern", "en": "Graphite and mint, rounded corners, menu icons - clean and high contrast, like the big music apps",
               "id": "Grafit dan mint, sudut membulat, ikon menu - bersih dan kontras tinggi, seperti aplikasi musik besar"},
    "cyberpunk": {"name": "Cyberpunk", "en": "Neon magenta, cyan and yellow on deep violet, cut corners, tech type, glowing lines",
                  "id": "Neon magenta, cyan, dan kuning di atas ungu pekat, sudut terpotong, huruf teknologi, garis bercahaya"},
}
LISTS = ("PALETTE", "COVER_SHADES")
ROLES = ("BLK", "SIDE", "PNL", "PNL2", "HOVER", "ROW_HOVER", "BRN", "BRN2", "GOLD", "TXT", "DIM", "RED")
EXTRA = ("OK", "WARN", "INFO", "ACC2", "GRID", "CARD", "CARD2", "NOWBG", "PH1", "PH2", "LYR")
_COLOR_OPTS = ("background", "foreground", "activebackground", "activeforeground", "highlightbackground", "highlightcolor", "selectbackground",
               "selectforeground", "insertbackground", "troughcolor", "disabledforeground", "readonlybackground", "selectcolor", "buttonbackground")

THEMES = {
    # the colours the program has always had
    "classic": dict(BLK="#0b0705", SIDE="#120b07", PNL="#1a110b", PNL2="#261811", HOVER="#33200f", ROW_HOVER="#21150d",
                    BRN="#8b5a2b", BRN2="#a96f3a", GOLD="#d9a560", TXT="#ead9bd", DIM="#8a7660", RED="#c0392b",
                    PALETTE=["#6f4521", "#8b5a2b", "#a96f3a", "#c68642", "#d9a560", "#e8c58f"],
                    COVER_SHADES=["#4a2c14", "#5b361a", "#6b4020", "#3d2511", "#7a4c22", "#52301a"],
                    OK="#9bb35c", WARN="#e0a43c", INFO="#7fa6b8", ACC2="#c9794a", GRID="#3b2714", CARD="#1f140e", CARD2="#2d1c10",
                    NOWBG="#241509", PH1="#3a2414", PH2="#7a4c22", LYR="#b9a48a"),
    # graphite surfaces in small elevation steps, one mint accent, cool blue / violet as second voice, off-white text
    "modern": dict(BLK="#0a0b0d", SIDE="#0f1114", PNL="#14171b", PNL2="#1b1f25", HOVER="#262b33", ROW_HOVER="#1a1e24",
                   BRN="#1fb67a", BRN2="#2ad18c", GOLD="#43e6a6", TXT="#f1f4f8", DIM="#8e99aa", RED="#ff5470",
                   PALETTE=["#0f7f57", "#1fb67a", "#2ad1b0", "#34c8e8", "#5b8def", "#8a6bf0"],
                   COVER_SHADES=["#16322b", "#1b3b33", "#20463c", "#122a24", "#255246", "#1a3a32"],
                   OK="#3ddc84", WARN="#ffb84d", INFO="#4da3ff", ACC2="#9a7bff", GRID="#242932", CARD="#171b20", CARD2="#20252c",
                   NOWBG="#101418", PH1="#16322b", PH2="#2c7a63", LYR="#b4bfcd"),
    # deep violet-black, hot magenta buttons, cyber yellow highlights, cyan for information
    "cyberpunk": dict(BLK="#07040f", SIDE="#0c0719", PNL="#120a24", PNL2="#1b1033", HOVER="#2c1853", ROW_HOVER="#190e30",
                      BRN="#e0189e", BRN2="#ff2bd6", GOLD="#fcee0a", TXT="#e8f6ff", DIM="#9a88dc", RED="#ff4468",
                      PALETTE=["#ff5fe3", "#b14bff", "#6c63ff", "#00b8ff", "#00e0ff", "#ffe600"],
                      COVER_SHADES=["#2a0f4a", "#3b1266", "#1e1b5e", "#0f2f5a", "#4a0f4a", "#12304a"],
                      OK="#b6ff00", WARN="#ff9f1c", INFO="#00f0ff", ACC2="#a06bff", GRID="#2a1650", CARD="#150c2b", CARD2="#20123d",
                      NOWBG="#0f0722", PH1="#2a0f4a", PH2="#7a2bb8", LYR="#bcaef0"),
}
# The shapes and the type of each look (no colours here). Every theme defines every key.
#   shape  corners of cards, list rows, boxes:  flat (square) | round | cut (chamfered, top-left and bottom-right)       r = corner size in pixels
#   btn / chip   the form of buttons and of the little tabs (chips):  flat | round | pill (fully round ends) | cut
#   nav    how the sidebar marks the page in use:  bar (the whole row is filled) | pill (rounded fill) | edge (neon bar at the left + fill)
#   icons  a small icon in front of each sidebar item      caps  CAPITAL LETTERS for menu items, buttons and headings     pad  roominess of buttons (1.0 = as before)
#   play   the play button:  circle | hex (cut-corner plate with a neon outline)       track  progress and volume bars:  flat | round | seg (segments)
#   knob   the handle on those bars:  dot | diamond                                       glow   0 none, 1 one neon line, 2 two lines (cyan + magenta)
#   sep    thin separator lines between the zones of the window                           logo   classic | modern | neon
#   ui / display / mono   font families in order of preference (the first installed one is used);  fs / dfs = size change of the normal / the display text
_BASE_FONTS = ("DejaVu Sans", "DejaVu Sans Mono", "Helvetica", "Arial", "TkDefaultFont")
STYLES = {
    "classic": dict(shape="flat", r=0, btn="flat", chip="flat", nav="bar", icons=False, caps=False, pad=1.0, play="circle", track="flat", track_h=4, knob="dot", knob_r=5, glow=0, sep=False,
                    logo="classic", fs=0, dfs=0, ui=("DejaVu Sans",), display=("DejaVu Serif",), mono=("DejaVu Sans Mono",)),
    "modern": dict(shape="round", r=10, btn="pill", chip="pill", nav="pill", icons=True, caps=False, pad=1.12, play="circle", track="round", track_h=6, knob="dot", knob_r=6, glow=0, sep=True,
                   logo="modern", fs=0, dfs=0, ui=("Inter", "SF Pro Text", "Segoe UI", "Roboto", "Noto Sans", "Helvetica Neue", "Ubuntu", "Cantarell", "DejaVu Sans"),
                   display=("Inter", "SF Pro Display", "Segoe UI Semibold", "Segoe UI", "Roboto", "Noto Sans", "Helvetica Neue", "Ubuntu", "DejaVu Sans"),
                   mono=("JetBrains Mono", "SF Mono", "Consolas", "Roboto Mono", "DejaVu Sans Mono")),
    "cyberpunk": dict(shape="cut", r=8, btn="cut", chip="cut", nav="edge", icons=True, caps=True, pad=1.0, play="hex", track="seg", track_h=6, knob="diamond", knob_r=7, glow=2, sep=True,
                      logo="neon", fs=-1, dfs=-1, ui=("Rajdhani", "Oxanium", "Share Tech Mono", "Orbitron", "JetBrains Mono", "Fira Code", "Consolas", "Menlo", "DejaVu Sans Mono"),
                      display=("Orbitron", "Audiowide", "Oxanium", "Rajdhani", "Share Tech Mono", "JetBrains Mono", "Consolas", "Menlo", "DejaVu Sans Mono"),
                      mono=("Share Tech Mono", "JetBrains Mono", "Fira Code", "Consolas", "Menlo", "DejaVu Sans Mono")),
}
STYLE = {}                                           # the style of the look in use: ONE dict that is changed in place, so every module that imported it sees a switch
_HOOKS = []
_STATE = {"name": None}


# ------------------------------------------------------------------ choosing
def names():
    return list(ORDER)


def label(name, lang="en"):
    i = INFO.get(name) or INFO["classic"]
    return i["name"]


def describe(name, lang="en"):
    i = INFO.get(name) or INFO["classic"]
    return i["id" if lang == "id" else "en"]


def current():
    """The theme in force: environment, then the saved choice, then classic."""
    if _STATE["name"] in THEMES:
        return _STATE["name"]
    n = (os.environ.get("ROFPALYS_THEME") or "").strip().lower()
    if n not in THEMES:
        try:
            with open(PATH, encoding="utf-8") as f:
                n = str(json.load(f).get("theme", "")).lower()
        except (OSError, ValueError, AttributeError):
            n = ""
    _STATE["name"] = n if n in THEMES else "classic"
    return _STATE["name"]


def save(name):
    if name not in THEMES:
        return False
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH + ".part", "w", encoding="utf-8") as f:
            json.dump({"theme": name}, f)
        os.replace(PATH + ".part", PATH)
        return True
    except OSError:
        return False


def _sync_style(name):
    STYLE.clear()
    STYLE.update(STYLES[name])


def style(name=None):
    """A copy of the style (shapes and fonts) of a theme; without a name: the look in use."""
    return dict(STYLES[name or current()])


def palette(name=None):
    """A copy of the whole palette of a theme (lists are copied too) and, under "STYLE", a copy of its style (screens that draw shapes read it from here)."""
    name = name or current()
    p = THEMES[name]
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in p.items()}
    out["STYLE"] = dict(STYLES[name])
    return out


def get(role, default="#ff00ff"):
    """One colour of the CURRENT theme (screens that draw themselves call this every time they draw, so they follow a switch at once)."""
    return THEMES[current()].get(role, default)


def apply_to(ns, name=None):
    """Put the palette of `name` (default: the current theme) into a module namespace: the colour names are set, the two lists are changed IN PLACE
    (every module that imported the same list sees it). Names the namespace does not have yet are created too."""
    p = THEMES[name or current()]
    for k, v in p.items():
        if k in LISTS and isinstance(ns.get(k), list):
            ns[k][:] = v
        elif k in LISTS:
            ns[k] = list(v)
        else:
            ns[k] = v
    if name is None or name == current():                      # the live style dict (changed in place by switch); a preview of another look gets a copy
        _sync_style(current())
        ns["STYLE"] = STYLE
    else:
        ns["STYLE"] = dict(STYLES[name])


# ------------------------------------------------------------------ colour maths
def _rgb(h):
    h = (h or "").strip().lower()
    if len(h) == 4 and h[0] == "#":
        h = "#" + "".join(c * 2 for c in h[1:])
    if len(h) != 7 or h[0] != "#":
        return None
    try:
        return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    except ValueError:
        return None


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x)))) for x in c)


def luminance(h):
    r = _rgb(h)
    if r is None:
        return 0.0
    v = [(x / 255.0) for x in r]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def contrast(a, b):
    """WCAG contrast ratio 1..21 (4.5 is the usual minimum for text, 7 is the 'AAA' level)."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def check(name=None):
    """[(what, ratio, minimum, ok)] for a theme: the contrast of text on every surface and of button text on every button colour."""
    p = THEMES[name or current()]
    out = []
    for s in ("BLK", "SIDE", "PNL", "PNL2", "HOVER", "CARD", "CARD2"):
        out.append(("TXT on %s" % s, contrast(p["TXT"], p[s]), 7.0))
    for s in ("BLK", "SIDE", "PNL", "PNL2", "CARD"):
        out.append(("DIM on %s" % s, contrast(p["DIM"], p[s]), 4.5 if name != "classic" else 3.5))
        out.append(("GOLD on %s" % s, contrast(p["GOLD"], p[s]), 4.5))
    for b in ("BRN", "BRN2", "GOLD"):
        out.append(("BLK on button %s" % b, contrast(p["BLK"], p[b]), 4.5 if name != "classic" else 3.0))
    out.append(("LYR (lyrics) on PNL", contrast(p["LYR"], p["PNL"]), 4.5))
    out.append(("TXT on NOWBG", contrast(p["TXT"], p["NOWBG"]), 7.0))
    return [(w, round(r, 2), m, r >= m) for w, r, m in out]


# colour names that may share one colour inside a theme: they share it in the original look, and the new looks keep the same pairs where they can
_SHARED = {"classic": {("BRN", "PALETTE1"), ("BRN2", "PALETTE2"), ("GOLD", "PALETTE4")}, "modern": {("BRN", "PALETTE1")}, "cyberpunk": set()}


def collisions(name):
    """[(colour, [names])] where two or more names of one theme have the same colour and that is not one of the allowed pairs. Such a pair could not be told apart
    again when switching back, so every theme must be free of them (selftest checks it)."""
    p = THEMES[name]
    seen = {}
    for k in ROLES + EXTRA:
        seen.setdefault(p[k].lower(), []).append(k)
    for i, c in enumerate(p["PALETTE"]):
        seen.setdefault(c.lower(), []).append("PALETTE%d" % i)
    out = []
    for c, ks in seen.items():
        if len(ks) > 1 and not all((a, b) in _SHARED[name] or (b, a) in _SHARED[name] for a in ks for b in ks if a != b):
            out.append((c, ks))
    return out


def color_map(old, new):
    """{old colour: new colour} for every colour of the old palette. Named roles come first, then the two lists by position."""
    po, pn = THEMES[old], THEMES[new]
    m = {}
    for k in LISTS:
        for a, b in zip(po[k], pn[k]):
            m.setdefault(a.lower(), b.lower())
    for k in tuple(EXTRA) + tuple(ROLES):
        m[po[k].lower()] = pn[k].lower()                                   # the names the window uses overwrite the extras, which overwrite the list entries: when two roles
    return m                                                              # share one colour (modern: GOLD and OK), the window's own name decides


class Mapper:
    """Maps one colour string of the old theme to the new theme: exact palette colours first, then 'nearest palette colour + the same difference'
    for colours that were blended at run time (within a distance of 60 in RGB); anything else is left alone."""

    def __init__(self, old, new):
        self.exact = color_map(old, new)
        self.newset = {str(v).lower() for k, v in THEMES[new].items() if isinstance(v, str)} | {c.lower() for k in LISTS for c in THEMES[new][k]}
        self.rgbs = [(_rgb(a), _rgb(b)) for a, b in self.exact.items()]
        self.cache = {}

    def __call__(self, c):
        if not isinstance(c, str):
            return None
        k = c.strip().lower()
        if k in self.cache:
            return self.cache[k]
        r = _rgb(k)
        out = None
        if k in self.exact:
            out = self.exact[k]
        elif k in self.newset:
            out = None                                                      # already a colour of the new theme: never move it a second time
        elif r is not None:
            best = None
            for a, b in self.rgbs:
                if a is None or b is None:
                    continue
                d = sum((x - y) ** 2 for x, y in zip(r, a)) ** 0.5
                if d <= 60 and (best is None or d < best[0]):
                    best = (d, a, b)
            if best is not None:
                _, a, b = best
                out = _hex([bb + (x - aa) for x, aa, bb in zip(r, a, b)])
        self.cache[k] = out
        return out


# ------------------------------------------------------------------ switching while the window is open
def on_switch(fn):
    """fn(old, new, mapper) is called after every switch (icons, charts and windows that keep colours of their own repaint here)."""
    if fn not in _HOOKS:
        _HOOKS.append(fn)


def _retint(w, mapper):
    """One widget: every colour option that belongs to the old palette gets the new colour."""
    own = getattr(w, "retint", None)
    if callable(own):                                       # a drawn widget of ours (rofpalys_gui_base.ShapeLabel ...) keeps its colours itself
        try:
            own(mapper)
            return
        except Exception:
            pass
    for opt in _COLOR_OPTS:
        try:
            cur = w.cget(opt)
        except Exception:
            continue
        new = mapper(cur) if isinstance(cur, str) else None
        if new and new != str(cur).lower():
            try:
                w.configure(**{opt: new})
            except Exception:
                pass
    cls = w.winfo_class()
    if cls == "Canvas":
        for item in w.find_all():
            for opt in ("fill", "outline"):
                try:
                    cur = w.itemcget(item, opt)
                except Exception:
                    continue
                new = mapper(cur) if cur else None
                if new and new != str(cur).lower():
                    try:
                        w.itemconfigure(item, **{opt: new})
                    except Exception:
                        pass
    elif cls == "Menu":
        try:
            last = w.index("end")
        except Exception:
            last = None
        for i in range(0, (last if last is not None else -1) + 1):
            for opt in ("background", "foreground", "activebackground", "activeforeground"):
                try:
                    cur = w.entrycget(i, opt)
                except Exception:
                    continue
                new = mapper(cur) if cur else None
                if new:
                    try:
                        w.entryconfigure(i, **{opt: new})
                    except Exception:
                        pass


def retheme_tree(root, old, new, mapper=None):
    """Re-colour a Tk widget tree from the old theme to the new one. Returns how many widgets were visited."""
    mapper = mapper or Mapper(old, new)
    n = 0
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            _retint(w, mapper)
            n += 1
            stack.extend(w.winfo_children())
        except Exception:
            continue
    return n


def _follow_modules(old, name):
    """The colour names (and the lists) of every loaded rofpalys module - and of the file that was started directly (__main__) - become those of the new look."""
    for modname, mod in list(sys.modules.items()):
        if mod is None or modname == __name__ or not (modname.startswith("rofpalys") or modname == "__main__"):
            continue
        d = getattr(mod, "__dict__", None)
        if d is None:
            continue
        for k in tuple(ROLES) + tuple(EXTRA):
            if k in d and isinstance(d[k], str) and d[k].lower() == THEMES[old][k].lower():
                d[k] = THEMES[name][k]
        for k in LISTS:
            if k in d and isinstance(d[k], list) and [str(x).lower() for x in d[k]] == [x.lower() for x in THEMES[old][k]]:
                d[k][:] = THEMES[name][k]
        if "STYLE" in d and d["STYLE"] is not STYLE and isinstance(d["STYLE"], dict) and d["STYLE"].get("shape") == STYLES[old]["shape"]:
            d["STYLE"] = STYLE                                # a module that kept its own copy of the style joins the live one


def switch(root, name, save_choice=True, retint_main=True):
    """Change the theme of the running program. Must be called from the Tk thread. Returns the number of widgets that were visited (0: nothing to do).
    retint_main=False: the caller builds its main window again (the GUI does), so only the windows that are open next to it (Toplevels) are re-coloured here."""
    if name not in THEMES:
        return 0
    old = current()
    if name == old:
        return 0
    mapper = Mapper(old, name)
    if save_choice:
        save(name)
    _STATE["name"] = name
    _sync_style(name)
    _follow_modules(old, name)
    n = 0
    if root is not None:
        if retint_main:
            n = retheme_tree(root, old, name, mapper)
        else:
            try:
                for w in root.winfo_children():
                    if w.winfo_class() == "Toplevel":
                        n += retheme_tree(w, old, name, mapper)
            except Exception:
                pass
    for fn in list(_HOOKS):
        try:
            fn(old, name, mapper)
        except Exception:
            pass
    return n


def saved_name():
    """The look written in the file (the environment is not looked at): the running window compares this with what it shows."""
    try:
        with open(PATH, encoding="utf-8") as f:
            n = str(json.load(f).get("theme", "")).lower()
    except (OSError, ValueError, AttributeError):
        return ""
    return n if n in THEMES else ""


def _lang():
    v = (os.environ.get("ROFPALYS_LANG") or os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    return "id" if v.startswith("id") else "en"


def _swatch(name):
    """Five colour blocks of a theme for terminals that know 24-bit colour (an empty string when the output is not a terminal)."""
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return ""
    p = THEMES[name]
    out = ""
    for role in ("PNL", "CARD", "GOLD", "BRN2", "ACC2", "OK"):
        r, g, b = _rgb(p[role])
        out += "\x1b[48;2;%d;%d;%dm  \x1b[0m" % (r, g, b)
    return out + " "


USAGE = {"en": """  rofpalys theme                 the three looks and the one in use
  rofpalys theme NAME            classic | modern | cyberpunk   - saved; an open window follows within two seconds
  rofpalys theme next            the next look
  rofpalys theme check [NAME]    contrast report (WCAG) of the palettes""",
         "id": """  rofpalys theme                 tiga tampilan dan yang sedang dipakai
  rofpalys theme NAMA            classic | modern | cyberpunk   - disimpan; jendela yang terbuka ikut berubah dalam dua detik
  rofpalys theme next            tampilan berikutnya
  rofpalys theme check [NAMA]    laporan kontras (WCAG) palet warna"""}


def cli(argv):
    """rofpalys theme [NAME | next | check [NAME] | help]"""
    lg = _lang()
    a = [x for x in argv if x]
    cmd = a[0].lower() if a else ""
    if cmd in ("help", "-h", "--help"):
        print(USAGE[lg])
        return 0
    if cmd == "check":
        want = [a[1].lower()] if len(a) > 1 else list(ORDER)
        bad = 0
        for n in want:
            if n not in THEMES:
                print("unknown look: %s (%s)" % (n, ", ".join(ORDER)))
                return 1
            for what, ratio, need, good in check(n):
                bad += not good
                print("  %-10s %-24s %5.1f:1  (needs %.1f)  %s" % (n, what, ratio, need, "ok" if good else "TOO LOW"))
            col = collisions(n)
            print("  %-10s colours shared between roles: %s" % (n, col or "none"))
        return 1 if bad else 0
    cur = current()
    if cmd in ("", "list"):
        for n in ORDER:
            print("  %s%s %-10s %s" % ("*" if n == cur else " ", _swatch(n), INFO[n]["name"], describe(n, lg)))
        print("\n" + USAGE[lg])
        return 0
    name = ORDER[(ORDER.index(cur) + 1) % len(ORDER)] if cmd == "next" else cmd
    if name not in THEMES:
        print("%s: %s" % ({"en": "unknown look", "id": "tampilan tidak dikenal"}[lg], cmd))
        print(USAGE[lg])
        return 1
    if not save(name):
        print({"en": "could not write ", "id": "tidak bisa menulis "} [lg] + PATH)
        return 1
    print("%s %s - %s" % ({"en": "saved:", "id": "tersimpan:"}[lg], INFO[name]["name"], {"en": "an open window follows within two seconds; the next start uses it.", "id": "jendela yang terbuka ikut berubah dalam dua detik; start berikutnya memakainya."}[lg]))
    env = (os.environ.get("ROFPALYS_THEME") or "").strip().lower()
    if env in THEMES and env != name:
        print({"en": "note: ROFPALYS_THEME=%s is set in this shell and wins over the saved choice.", "id": "catatan: ROFPALYS_THEME=%s terpasang di shell ini dan mengalahkan pilihan tersimpan."}[lg] % env)
    return 0


def selftest(verbose=True):
    ok = True
    for n in ORDER:
        bad = [(w, r, m) for w, r, m, good in check(n) if not good]
        col = collisions(n)
        if bad or col:
            ok = False
        if verbose:
            print("  theme %-10s contrast checks: %d, failed: %s, shared colours: %s" % (n, len(check(n)), bad or "none", col or "none"))
    keys = set(STYLES["classic"])
    for n in ORDER:
        if set(STYLES[n]) != keys or any(not STYLES[n][k] for k in ("ui", "display", "mono")):
            ok = False
            if verbose:
                print("  style %-10s does not define the same keys as classic" % n)
    m = Mapper("classic", "modern")
    ok = ok and m("#1a110b") == THEMES["modern"]["PNL"] and m("#ead9bd") == THEMES["modern"]["TXT"] and m("#123456") is None
    near = m("#1c130d")                                                     # a blended colour next to PNL moves with PNL
    ok = ok and near is not None and contrast(near, THEMES["modern"]["TXT"]) > 7
    return ok


# END-OF-FILE rofpalys_theme.py

