#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - GUI building blocks (colours, texts, icons, list, logo) shared by rofpalys_gui.py and every rofpalys_gui_<feature>.py
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Nothing here opens a window. rofpalys_gui.py (the window) and the feature files (rofpalys_gui_playlists.py, ...) both import this with
    from rofpalys_gui_base import *"""
import atexit
import bisect
import json
import math
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import zlib

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, messagebox, simpledialog
except ImportError:
    tk = tkfont = None

import rofpalys_engine as E
import rofpalys_library as L
import rofpalys_library as lib
import rofpalys_alarm as AL
import rofpalys_control as CT
import rofpalys_effects as FX
import rofpalys_lyrics as LY
import rofpalys_media as M
import rofpalys_playlists as PL
import rofpalys_queue as Q
import rofpalys_sleep as SL
import rofpalys_stats as ST
try:
    import rofpalys_theme as TH                     # Classic / Modern / Cyberpunk (the colours below are Classic; the theme file replaces them at start)
except Exception:
    TH = None

HOME, CFG = lib.HOME, lib.CONFIG_DIR
GUI_CFG = os.path.join(CFG, "gui.json")
PID_FILE = os.path.join(lib.CACHE_DIR, "gui.pid")
BLK, SIDE, PNL, PNL2, HOVER, ROW_HOVER = "#0b0705", "#120b07", "#1a110b", "#261811", "#33200f", "#21150d"
BRN, BRN2, GOLD, TXT, DIM, RED = "#8b5a2b", "#a96f3a", "#d9a560", "#ead9bd", "#8a7660", "#c0392b"
PALETTE = ["#6f4521", "#8b5a2b", "#a96f3a", "#c68642", "#d9a560", "#e8c58f"]
COVER_SHADES = ["#4a2c14", "#5b361a", "#6b4020", "#3d2511", "#7a4c22", "#52301a"]
OK, WARN, INFO, ACC2, GRID, CARD, CARD2 = "#9bb35c", "#e0a43c", "#7fa6b8", "#c68642", "#33200f", "#261811", "#33200f"       # roles of the newer screens
NOWBG, PH1, PH2, LYR = "#241509", "#3a2414", "#7a4c22", "#b9a48a"                                                                # Now Playing background, cover placeholder, lyrics
STYLE = dict(shape="flat", r=0, btn="flat", chip="flat", nav="bar", icons=False, caps=False, pad=1.0, play="circle", track="flat", track_h=4, knob="dot", knob_r=5, glow=0,
             sep=False, logo="classic", fs=0, dfs=0, ui=("DejaVu Sans",), display=("DejaVu Serif",), mono=("DejaVu Sans Mono",))     # shapes + type of the look (Classic); the theme file replaces it
if TH is not None:
    try:
        TH.apply_to(globals())                      # the whole window is built in the chosen theme
    except Exception:
        pass
ANIMS = ["Bars", "Mirror", "Wave", "Rings", "Rain", "Stars"]
SORTS = ["name", "recent", "plays"]
CHIPS = ("home", "songs", "categories", "folders", "artists", "playlists", "favorites")
ART_BUCKETS = (192, 288, 384, 512, 640)
DEFAULT_CFG = {"geometry": "", "last": {"song": "", "pos": 0}, "stats": {}, "total_sec": 0, "anim_auto": True, "sort": "name",
               "ui": {"view": "library", "chip": "home", "group": ""}}
TXT_ = {
    "en": dict(library="Library", favorites="Favorites", now="Now Playing", visual="Visualizer", settings="Settings", search="Search songs",
               add="Add music folder...", rescan="Rescan library", dl="Download audio (yt-dlp)...", stats="Listening statistics", backup="Backup...",
               restore="Restore...", lang="Language", eng="Audio engine", dj="Auto-DJ", aura="Aura colors", x3="Visual x3", anim="Animations",
               reset="Deep reset...", quit="Quit", sort="Sort", nomusic="Nothing playing", songs="songs", scanning="Scanning music folders...",
               empty="No songs yet  -  open  Menu > Add music folder", dlq="YouTube / audio URL:", sure="Reset favorites, lyric cache, statistics and resume position?",
               total="Total listening", played="Songs played", s_art="Cover art", s_video="Music video", s_lyrics="Lyrics", s_cache="Storage",
               auto="Auto-download", local="Local only", off="Off", panel="Side panel", caption="Captions", both="Both", prefer="Show video instead of cover art",
               quality="Video quality", maxsize="Max video size", limit="Cache limit", reset_song="Reset art & video of this song", reset_all="Reset ALL art & video",
               refetch="Search again now", used="Used", close="Close", confirm_all="Delete every downloaded cover and video from the cache?\n(Your own songs and pictures are never deleted.)",
               done="Done", other="Other", noart="No cover yet", loading="Looking for cover...", lyr_none="No lyrics yet",
               home="Home", songs_chip="Songs", categories="Categories", folders="Folders", search_ph="What do you want to play?", top_result="Top result",
               songs_h="Songs", folders_h="Folders & categories", more_like="More like %s", recent="Continue listening", mix="Made for you",
               favorites_h="Your favorites", top="Most played", new="Recently added", discover="Discover", play="Play", shuffle="Shuffle",
               did_you_mean="Did you mean: %s ?", no_results="No results", search_results="Search results", category="Category", folder="Folder",
               empty_fav="No favorites yet - tap the heart on a song"),
    "id": dict(library="Pustaka", favorites="Favorit", now="Sedang Diputar", visual="Visual", settings="Pengaturan", search="Cari lagu",
               add="Tambah folder musik...", rescan="Pindai ulang", dl="Unduh audio (yt-dlp)...", stats="Statistik mendengar", backup="Cadangkan...",
               restore="Pulihkan...", lang="Bahasa", eng="Mesin audio", dj="Auto-DJ", aura="Warna aura", x3="Visual x3", anim="Animasi",
               reset="Reset total...", quit="Keluar", sort="Urutan", nomusic="Belum ada lagu", songs="lagu", scanning="Memindai folder musik...",
               empty="Belum ada lagu  -  buka  Menu > Tambah folder musik", dlq="URL YouTube / audio:", sure="Reset favorit, cache lirik, statistik, dan posisi terakhir?",
               total="Total mendengar", played="Lagu diputar", s_art="Gambar sampul", s_video="Video klip", s_lyrics="Lirik", s_cache="Penyimpanan",
               auto="Unduh otomatis", local="Hanya lokal", off="Mati", panel="Panel samping", caption="Teks di gambar", both="Keduanya",
               prefer="Tampilkan video menggantikan sampul", quality="Kualitas video", maxsize="Maks. ukuran video", limit="Batas cache",
               reset_song="Reset gambar & video lagu ini", reset_all="Reset SEMUA gambar & video", refetch="Cari ulang sekarang", used="Terpakai", close="Tutup",
               confirm_all="Hapus semua sampul dan video hasil unduhan dari cache?\n(Lagu dan gambar milikmu tidak pernah dihapus.)", done="Selesai", other="Lainnya",
               noart="Belum ada sampul", loading="Mencari sampul...", lyr_none="Belum ada lirik",
               home="Beranda", songs_chip="Lagu", categories="Kategori", folders="Folder", search_ph="Mau putar lagu apa?", top_result="Hasil teratas",
               songs_h="Lagu", folders_h="Folder & kategori", more_like="Mirip %s", recent="Lanjutkan mendengar", mix="Dibuat untukmu",
               favorites_h="Favoritmu", top="Paling sering diputar", new="Baru ditambahkan", discover="Temukan", play="Putar", shuffle="Acak",
               did_you_mean="Maksudmu: %s ?", no_results="Tidak ada hasil", search_results="Hasil pencarian", category="Kategori", folder="Folder",
               empty_fav="Belum ada favorit - ketuk hati pada lagu"),
}

TXT_["en"].update(dict(
    sleep="Sleep timer", sleep_dur="Timer (the song repeats until the time is over)", sleep_until="Until a clock time", sleep_zone="Time zone",
    sleep_hint="02.00 = 2 hours   ·   45 = 45 minutes   ·   1h30", sleep_start="Start", sleep_stop="Stop the timer", sleep_now="Now",
    sleep_ends="stops at", sleep_in="in", sleep_bad="Type a time like 02.00 (2 hours), 45 (minutes) or 00:00", sleep_inactive="No timer is running.",
    sleep_active="Running", sleep_finish="When the time is up", sleep_cut="Stop right away", sleep_end="Let the song finish", clock_hint="Stop at (24 h clock)",
    lyr_find="Find lyrics", lyr_artist="Artist", lyr_title="Title", lyr_search="Search", lyr_use="Use selected", lyr_yt="YouTube captions",
    lyr_del="Delete saved lyrics and search again", lyr_file="Load from file...", lyr_src="Source", lyr_mode="Lyrics sources", lyr_online="Online + local",
    lyr_local="Local only", lyr_yt_s="YouTube captions as a fallback", lyr_found="found", lyr_none_found="Nothing found - check artist and title",
    view_cover="Cover + lyrics", view_video="Video + lyrics", default_view="Now Playing shows", v_video="Video", v_cover="Cover", no_video="No video for this song",
    sure_all="Reset EVERYTHING?\n\nDeleted: favorites, settings, statistics, window state, saved lyrics, downloaded covers and videos, library cache.\n"
             "NOT touched: your songs, your own .lrc files and the audio in Music/ROFPALys.\n\nRofpalys closes afterwards.",
    reset_done="Everything was reset. Open Rofpalys again.", yes="Yes", no="No"))
TXT_["id"].update(dict(
    sleep="Timer tidur", sleep_dur="Timer (lagu diulang sampai waktunya habis)", sleep_until="Sampai jam tertentu", sleep_zone="Zona waktu",
    sleep_hint="02.00 = 2 jam   ·   45 = 45 menit   ·   1j30", sleep_start="Mulai", sleep_stop="Hentikan timer", sleep_now="Sekarang",
    sleep_ends="berhenti jam", sleep_in="dalam", sleep_bad="Ketik waktu seperti 02.00 (2 jam), 45 (menit) atau 00:00", sleep_inactive="Tidak ada timer yang berjalan.",
    sleep_active="Berjalan", sleep_finish="Saat waktu habis", sleep_cut="Berhenti langsung", sleep_end="Biarkan lagu selesai", clock_hint="Berhenti jam (format 24 jam)",
    lyr_find="Cari lirik", lyr_artist="Artis", lyr_title="Judul", lyr_search="Cari", lyr_use="Pakai yang dipilih", lyr_yt="Teks YouTube",
    lyr_del="Hapus lirik tersimpan dan cari ulang", lyr_file="Ambil dari file...", lyr_src="Sumber", lyr_mode="Sumber lirik", lyr_online="Online + lokal",
    lyr_local="Hanya lokal", lyr_yt_s="Teks YouTube sebagai cadangan", lyr_found="ditemukan", lyr_none_found="Tidak ditemukan - cek artis dan judul",
    view_cover="Sampul + lirik", view_video="Video + lirik", default_view="Sedang Diputar menampilkan", v_video="Video", v_cover="Sampul", no_video="Tidak ada video untuk lagu ini",
    sure_all="Reset SEMUANYA?\n\nDihapus: favorit, pengaturan, statistik, kondisi jendela, lirik tersimpan, sampul dan video unduhan, cache pustaka.\n"
             "TIDAK disentuh: lagu-lagumu, file .lrc milikmu, dan audio di Music/ROFPALys.\n\nRofpalys akan menutup setelahnya.",
    reset_done="Semua sudah direset. Buka Rofpalys lagi.", yes="Ya", no="Tidak"))

TXT_["en"].update(dict(
    artists="Artists", playlists="Playlists", artist="Artist", mix_kind="Mix", playlist="Playlist", mixes="Mixes", stats_nav="Statistics", queue="Queue",
    new_playlist="New playlist", name_prompt="Name:", pl_rename="Rename", pl_delete="Delete", pl_export="Export .m3u", pl_import="Import playlist (.m3u)...",
    add_to_pl="Add to playlist", new_pl_with="New playlist...", remove_from_pl="Remove from this playlist", move_up="Move up", move_down="Move down",
    add_queue="Add to queue", play_next="Play next", queue_now="Now playing", queue_next="Next in queue", queue_ctx="Next from your list", queue_hist="Recently played",
    queue_clear="Clear queue", pl_empty="This playlist is empty - right-click a song > Add to playlist", stats_title="Your listening", st_total="Total listening",
    st_week="Last 7 days", st_songs="Songs played", st_streak="Day streak", st_days="Last 14 days (minutes per day)", st_top_songs="Top songs", st_top_artists="Top artists",
    st_none="Nothing yet - play some music and come back", fx="Sound effects", fx_preset="Preset", fx_speed="Speed", fx_reverb="Reverb", fx_norm="Even out the volume",
    fx_note="Effects work with mpv and ffplay (player in use: %s). Slowed and Nightcore also change the pitch, like a tape.", fx_normal="Normal", fx_bass="Bass", fx_vocal="Vocal",
    fx_treble="Treble", fx_lofi="Lo-fi", fx_slowed="Slowed", fx_nightcore="Nightcore", fx_light="Light", fx_hall="Hall", alarm="Wake-up alarm", alarm_time="Ring at (24 h clock)",
    alarm_play="What to play", alarm_song="This song", alarm_pl="A playlist", alarm_rep="Repeat", alarm_once="Once", alarm_daily="Every day", alarm_week="Mon-Fri",
    alarm_set="Set alarm", alarm_none="No alarms yet.", alarm_need_song="Play a song first, or choose a playlist below.",
    alarm_hint="Rofpalys must be running at that time (Termux: run termux-wake-lock, or start  rofpalys daemon).", notify="Notification buttons (Termux)",
    fade="Fade the volume out at the end", on="On", added="Added", fx_eq="Equalizer",
    sel_mode="Select songs...", sel_count="%d selected", sel_all="Select all", sel_done="Done", add_all_to_pl="Add all to playlist", add_all_queue="Add all to queue",
    play_all="Play all", pl_dup="Duplicate", pl_save_page="Save these songs as a playlist", pl_save_queue="Save queue as playlist", pl_added_n="%d song(s) added",
    pl_made_n="Playlist created with %d song(s)", pl_nothing="Nothing selected", shortcuts="Keyboard shortcuts", close_ok="Close",
    shortcuts_text="Space  play / pause\nN / P  next / previous\n← / →  seek 10 s\nL  favorite\nM  play mode\nZ  Now Playing\nC  visualizer\nA  next animation\nCtrl+F  search\n?  this help",
    features="Features loaded", feat_failed="could not load"))
TXT_["id"].update(dict(
    artists="Artis", playlists="Playlist", artist="Artis", mix_kind="Mix", playlist="Playlist", mixes="Mix", stats_nav="Statistik", queue="Antrean",
    new_playlist="Playlist baru", name_prompt="Nama:", pl_rename="Ganti nama", pl_delete="Hapus", pl_export="Ekspor .m3u", pl_import="Impor playlist (.m3u)...",
    add_to_pl="Tambah ke playlist", new_pl_with="Playlist baru...", remove_from_pl="Hapus dari playlist ini", move_up="Naikkan", move_down="Turunkan",
    add_queue="Tambah ke antrean", play_next="Putar berikutnya", queue_now="Sedang diputar", queue_next="Selanjutnya di antrean", queue_ctx="Selanjutnya dari daftarmu",
    queue_hist="Baru diputar", queue_clear="Kosongkan antrean", pl_empty="Playlist ini kosong - klik kanan lagu > Tambah ke playlist", stats_title="Yang kamu dengarkan",
    st_total="Total mendengar", st_week="7 hari terakhir", st_songs="Lagu diputar", st_streak="Hari beruntun", st_days="14 hari terakhir (menit per hari)",
    st_top_songs="Lagu teratas", st_top_artists="Artis teratas", st_none="Belum ada - putar musik dulu lalu kembali ke sini", fx="Efek suara", fx_preset="Preset",
    fx_speed="Kecepatan", fx_reverb="Gema", fx_norm="Ratakan volume", fx_note="Efek jalan dengan mpv dan ffplay (pemutar dipakai: %s). Slowed dan Nightcore juga mengubah nada, seperti kaset.",
    fx_normal="Normal", fx_bass="Bass", fx_vocal="Vokal", fx_treble="Treble", fx_lofi="Lo-fi", fx_slowed="Slowed", fx_nightcore="Nightcore", fx_light="Ringan", fx_hall="Aula",
    alarm="Alarm bangun tidur", alarm_time="Berbunyi jam (format 24 jam)", alarm_play="Yang diputar", alarm_song="Lagu ini", alarm_pl="Sebuah playlist", alarm_rep="Ulangi",
    alarm_once="Sekali", alarm_daily="Setiap hari", alarm_week="Senin-Jumat", alarm_set="Pasang alarm", alarm_none="Belum ada alarm.",
    alarm_need_song="Putar lagu dulu, atau pilih playlist di bawah.", alarm_hint="Rofpalys harus sedang berjalan saat itu (Termux: jalankan termux-wake-lock, atau mulai  rofpalys daemon).",
    notify="Tombol di notifikasi (Termux)", fade="Volume mengecil pelan di akhir", on="Hidup", added="Ditambahkan", fx_eq="Equalizer",
    sel_mode="Pilih lagu...", sel_count="%d dipilih", sel_all="Pilih semua", sel_done="Selesai", add_all_to_pl="Tambahkan semua ke playlist", add_all_queue="Tambahkan semua ke antrean",
    play_all="Putar semua", pl_dup="Gandakan", pl_save_page="Simpan lagu-lagu ini sebagai playlist", pl_save_queue="Simpan antrean sebagai playlist", pl_added_n="%d lagu ditambahkan",
    pl_made_n="Playlist dibuat dengan %d lagu", pl_nothing="Belum ada yang dipilih", shortcuts="Pintasan keyboard", close_ok="Tutup",
    shortcuts_text="Spasi  putar / jeda\nN / P  berikut / sebelumnya\n← / →  geser 10 detik\nL  favorit\nM  mode putar\nZ  Sedang Diputar\nC  visualizer\nA  animasi berikut\nCtrl+F  cari\n?  bantuan ini",
    features="Fitur yang dimuat", feat_failed="gagal dimuat"))


TXT_["en"].update(dict(
    ck_title="CyroKayAI - exact lyric sync", ck_auto="Find and sync automatically", ck_melody="Melody only", ck_working="CyroKayAI is working...",
    ck_none="No result for this song yet. Press the button: it checks who made the song, checks the internet, listens to the song and fits the lyrics to the voice.",
    ck_skip="Skip the extra music part so the lyrics fit (only if a cut plan exists)", ck_fit_note="Lyrics you pick are fitted to the real recording first.",
    ck_st_creator="Checking who made the song...", ck_st_internet="Checking the internet...", ck_st_fetch="Looking for lyrics...", ck_st_listen="Listening to the song...",
    ck_st_providers="Asking syncedlyrics, lrcdl, lyriq, librelyrics...", ck_st_fit="Fitting the lyrics to the voice...", ck_missing="CyroKayAI file (rofpalys_CyroKayAI_lyric.py) is not installed - run: python ~/rofpalys.py install",
    ck_nosong="Play a song first.", ck_fitted="Fitted to the music"))
TXT_["id"].update(dict(
    ck_title="CyroKayAI - sinkron lirik presisi", ck_auto="Cari dan sinkronkan otomatis", ck_melody="Hanya melodi", ck_working="CyroKayAI sedang bekerja...",
    ck_none="Belum ada hasil untuk lagu ini. Tekan tombolnya: ia mengecek pembuat lagu, mengecek internet, mendengarkan lagu, lalu mencocokkan lirik dengan suara.",
    ck_skip="Lewati bagian musik berlebih agar lirik pas (hanya jika ada rencana potong)", ck_fit_note="Lirik yang kamu pilih dicocokkan dulu dengan rekaman aslinya.",
    ck_st_creator="Mengecek siapa pembuat lagu...", ck_st_internet="Mengecek internet...", ck_st_fetch="Mencari lirik...", ck_st_listen="Mendengarkan lagu...",
    ck_st_providers="Menanyakan syncedlyrics, lrcdl, lyriq, librelyrics...", ck_st_fit="Mencocokkan lirik dengan suara...", ck_missing="File CyroKayAI (rofpalys_CyroKayAI_lyric.py) belum terpasang - jalankan: python ~/rofpalys.py install",
    ck_nosong="Putar lagu dulu.", ck_fitted="Dicocokkan dengan musik"))


def emoji_ok():
    """Can this Tk draw colour emoji (the 🎶 / 🎵 melody markers) safely? Windows and macOS: yes. Linux: only Tk >= 8.6.10 (older Tk can crash on emoji).
    ROFPALYS_NOTES=emoji or =text overrides the check."""
    forced = os.environ.get("ROFPALYS_NOTES", "").lower()
    if forced in ("emoji", "text"):
        return forced == "emoji"
    if sys.platform in ("win32", "darwin"):
        return True
    try:
        ver = tk.Tcl().eval("info patchlevel")
        return tuple(int(x) for x in ver.split(".")[:3]) >= (8, 6, 10)
    except Exception:
        return False


def log(msg):
    try:
        os.makedirs(lib.CACHE_DIR, exist_ok=True)
        with open(os.path.join(lib.CACHE_DIR, "gui.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except OSError:
        pass


def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))


def hms(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60) if sec >= 3600 else "%d:%02d" % (sec // 60, sec % 60)


# ------------------------------------------------------------------ icons are drawn with shapes, so they never depend on a font having the symbol
def draw_icon(cv, kind, cx, cy, s, color):
    r = s / 2.0
    fl = {"fill": color, "outline": ""}
    ln = {"fill": color, "width": max(2, int(s / 10.0))}
    if kind == "play":
        cv.create_polygon(cx - r * .55, cy - r, cx - r * .55, cy + r, cx + r * .9, cy, **fl)
    elif kind == "pause":
        cv.create_rectangle(cx - r * .7, cy - r, cx - r * .15, cy + r, **fl)
        cv.create_rectangle(cx + r * .15, cy - r, cx + r * .7, cy + r, **fl)
    elif kind == "next":
        cv.create_polygon(cx - r * .9, cy - r * .8, cx - r * .9, cy + r * .8, cx + r * .5, cy, **fl)
        cv.create_rectangle(cx + r * .6, cy - r * .8, cx + r * .95, cy + r * .8, **fl)
    elif kind == "prev":
        cv.create_polygon(cx + r * .9, cy - r * .8, cx + r * .9, cy + r * .8, cx - r * .5, cy, **fl)
        cv.create_rectangle(cx - r * .95, cy - r * .8, cx - r * .6, cy + r * .8, **fl)
    elif kind in ("heart", "heart_on"):
        pts = [cx, cy + r * .95, cx - r * 1.15, cy - r * .05, cx - r * .65, cy - r * .9, cx, cy - r * .4, cx + r * .65, cy - r * .9, cx + r * 1.15, cy - r * .05]
        if kind == "heart_on":
            cv.create_polygon(pts, smooth=True, fill=color, outline=color)
        else:
            cv.create_polygon(pts, smooth=True, fill="", outline=color, width=2)
    elif kind == "shuffle":
        cv.create_line(cx - r, cy + r * .5, cx - r * .15, cy + r * .5, cx + r * .45, cy - r * .5, cx + r * .75, cy - r * .5, **ln)
        cv.create_line(cx - r, cy - r * .5, cx - r * .15, cy - r * .5, cx + r * .45, cy + r * .5, cx + r * .75, cy + r * .5, **ln)
        cv.create_polygon(cx + r * .7, cy - r, cx + r, cy - r * .5, cx + r * .7, cy, **fl)
        cv.create_polygon(cx + r * .7, cy, cx + r, cy + r * .5, cx + r * .7, cy + r, **fl)
    elif kind in ("repeat", "repeat1"):
        cv.create_line(cx - r * .9, cy + r * .1, cx - r * .9, cy - r * .5, cx + r * .6, cy - r * .5, **ln)
        cv.create_line(cx + r * .9, cy - r * .1, cx + r * .9, cy + r * .5, cx - r * .6, cy + r * .5, **ln)
        cv.create_polygon(cx + r * .45, cy - r * .95, cx + r * .95, cy - r * .5, cx + r * .45, cy - r * .05, **fl)
        cv.create_polygon(cx - r * .45, cy + r * .05, cx - r * .95, cy + r * .5, cx - r * .45, cy + r * .95, **fl)
        if kind == "repeat1":
            cv.create_text(cx, cy, text="1", fill=color, font=("DejaVu Sans", max(6, int(s / 3.2)), "bold"))
    elif kind in ("arrow", "arrow2"):
        for dy in ((-r * .45, r * .45) if kind == "arrow2" else (0,)):
            cv.create_line(cx - r, cy + dy, cx + r * .6, cy + dy, **ln)
            cv.create_polygon(cx + r * .3, cy + dy - r * .4, cx + r, cy + dy, cx + r * .3, cy + dy + r * .4, **fl)
    elif kind == "volume":
        cv.create_polygon(cx - r, cy - r * .35, cx - r * .5, cy - r * .35, cx, cy - r * .85, cx, cy + r * .85, cx - r * .5, cy + r * .35, cx - r, cy + r * .35, **fl)
        cv.create_arc(cx - r * .2, cy - r * .55, cx + r * .6, cy + r * .55, start=-50, extent=100, style="arc", outline=color, width=2)
        cv.create_arc(cx - r * .2, cy - r * .95, cx + r * 1.0, cy + r * .95, start=-50, extent=100, style="arc", outline=color, width=2)
    elif kind == "expand":
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            cv.create_line(cx + sx * r, cy + sy * r * .35, cx + sx * r, cy + sy * r, cx + sx * r * .35, cy + sy * r, **ln)
    elif kind == "back":
        cv.create_line(cx + r * .4, cy - r, cx - r * .5, cy, cx + r * .4, cy + r, **ln)
    elif kind == "chev":
        cv.create_line(cx - r * .4, cy - r, cx + r * .5, cy, cx - r * .4, cy + r, **ln)
    elif kind == "search":
        cv.create_oval(cx - r, cy - r, cx + r * .3, cy + r * .3, outline=color, width=2)
        cv.create_line(cx + r * .2, cy + r * .2, cx + r, cy + r, **ln)
    elif kind == "folder":
        cv.create_polygon(cx - r, cy - r * .6, cx - r * .3, cy - r * .6, cx, cy - r * .3, cx + r, cy - r * .3, cx + r, cy + r * .75, cx - r, cy + r * .75, **fl)
    elif kind == "note":
        cv.create_oval(cx - r * .8, cy + r * .1, cx, cy + r * .8, **fl)
        cv.create_line(cx - r * .05, cy + r * .45, cx - r * .05, cy - r * .85, **ln)
        cv.create_polygon(cx, cy - r * .85, cx + r * .8, cy - r * .5, cx, cy - r * .2, **fl)
    elif kind == "wave":
        for i, hh in enumerate((.4, .9, .6, 1.0, .5)):
            x = cx - r * .8 + i * r * .4
            cv.create_rectangle(x - r * .1, cy - r * hh, x + r * .1, cy + r * hh, **fl)
    elif kind == "headphones":
        cv.create_arc(cx - r, cy - r * .95, cx + r, cy + r * .95, start=0, extent=180, style="arc", outline=color, width=max(2, int(s / 9.0)))
        cv.create_rectangle(cx - r * 1.05, cy - r * .05, cx - r * .5, cy + r * .85, **fl)
        cv.create_rectangle(cx + r * .5, cy - r * .05, cx + r * 1.05, cy + r * .85, **fl)
    elif kind == "video":
        cv.create_rectangle(cx - r, cy - r * .7, cx + r, cy + r * .7, outline=color, width=2)
        cv.create_polygon(cx - r * .25, cy - r * .35, cx - r * .25, cy + r * .35, cx + r * .4, cy, **fl)
    elif kind == "moon":
        cv.create_oval(cx - r * .85, cy - r * .85, cx + r * .85, cy + r * .85, **fl)
        cv.create_oval(cx - r * .2, cy - r * 1.05, cx + r * 1.3, cy + r * .55, fill=cv.cget("bg"), outline="")
    elif kind == "lyrics":
        for k, wd in enumerate((1.0, 0.7, 0.9, 0.5)):
            y = cy - r * .75 + k * r * .5
            cv.create_line(cx - r * wd, y, cx + r * wd, y, **ln)
    elif kind == "queue":
        for k, y in enumerate((-.7, -.2, .3)):
            cv.create_line(cx - r, cy + y * r, cx + r * (.2 if k < 2 else -.2), cy + y * r, **ln)
        cv.create_polygon(cx + r * .35, cy + r * .0, cx + r * .35, cy + r * .9, cx + r * 1.0, cy + r * .45, **fl)
    elif kind == "equalizer":
        for k, x in enumerate((-.6, 0, .6)):
            cv.create_line(cx + x * r, cy - r, cx + x * r, cy + r, **ln)
            cv.create_rectangle(cx + x * r - r * .22, cy + (k - 1) * r * .5 - r * .14, cx + x * r + r * .22, cy + (k - 1) * r * .5 + r * .14, **fl)
    elif kind == "palette":
        cv.create_oval(cx - r, cy - r * .9, cx + r, cy + r * .9, outline=color, width=max(2, int(s / 8.0)))
        for dx, dy in ((-.45, -.3), (.05, -.5), (.5, -.1), (-.3, .3)):
            cv.create_oval(cx + dx * r - r * .17, cy + dy * r - r * .17, cx + dx * r + r * .17, cy + dy * r + r * .17, fill=color, outline=color)
    elif kind == "stats":
        for k, hh in enumerate((.5, 1.0, .75)):
            x = cx - r * .7 + k * r * .7
            cv.create_rectangle(x - r * .2, cy + r - r * 2 * hh, x + r * .2, cy + r, **fl)
    elif kind == "ab":
        cv.create_text(cx, cy, text="A-B", fill=color, font=("DejaVu Sans", max(7, int(s / 2.3)), "bold"))
    elif kind == "plus":
        cv.create_line(cx - r * .7, cy, cx + r * .7, cy, **ln)
        cv.create_line(cx, cy - r * .7, cx, cy + r * .7, **ln)
    elif kind == "gear":
        cv.create_oval(cx - r * .55, cy - r * .55, cx + r * .55, cy + r * .55, outline=color, width=max(2, int(s / 6.0)))
        for a in range(0, 360, 45):
            x, y = math.cos(math.radians(a)), math.sin(math.radians(a))
            cv.create_line(cx + x * r * .7, cy + y * r * .7, cx + x * r, cy + y * r, **ln)


_ICONS = []                                          # every icon button that exists (so a theme switch can give them the new colours)


class IconBtn:
    """A small clickable icon (a canvas). Hover turns it gold."""

    def __init__(self, parent, kind, cmd, size=22, color=None, hover=None, bg=None, pad=8):
        color, hover, bg = color or DIM, hover or GOLD, bg or SIDE            # looked up now (not when the program started): a theme switch changes them
        self.kind, self.color, self.hover_c, self.size, self.cmd, self.cur = kind, color, hover, size, cmd, color
        _ICONS[:] = [w for w in _ICONS if w() is not None] + [__import__("weakref").ref(self)]
        self.d = size + pad * 2
        self.hov = False
        self.cv = tk.Canvas(parent, width=self.d, height=self.d, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.bind("<Button-1>", lambda e: self.cmd())
        self.cv.bind("<Enter>", lambda e: self._over(True))
        self.cv.bind("<Leave>", lambda e: self._over(False))
        self.paint(color)

    def _over(self, on):
        self.hov = on
        self.paint(self.hover_c if on else self.color)

    def paint(self, col=None):
        self.cur = col or self.cur
        self.cv.delete("all")
        if self.hov and STYLE["shape"] != "flat":                      # the rounded / cut looks light a plate behind the icon
            d = self.d
            if STYLE["shape"] == "round":
                self.cv.create_oval(2, 2, d - 2, d - 2, fill=HOVER, outline="")
            else:
                draw_shape(self.cv, 2, 2, d - 2, d - 2, fill=HOVER, outline=BRN2, shape="cut", r=7)
        draw_icon(self.cv, self.kind, self.d / 2.0, self.d / 2.0, self.size, self.cur)

    def set(self, kind=None, color=None):
        if (kind and kind != self.kind) or (color and color != self.color):
            self.kind, self.color = kind or self.kind, color or self.color
            self.paint(self.color)

    def pack(self, **kw):
        self.cv.pack(**kw)

    def forget(self):
        self.cv.pack_forget()


def _icons_follow_theme(old, new, mapper):
    """After a theme switch: the colours an icon remembers (normal / hover / current) become the new theme's, then it is drawn again."""
    for ref in list(_ICONS):
        w = ref()
        if w is None:
            continue
        try:
            w.color, w.hover_c, w.cur = mapper(w.color) or w.color, mapper(w.hover_c) or w.hover_c, mapper(w.cur) or w.cur
            w.paint(w.cur)
        except Exception:
            pass


if TH is not None:
    TH.on_switch(_icons_follow_theme)


# ------------------------------------------------------------------ SHAPES and TYPE of the look in use (rofpalys_theme.STYLES): square / rounded / cut corners, drawn buttons, bars, fonts
def cap(s):
    """CAPITAL LETTERS when the look asks for them (Cyberpunk), the text as it is otherwise."""
    return str(s).upper() if STYLE.get("caps") else s


_FAMS = {}


def pick_family(cands, root=None):
    """The first font family of the list that is installed (the last one when none is: Tk then substitutes, as it always did)."""
    key = tuple(cands)
    if key in _FAMS:
        return _FAMS[key]
    try:
        have = {f.lower(): f for f in tkfont.families(root)}
    except Exception:
        have = {}
    out = next((have[c.lower()] for c in cands if c.lower() in have), None) or cands[-1]
    _FAMS[key] = out
    return out


def look_fonts(root, fs):
    """The font tuples of the window for the look in use. Classic gives exactly what the window always used."""
    st = STYLE
    ui, disp, mono = (pick_family(st[k], root) for k in ("ui", "display", "mono"))
    fs = max(9, fs + st["fs"]) if st["fs"] else fs
    ds = fs + 4 + st["dfs"]
    return {"ui": (ui, fs), "mono": (mono, fs), "nav": (ui, fs + 1, "bold"), "big": (disp, ds, "bold"), "title": (ui, fs + 1, "bold"), "small": (ui, max(8, fs - 2)),
            "head": (ui, fs + 3, "bold"), "ui_b": (ui, fs, "bold"), "display": disp}


_FOBJ = {}


def font_obj(f):
    """A tkfont.Font for a font tuple / name (kept, so measuring is cheap)."""
    k = (id(getattr(tk, "_default_root", None)), f if isinstance(f, str) else tuple(f))
    o = _FOBJ.get(k)
    if o is None:
        try:
            o = tkfont.Font(font=f)
        except Exception:
            o = tkfont.Font(family="DejaVu Sans", size=10)
        _FOBJ[k] = o
    return o


def shape_pts(x1, y1, x2, y2, shape, r):
    """(points, smooth) of a polygon with square, round, pill (fully round ends) or cut (chamfered top-left and bottom-right) corners."""
    w, h = x2 - x1, y2 - y1
    if shape in ("round", "pill"):
        r = h / 2.0 if shape == "pill" else r
        r = max(0, min(r, w / 2.0, h / 2.0))
        if r >= 1:
            return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1], True
    elif shape == "cut":
        c = max(0, min(r, w / 2.0, h / 2.0))
        if c >= 1:
            return [x1 + c, y1, x2, y1, x2, y2 - c, x2 - c, y2, x1, y2, x1, y1 + c], False
    return [x1, y1, x2, y1, x2, y2, x1, y2], False


def draw_shape(cv, x1, y1, x2, y2, fill="", outline="", shape=None, r=None, width=1, tags=()):
    """A rectangle in the corner form of the look in use (or of `shape`)."""
    shape = STYLE["shape"] if shape is None else shape
    r = STYLE["r"] if r is None else r
    if shape == "flat" or (shape in ("round", "cut") and r < 1):
        return cv.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width, tags=tags)
    pts, smooth = shape_pts(x1, y1, x2, y2, shape, r)
    return cv.create_polygon(pts, smooth=smooth, fill=fill, outline=outline, width=width, tags=tags)


def neon(cv, x1, y1, x2, y2, color, under, shape=None, r=None, level=None, width=2, tags=()):
    """A glowing outline: a dim halo outside (level 2) and the bright line (level 1 and 2)."""
    level = STYLE["glow"] if level is None else level
    if level >= 2:
        draw_shape(cv, x1 - 2, y1 - 2, x2 + 2, y2 + 2, outline=lerp(color, under, 0.72), shape=shape, r=r, width=1, tags=tags)
    if level >= 1:
        draw_shape(cv, x1, y1, x2, y2, outline=color, shape=shape, r=r, width=width, tags=tags)


class ShapeLabel(tk.Canvas if tk else object):
    """A Label that draws its own body, so it can have rounded or cut corners, a neon outline, an icon in front and capital letters. It answers the calls of a tk.Label
    (configure text / bg / fg / font, cget, pack, bind, cursor) so the code that made Labels works unchanged. bg = the colour of the BODY; pbg = what is behind the
    corners (default: the parent's colour). outline: "" none, "auto" = a neon line when the look glows, or a colour. accent: a 3 px bar at the left edge."""
    _OPTS = ("text", "fg", "bg", "font", "padx", "pady", "anchor", "shape", "r", "outline", "icon", "accent", "caps", "ow", "chars")
    _ALIAS = {"foreground": "fg", "background": "bg", "width": "chars"}
    _IGNORE = ("state", "relief", "bd", "borderwidth", "justify", "wraplength", "compound", "image", "underline", "takefocus", "activeforeground", "disabledforeground",
               "highlightthickness", "highlightbackground", "highlightcolor", "textvariable", "height", "activebackground", "overrelief", "bitmap")

    def __init__(self, parent, text="", bg=None, fg=None, font=None, padx=12, pady=5, anchor="center", shape=None, r=None, outline="auto", icon=None, accent="",
                 caps=None, cursor="", pbg=None, **kw):
        try:
            pb = pbg or parent.cget("bg")
        except Exception:
            pb = PNL
        super().__init__(parent, bg=pb, highlightthickness=0, bd=0, cursor=cursor)
        self._pbg, self._job, self._hov = pb, None, False
        self._s = dict(text=text, bg=bg or PNL2, fg=fg or TXT, font=font or ("DejaVu Sans", 10), padx=padx, pady=pady, anchor=anchor, shape=shape or STYLE["btn"], r=r,
                       outline=outline, icon=icon, accent=accent, caps=STYLE["caps"] if caps is None else caps, ow=1, chars=0)
        for k, v in kw.items():
            self._set(k, v)
        self.bind("<Configure>", lambda e: self._later(), add="+")
        self.bind("<Enter>", lambda e: self._hover(True), add="+")
        self.bind("<Leave>", lambda e: self._hover(False), add="+")
        self._fit()

    # ---- the Label calls
    def _set(self, k, v):
        k = self._ALIAS.get(k, k)
        if k in self._OPTS:
            self._s[k] = v
            return True
        if k == "pbg":
            self._pbg = v
            tk.Canvas.configure(self, bg=v)
            return True
        if k in self._IGNORE:
            return False
        try:
            tk.Canvas.configure(self, **{k: v})
        except Exception:
            pass
        return False

    def configure(self, cnf=None, **kw):
        if cnf:
            kw = dict(cnf, **kw)
        if not kw:
            return tk.Canvas.configure(self)
        for k, v in kw.items():
            self._set(k, v)
        self._fit()
        return None

    config = configure

    def bind(self, sequence=None, func=None, add=None):
        """Like Misc.bind, except that <Enter> and <Leave> always ADD to the binding: the window's own code binds them for hover colours (replacing what was there),
        and this widget needs its own hover tracking (neon outline) to survive that."""
        if sequence in ("<Enter>", "<Leave>") and func is not None:
            add = "+"
        return tk.Canvas.bind(self, sequence, func, add)

    def cget(self, key):
        key = self._ALIAS.get(key, key)
        if key in self._OPTS:
            return self._s[key]
        if key in ("pbg",):
            return self._pbg
        try:
            return tk.Canvas.cget(self, key)
        except Exception:
            return ""

    def retint(self, mapper):
        """A theme switch while this widget is open: its remembered colours become the new theme's."""
        for k in ("bg", "fg", "outline", "accent"):
            v = self._s.get(k)
            n = mapper(v) if isinstance(v, str) and v.startswith("#") else None
            if n:
                self._s[k] = n
        n = mapper(self._pbg)
        if n:
            self._pbg = n
            tk.Canvas.configure(self, bg=n)
        self._later()

    # ---- size and drawing
    def _text(self):
        t = str(self._s["text"]).strip() if (self._s["icon"] or self._s["shape"] != "flat") else str(self._s["text"])
        return t.upper() if self._s["caps"] else t

    def _fit(self):
        s = self._s
        f = font_obj(s["font"])
        icon = (f.metrics("linespace") - 2 + 8) if s["icon"] else 0
        w = int(f.measure(self._text())) + 2 * int(s["padx"]) + icon + 2
        if s["chars"]:
            w = max(w, int(f.measure("0") * s["chars"]) + 2 * int(s["padx"]) + 2)
        h = int(f.metrics("linespace")) + 2 * int(s["pady"]) + 2
        tk.Canvas.configure(self, width=w, height=h)
        self._later()

    def _later(self):
        if self._job is None:
            try:
                self._job = self.after_idle(self._draw)
            except Exception:
                self._job = None

    def _hover(self, on):
        self._hov = on
        self._later()

    def _draw(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
            s = self._s
            w, h = max(int(self.winfo_width()), 2), max(int(self.winfo_height()), 2)
            if w < 12:
                w, h = int(self.winfo_reqwidth()), int(self.winfo_reqheight())
            self.delete("all")
            f = font_obj(s["font"])
            under, fill, shape = self._pbg, s["bg"], s["shape"]
            r = s["r"] if s["r"] is not None else STYLE["r"]
            out = s["outline"]
            if out == "auto":
                out = (INFO if self._hov else lerp(fill, BRN2, 0.55)) if (STYLE["glow"] and fill != under) else ""
            if fill != under or out:
                if shape == "flat":
                    self.create_rectangle(0, 0, w - 1, h - 1, fill=fill, outline=out or "")
                else:
                    draw_shape(self, 1, 1, w - 2, h - 2, fill=fill, outline=out or "", shape=shape, r=r, width=1)
                    if out and STYLE["glow"] >= 2:
                        draw_shape(self, 0, 0, w - 1, h - 1, outline=lerp(out, under, 0.7), shape=shape, r=r, width=1)
            if s["accent"]:
                self.create_rectangle(0, 3, 3, h - 3, fill=s["accent"], outline="")
                if STYLE["glow"]:
                    self.create_rectangle(3, 5, 5, h - 5, fill=lerp(s["accent"], fill, 0.7), outline="")
            x = int(s["padx"]) + (3 if s["accent"] else 0)
            if s["icon"]:
                isz = max(12, f.metrics("linespace") - 4)
                draw_icon(self, s["icon"], x + isz / 2.0, h / 2.0, isz, s["fg"])
                x += isz + 8
            if s["anchor"] in ("w", "nw", "sw"):
                self.create_text(x, h / 2.0, text=self._text(), fill=s["fg"], font=s["font"], anchor="w")
            else:
                self.create_text(w / 2.0, h / 2.0, text=self._text(), fill=s["fg"], font=s["font"], anchor="center")
        except Exception as e:
            log("ShapeLabel: %r" % (e,))


class Box(tk.Canvas if tk else object):
    """A rounded / cut panel that holds ONE widget group in .inner (the search field sits in one). The body follows the look in use; focus_ring() lights its outline."""

    def __init__(self, parent, fill=None, outline="", shape=None, r=None, padx=10, pady=3, left=0, pbg=None):
        try:
            pb = pbg or parent.cget("bg")
        except Exception:
            pb = PNL
        super().__init__(parent, bg=pb, highlightthickness=0, bd=0)
        self.fill, self.outline, self.shape, self.r, self.px, self.py, self.left, self.pbg = fill or PNL2, outline, shape or STYLE["btn"], r, padx, pady, left, pb
        self.inner = tk.Frame(self, bg=self.fill)
        self.win = self.create_window(padx + left, pady, window=self.inner, anchor="nw")
        self.icon = None
        self.bind("<Configure>", lambda e: self.layout())
        self.inner.bind("<Configure>", lambda e: self.need())

    def need(self):
        h = self.inner.winfo_reqheight() + 2 * self.py
        if abs(int(self.winfo_reqheight()) - h) > 1:
            self.configure(height=h)

    def layout(self):
        w, h = int(self.winfo_width()), int(self.winfo_height())
        if w < 12 or h < 8:
            return
        for i in getattr(self, "_mine", ()):
            self.delete(i)
        before = set(self.find_all())
        r = self.r if self.r is not None else STYLE["r"]
        draw_shape(self, 1, 1, w - 2, h - 2, fill=self.fill, outline=self.outline, shape=self.shape, r=r)
        if self.icon:
            draw_icon(self, "search", self.px + 9, h / 2.0, 14, self.icon)
        self._mine = [i for i in self.find_all() if i not in before]
        for i in reversed(self._mine):                                   # the body and the icon go below the field, keeping their own order
            self.tag_lower(i)
        self.coords(self.win, self.px + self.left, self.py)
        self.itemconfigure(self.win, width=max(10, w - 2 * self.px - self.left), height=max(8, h - 2 * self.py))

    def set_outline(self, color):
        self.outline = color
        self.layout()

    def focus_ring(self, widget, on, off=""):
        widget.bind("<FocusIn>", lambda e: self.set_outline(on), add="+")
        widget.bind("<FocusOut>", lambda e: self.set_outline(off), add="+")

    def retint(self, mapper):
        for k in ("fill", "outline", "pbg", "icon"):
            v = getattr(self, k, None)
            n = mapper(v) if isinstance(v, str) and v.startswith("#") else None
            if n:
                setattr(self, k, n)
        try:
            self.inner.configure(bg=self.fill)
            tk.Canvas.configure(self, bg=self.pbg)
        except Exception:
            pass
        self.layout()


def paint_track(c, x1, x2, cy, x, knob=True):
    """The progress / volume bar in the look in use. x = where the handle is (x1..x2). Classic draws exactly what the window always drew."""
    st = STYLE
    kind, th = st["track"], st["track_h"]
    frac = 0.0 if x2 <= x1 else max(0.0, min(1.0, (x - x1) / float(x2 - x1)))
    if kind == "flat":
        c.create_rectangle(x1, cy - 2, x2, cy + 2, fill=PNL2, outline="")
        if knob:
            c.create_rectangle(x1, cy - 2, x, cy + 2, fill=GOLD, outline="")
            c.create_oval(x - 5, cy - 5, x + 5, cy + 5, fill=TXT, outline="")
        return
    if kind == "round":
        c.create_polygon(shape_pts(x1, cy - th / 2.0, x2, cy + th / 2.0, "pill", 0)[0], smooth=True, fill=GRID, outline="")
        if knob and x - x1 >= 1:
            c.create_polygon(shape_pts(x1, cy - th / 2.0, max(x, x1 + th), cy + th / 2.0, "pill", 0)[0], smooth=True, fill=GOLD, outline="")
        if knob:
            k = st["knob_r"]
            c.create_oval(x - k, cy - k, x + k, cy + k, fill=TXT, outline=lerp(GOLD, SIDE, 0.5), width=2)
        return
    sw, gap = 6, 3                                                   # "seg": slanted segments like a level meter
    n = max(4, int((x2 - x1) // (sw + gap)))
    lit = int(round(frac * n))
    hh = th / 2.0 + 1
    for i in range(n):
        sx = x1 + i * (sw + gap)
        on = knob and i < lit
        c.create_polygon(sx, cy + hh, sx + 2, cy - hh, sx + sw + 2, cy - hh, sx + sw, cy + hh, fill=GOLD if on else GRID, outline="")
        if on and i == lit - 1:
            c.create_line(sx, cy + hh + 2, sx + sw, cy + hh + 2, fill=BRN2, width=1)
    if knob:
        k = st["knob_r"]
        c.create_polygon(x, cy - k - 1, x + k, cy, x, cy + k + 1, x - k, cy, fill=TXT, outline=BRN2, width=2)


def paint_play(c, playing, size=44):
    """The round play / pause button of the bottom bar, in the form of the look in use."""
    st = STYLE
    kind = st["play"]
    if kind == "hex":
        cc = 11
        pts = [cc, 2, size - 2, 2, size - 2, size - cc, size - cc, size - 2, 2, size - 2, 2, cc]
        c.create_polygon(pts, fill=BLK, outline=GOLD, width=2)
        ins = [cc + 3, 6, size - 6, 6, size - 6, size - cc - 3, size - cc - 3, size - 6, 6, size - 6, 6, cc + 3]
        c.create_polygon(ins, fill="", outline=BRN2, width=1)
        col = GOLD
    else:
        if kind == "circle" and st["shape"] != "flat":
            c.create_oval(1, 1, size - 1, size - 1, outline=lerp(GOLD, SIDE, 0.6), width=2)
            c.create_oval(4, 4, size - 4, size - 4, fill=GOLD, outline="")
        else:
            c.create_oval(2, 2, size - 2, size - 2, fill=GOLD, outline="")
        col = BLK
    if playing:
        if st["shape"] == "round":
            draw_shape(c, 15, 13, 20, 31, fill=col, shape="round", r=2)
            draw_shape(c, 24, 13, 29, 31, fill=col, shape="round", r=2)
        else:
            c.create_rectangle(15, 13, 20, 31, fill=col, outline="")
            c.create_rectangle(24, 13, 29, 31, fill=col, outline="")
    else:
        c.create_polygon(16, 12, 16, 32, 32, 22, fill=col, outline="")


class Logo:
    """ROFPALYS drawn as text that is re-sized to the width it gets, so it is never cut off - whatever the window size. The form follows the look in use:
    Classic = serif with one line below, Modern = clean letters with a short rounded bar, Cyberpunk = neon letters with a double glowing line."""
    TEXT = "ROFPALYS"

    def __init__(self, parent, height, bg, width=None):
        kw = {"width": width} if width else {}
        self.cv = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0, **kw)
        self.font = tkfont.Font(family=pick_family(STYLE["display"], parent), size=24, weight="bold")
        self.sig = None
        self.cv.bind("<Configure>", lambda e: self.draw())

    def draw(self):
        cv = self.cv
        w, h = int(cv.winfo_width()), int(cv.winfo_height())
        if w < 24 or h < 12 or (w, h) == self.sig:
            return
        self.sig = (w, h)
        size, text = 42, self.TEXT
        while size > 5:
            self.font.configure(size=size)
            if self.font.measure(text) <= w - 18 and self.font.metrics("linespace") <= h - 10:
                break
            size -= 1
        if self.font.measure(text) > w - 18:                  # absurdly narrow: show just the first letter instead of a cut-off word
            text = text[:1]
        cv.delete("all")
        kind = STYLE["logo"]
        if kind == "neon":
            cv.create_text(w // 2 + 2, h // 2 - 2 + 2, text=text, fill=BRN2, font=self.font)
            cv.create_text(w // 2, h // 2 - 2, text=text, fill=GOLD, font=self.font)
            cv.create_line(9, h - 6, w - 9, h - 6, fill=INFO, width=2)
            cv.create_line(9, h - 2, w * 0.55, h - 2, fill=BRN2, width=2)
            cv.create_polygon(w - 9, h - 10, w - 3, h - 6, w - 9, h - 2, w - 15, h - 6, fill=GOLD, outline="")
        elif kind == "modern":
            cv.create_text(w // 2, h // 2 - 2, text=text, fill=TXT, font=self.font)
            cv.create_line(w // 2 - 18, h - 5, w // 2 + 18, h - 5, fill=GOLD, width=4, capstyle="round")
        else:
            cv.create_text(w // 2, h // 2 - 2, text=text, fill=GOLD, font=self.font)
            cv.create_line(9, h - 4, w - 9, h - 4, fill=BRN, width=2)

    def pack(self, **kw):
        self.cv.pack(**kw)

    def forget(self):
        self.cv.pack_forget()


class RowList:
    """Spotify-style list drawn on one canvas: cover + title + subtitle per row. Only the visible rows are drawn, so thousands of songs stay fast."""
    ROW_H, HEAD_H = 58, 46

    def __init__(self, app, parent):
        self.app = app
        self.items, self.offs, self.top, self.sel, self.hover = [], [0], 0, -1, -1
        self.frame = tk.Frame(parent, bg=PNL)
        self.sb = tk.Scrollbar(self.frame, command=self.yview, bg=PNL2, troughcolor=PNL, bd=0, highlightthickness=0, width=10, activebackground=BRN)
        self.sb.pack(side="right", fill="y")
        self.cv = tk.Canvas(self.frame, bg=PNL, highlightthickness=0, takefocus=1)
        self.cv.pack(side="left", fill="both", expand=True)
        for seq, fn in (("<Configure>", lambda e: self.redraw()), ("<Button-1>", self.on_click), ("<Double-Button-1>", self.on_double),
                        ("<Button-3>", self.on_context), ("<Motion>", self.on_motion), ("<Leave>", self.on_leave), ("<MouseWheel>", self.on_wheel),
                        ("<Button-4>", self.on_wheel), ("<Button-5>", self.on_wheel), ("<Up>", lambda e: self.move(-1)), ("<Down>", lambda e: self.move(1)),
                        ("<Prior>", lambda e: self.move(-8)), ("<Next>", lambda e: self.move(8)), ("<Return>", lambda e: self.activate(self.sel))):
            self.cv.bind(seq, fn)
        self.on_activate = self.on_heart = self.on_menu = self.on_select = lambda *a: None
        self.select_mode, self.checked = False, set()      # select mode: check boxes appear, a click ticks a song / a whole group

    # ---- data
    def set_items(self, items):
        self.items, self.offs = items, [0]
        for it in items:
            self.offs.append(self.offs[-1] + (self.HEAD_H if it["kind"] in ("header", "suggest") else self.ROW_H))
        self.top, self.sel, self.hover = 0, -1, -1
        self.redraw()

    @staticmethod
    def key_of(it):
        """What identifies a row in the selection: a song's path or a group's id (None: the row cannot be selected)."""
        return it.get("path") if it["kind"] == "song" else (it.get("gid") if it["kind"] == "group" else None)

    def set_select_mode(self, flag):
        self.select_mode, self.checked = bool(flag), set()
        self.redraw()

    def check_all(self):
        self.checked = {k for k in (self.key_of(it) for it in self.items) if k}
        self.redraw()

    def selected_item(self):
        return self.items[self.sel] if 0 <= self.sel < len(self.items) else None

    def max_top(self):
        return max(0, self.offs[-1] - int(self.cv.winfo_height()))

    def index_at(self, y):
        y += self.top
        if y < 0 or y >= self.offs[-1]:
            return -1
        return bisect.bisect_right(self.offs, y) - 1

    # ---- scrolling
    def yview(self, *a):
        if a and a[0] == "moveto":
            self.top = int(float(a[1]) * self.offs[-1])
        elif len(a) >= 3 and a[0] == "scroll":
            self.top += int(a[1]) * (self.ROW_H if a[2] == "units" else max(60, int(self.cv.winfo_height()) - 40))
        self.top = max(0, min(self.top, self.max_top()))
        self.redraw()

    def on_wheel(self, e):
        num = e.num if isinstance(getattr(e, "num", 0), int) else 0
        delta = getattr(e, "delta", 0) or 0
        step = -1 if (num == 4 or delta > 0) else 1
        self.top = max(0, min(self.top + step * 70, self.max_top()))
        self.redraw()

    def see(self, i):
        if not 0 <= i < len(self.items):
            return
        h = int(self.cv.winfo_height())
        if self.offs[i] < self.top:
            self.top = self.offs[i]
        elif self.offs[i + 1] > self.top + h:
            self.top = self.offs[i + 1] - h
        self.top = max(0, min(self.top, self.max_top()))

    def move(self, d):
        i = self.sel
        step = 1 if d > 0 else -1
        for _ in range(abs(d)):
            j = i + step
            while 0 <= j < len(self.items) and self.items[j]["kind"] in ("header", "suggest"):
                j += step
            if not 0 <= j < len(self.items):
                break
            i = j
        if i != self.sel and 0 <= i < len(self.items):
            self.sel = i
            self.see(i)
            self.redraw()

    # ---- mouse
    def on_click(self, e):
        self.cv.focus_set()
        i = self.index_at(e.y)
        if i < 0:
            return
        it = self.items[i]
        if self.select_mode:
            k = self.key_of(it)
            if k:
                self.checked.symmetric_difference_update({k})
                self.redraw()
                self.on_select(it)
            return
        if it["kind"] == "song" and e.x > int(self.cv.winfo_width()) - 58:
            self.on_heart(it)
            return
        if it["kind"] in ("header",):
            return
        self.sel = i
        if it["kind"] in ("group", "suggest", "action"):
            self.activate(i)
            return
        self.redraw()

    def on_double(self, e):
        i = self.index_at(e.y)
        if not self.select_mode and i >= 0 and self.items[i]["kind"] == "song" and e.x <= int(self.cv.winfo_width()) - 58:
            self.activate(i)

    def on_context(self, e):
        i = self.index_at(e.y)
        if 0 <= i < len(self.items) and self.items[i]["kind"] in ("song", "group"):
            self.sel = i
            self.redraw()
            self.on_menu(self.items[i], e)

    def on_motion(self, e):
        i = self.index_at(e.y)
        if i != self.hover:
            self.hover = i
            self.redraw()

    def on_leave(self, e):
        if self.hover != -1:
            self.hover = -1
            self.redraw()

    def activate(self, i):
        if 0 <= i < len(self.items) and self.items[i]["kind"] != "header":
            self.on_activate(self.items[i])

    # ---- drawing
    def redraw(self):
        cv, app = self.cv, self.app
        w, h = int(cv.winfo_width()), int(cv.winfo_height())
        if w < 40 or h < 40:
            return
        cv.delete("all")
        total = self.offs[-1]
        self.top = max(0, min(self.top, self.max_top()))
        self.sb.set(self.top / float(total) if total else 0.0, min(1.0, (self.top + h) / float(total)) if total else 1.0)
        if not self.items:
            cv.create_text(w // 2, h // 3, text=app.empty_text(), fill=DIM, font=app.f_ui, width=w - 60, justify="center")
            return
        i = max(0, bisect.bisect_right(self.offs, self.top) - 1)
        while i < len(self.items) and self.offs[i] - self.top < h:
            self.draw_row(i, self.offs[i] - self.top, w)
            i += 1

    def draw_row(self, i, y0, w):
        cv, app, it = self.cv, self.app, self.items[i]
        kind = it["kind"]
        if kind == "header":
            cv.create_text(16, y0 + self.HEAD_H - 12, text=cap(it["title"]), anchor="sw", fill=TXT, font=app.f_head)
            if STYLE["glow"]:                                                       # a short neon line under the heading
                cv.create_line(16, y0 + self.HEAD_H - 6, 60, y0 + self.HEAD_H - 6, fill=BRN2, width=2)
            return
        if kind == "suggest":
            cv.create_text(16, y0 + self.HEAD_H // 2 + 4, text=cap(it["title"]), anchor="w", fill=GOLD, font=app.f_ui_b)
            return
        rh = self.ROW_H
        playing = kind == "song" and it["path"] == E.playing_song_name
        bg = HOVER if i == self.sel else (ROW_HOVER if i == self.hover else "")
        flat = STYLE["shape"] == "flat"
        if bg:
            if flat:
                cv.create_rectangle(6, y0 + 2, w - 6, y0 + rh - 2, fill=bg, outline="")
            else:                                                                   # rounded / cut row, with a neon line on the selected one when the look glows
                draw_shape(cv, 6, y0 + 2, w - 6, y0 + rh - 2, fill=bg, outline=(BRN2 if (STYLE["glow"] and i == self.sel) else ""), shape=STYLE["shape"], r=STYLE["r"])
        if playing:
            if flat:
                cv.create_polygon(8, y0 + rh // 2 - 6, 8, y0 + rh // 2 + 6, 15, y0 + rh // 2, fill=GOLD, outline="")
            else:
                cv.create_rectangle(9, y0 + rh // 2 - 11, 12, y0 + rh // 2 + 11, fill=GOLD, outline="")
        if kind == "action":
            draw_shape(cv, 22, y0 + 5, 70, y0 + 53, fill=PNL2, outline="", shape=STYLE["shape"], r=STYLE["r"]) if not flat else cv.create_rectangle(22, y0 + 5, 70, y0 + 53, fill=PNL2, outline="")
            draw_icon(cv, "plus", 46, y0 + 29, 20, GOLD)
            cv.create_text(84, y0 + rh // 2, text=app.fit(it["title"], "ui_b", max(40, w - 120)), anchor="w", fill=GOLD, font=app.f_ui_b)
            return
        app.draw_cover(cv, 22, y0 + 5, 48, it)
        if self.select_mode and self.key_of(it):
            on = self.key_of(it) in self.checked
            cv.create_rectangle(8, y0 + 18, 26, y0 + 36, fill=GOLD if on else BLK, outline=GOLD, width=2)
            if on:
                cv.create_line(12, y0 + 27, 16, y0 + 32, 23, y0 + 21, fill=BLK, width=2)
        right = w - 20
        if kind == "song":
            fav = it["path"] in E.favorites
            if not self.select_mode:
                draw_icon(cv, "heart_on" if fav else "heart", w - 34, y0 + rh // 2, 15, RED if fav else DIM)
            right = w - 62
            if it.get("right"):
                cv.create_text(right, y0 + rh // 2, text=it["right"], anchor="e", fill=DIM, font=app.f_small)
                right -= app.tw(it["right"], "small") + 14
        else:
            draw_icon(cv, "chev", w - 30, y0 + rh // 2, 14, DIM)
            right = w - 52
        maxw = max(40, right - 84)
        cv.create_text(84, y0 + 21, text=app.fit(it["title"], "ui_b", maxw), anchor="w", fill=GOLD if playing else TXT, font=app.f_ui_b)
        cv.create_text(84, y0 + 41, text=app.fit(it.get("sub", ""), "small", maxw), anchor="w", fill=DIM, font=app.f_small)


TXT_["en"].update(dict(
    lv_title="Live lyrics", lv_loading="Loading the lyrics...", lv_none="No lyrics for this song yet. Open  Find lyrics  and press  Find and sync automatically.",
    lv_plain="These lyrics have no timing, so they cannot follow the song. Open  Find lyrics  and press  Find and sync automatically.", lv_nosong="Play a song first.",
    lv_on="Smooth lyric view (scrolls with the song, Spotify style)", lv_hint="Click a line to jump there. Mouse wheel to browse. +-0.1 s moves the lyrics for this song.",
    lv_learned="Learned from your corrections"))
TXT_["id"].update(dict(
    lv_title="Lirik langsung", lv_loading="Memuat lirik...", lv_none="Belum ada lirik untuk lagu ini. Buka  Cari lirik  lalu tekan  Cari dan sinkronkan otomatis.",
    lv_plain="Lirik ini tidak punya waktu, jadi tidak bisa mengikuti lagu. Buka  Cari lirik  lalu tekan  Cari dan sinkronkan otomatis.", lv_nosong="Putar lagu dulu.",
    lv_on="Tampilan lirik mulus (bergulir mengikuti lagu, gaya Spotify)", lv_hint="Klik satu baris untuk lompat ke sana. Roda mouse untuk melihat-lihat. +-0,1 dtk menggeser lirik lagu ini.",
    lv_learned="Dipelajari dari koreksimu"))

# END-OF-FILE rofpalys_gui_base.py

