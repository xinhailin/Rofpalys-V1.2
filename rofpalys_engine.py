#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - audio engine (playback, pause/seek, lyrics, favorites, settings, yt-dlp)
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Rofpalys engine. No UI code here: the TUI and the GUI both drive this module.
State lives in module globals so both front-ends can read it directly (E.is_playing, E.songs, ...)."""
import json
import locale
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

import rofpalys_effects as FX
import rofpalys_library as lib
import rofpalys_lyrics as LY
import rofpalys_queue as Q
import rofpalys_sleep as SL
import rofpalys_spectrum as SP
import rofpalys_stats as ST

__version__ = "5.4"
USER_AGENT = "Rofpalys/" + __version__
IS_WIN = sys.platform == "win32"
AUDIO_EXTS = lib.AUDIO_EXTS
CONFIG_DIR, CACHE_DIR = lib.CONFIG_DIR, lib.CACHE_DIR
LYRICS_DIR = os.path.join(CACHE_DIR, "lyrics")
FAV_FILE = os.path.join(CONFIG_DIR, "rof_favorites.json")
SET_FILE = os.path.join(CONFIG_DIR, "rof_settings.json")
DOWNLOAD_DIR = os.path.join(lib.HOME, "Music", "Rofpalys")

try:
    locale.setlocale(locale.LC_ALL, '')
except Exception:
    pass

# ------------------------------------------------------------------ state
songs_all, songs, queue_extra = [], [], []      # library / filtered view / files opened from outside the library
library_mtimes = {}
library_version = 0                             # +1 every time a scan finishes (front-ends poll this)
scanning = False
on_library_changed = None                       # GUI sets this to take over list refreshing
selected_idx = 0
playing_song_name = None                        # full path of the current song
is_playing = False                              # True while a song is loaded, also while paused
is_paused = False
play_mode = 0
favorites = set()
search_query, is_searching = "", False
current_lang = 'en'
current_lyrics, synced_lyrics, is_synced_lyrics = [], [], False
lyrics_scroll, last_scroll_time = 0, 0.0
is_downloading, dl_progress_text = False, ""
auto_dj = aura_mode = x3_vis = False
anim_enabled = True
ui_mode = "playlist"
volume = 80
scan_home, extra_folders, exclude_dirs, min_size_kb = True, [], [], 256
# cover art / video (see rofpalys_media.py): art & video = "auto" (download if missing) | "local" (only files you have) | "off"
media_art, media_video = "auto", "auto"
media_lyrics = "both"                            # "panel" | "caption" | "both" | "off"  (lyrics next to / on top of the art or video)
media_prefer_video = True
video_quality, video_max_mb, media_cache_mb = 480, 80, 1500
lyrics_mode, lyrics_youtube, lyrics_source = "auto", True, ""   # "auto" = also look online | "local" = only files and cache; where the shown lyrics came from
notify_controls, sleep_fade = True, True                        # notification buttons (Termux) | volume fades out during the last seconds of the sleep timer
ab_a = ab_b = None                                             # A-B repeat marks (seconds)
sleep_zone, sleep_finish = "local", False                       # time zone used for "until 00:00"; True = let the current song end when the time is up
engine_status_msg, engine_status_time = "", 0.0  # warnings (red)
info_msg, info_time = "", 0.0                    # neutral notices
AVAILABLE_ENGINES, ACTIVE_ENGINE_IDX = [], 0
current_process = None
progress_pct, current_time_str, total_time_str = 0.0, "00:00", "00:00"
current_time_seconds, total_time_seconds, start_time = 0.0, 1.0, 0.0
duration_known = False
manual_stop = False
lock = threading.RLock()
exit_flag = False
_fx_speed_used, _fading, _fade_t, _lv_smooth = 1.0, False, 0.0, {}
_ctx_song = None                                 # the last song that came from the visible list: after a queued song the list goes on from here
FADE_SECS = 20
_gen = 0                                        # bumps on every play/stop; old player threads see it and quit quietly
_active_pygame, _use_simulate, _pause_t = False, False, 0.0
_lyr_token, _lyr_for = 0, None

LANG = {
    'en': {'no_music': 'No music playing', 'track': 'Track', 'm_single': 'Single', 'm_rep1': 'Repeat 1', 'm_seq': 'Sequential',
           'm_loopx': 'Loop All', 'm_shuffle': 'Shuffle', 'lyric_title': '✦ KARAOKE SYNCED LYRICS ✦', 'visual_title': '⚡ QUANTUM MATRIX BASS SURGE ⚡',
           'lyric_empty': 'Lyrics unavailable.', 'lyric_dl': 'Syncing with LRCLIB...', 'lyric_fail': 'Lyrics not found in database.',
           'ctrl_1': '[Z] Lyric | [C] Vis | [X] Lang | [M] Mode | [L] Fav | [R] Reset',
           'ctrl_2': '[V] Search | [Y] yt-dlp | [F] Play | [P] Prev | [N] Next | [Q] Quit',
           'ctrl_3': '[7xz] Engine | [A] AutoDJ | [4a] Aura | [x3] VisX3 | [1b] Anim | [2e] Anim On/Off',
           'ctrl_4': '[Space] Pause | [←/→] Seek 10s | [+/-] Volume | [S] Rescan | [T] Sleep',
           'ctrl_5': '[E] Effects | [U] Add to queue | [B] A-B repeat',
           'nav': '↑/↓: Scroll • W/Enter: Play', 'search': 'Search: ',
           'no_engine': 'No player engine found! Install mpv, ffplay, vlc, or pip install pygame.',
           'all_fail': 'All engines failed to play this file.', 'nofile': 'File not found: ', 'noseek': 'This engine cannot seek',
           'empty': 'No songs found yet', 'scanning': 'Scanning...', 'volume': 'Volume',
           'sleep_on': 'Sleep timer: %s', 'sleep_off': 'Sleep timer off', 'sleep_done': 'Sleep timer: good night',
           'fx_refused': 'This player refused the effects - playing without them', 'fx_needs': 'Effects need mpv or ffplay',
           'fx_on': 'Effects: %s', 'queue_n': 'Up next: %d song(s)', 'ab_a': 'A-B repeat: A set', 'ab_b': 'A-B repeat: looping A to B', 'ab_off': 'A-B repeat off', 'alarm_none': 'Alarm: nothing to play'},
    'id': {'no_music': 'Belum ada lagu', 'track': 'Lagu', 'm_single': 'Normal', 'm_rep1': 'Ulangi 1', 'm_seq': 'Berurutan',
           'm_loopx': 'Ulangi Semua', 'm_shuffle': 'Acak', 'lyric_title': '✦ LIRIK SINKRON KARAOKE ✦', 'visual_title': '⚡ QUANTUM MATRIX BASS SURGE ⚡',
           'lyric_empty': 'Lirik tidak tersedia.', 'lyric_dl': 'Menghubungkan ke LRCLIB...', 'lyric_fail': 'Lirik tidak ditemukan di database.',
           'ctrl_1': '[Z] Lirik | [C] Vis | [X] Bahasa | [M] Mode | [L] Fav | [R] Reset',
           'ctrl_2': '[V] Cari | [Y] yt-dlp | [F] Putar | [P] Mundur | [N] Maju | [Q] Keluar',
           'ctrl_3': '[7xz] Mesin | [A] AutoDJ | [4a] Aura | [x3] VisX3 | [1b] Anim | [2e] Anim On/Off',
           'ctrl_4': '[Spasi] Jeda | [←/→] Geser 10d | [+/-] Volume | [S] Pindai | [T] Tidur',
           'ctrl_5': '[E] Efek | [U] Masuk antrean | [B] Ulang A-B',
           'nav': '↑/↓: Arahkan • W/Enter: Putar', 'search': 'Cari: ',
           'no_engine': 'Tidak ada player terdeteksi! Install mpv, ffplay, vlc, atau pip install pygame.',
           'all_fail': 'Semua engine gagal memutar file ini.', 'nofile': 'File tidak ditemukan: ', 'noseek': 'Mesin ini tidak bisa seek',
           'empty': 'Belum ada lagu ditemukan', 'scanning': 'Memindai...', 'volume': 'Volume',
           'sleep_on': 'Timer tidur: %s', 'sleep_off': 'Timer tidur mati', 'sleep_done': 'Timer tidur: selamat tidur',
           'fx_refused': 'Pemutar ini menolak efek - diputar tanpa efek', 'fx_needs': 'Efek butuh mpv atau ffplay',
           'fx_on': 'Efek: %s', 'queue_n': 'Selanjutnya: %d lagu', 'ab_a': 'Ulang A-B: titik A diset', 'ab_b': 'Ulang A-B: mengulang A sampai B', 'ab_off': 'Ulang A-B mati', 'alarm_none': 'Alarm: tidak ada yang diputar'},
    'zh': {'no_music': '未播放音乐', 'track': '曲目', 'm_single': '单曲', 'm_rep1': '单曲循环', 'm_seq': '顺序播放', 'm_loopx': '循环全部',
           'm_shuffle': '随机播放', 'lyric_title': '✦ 卡拉OK 同步歌词 ✦', 'visual_title': '⚡ 量子矩阵低音冲击 ⚡', 'lyric_empty': '没有歌词。',
           'lyric_dl': '正在从 LRCLIB 同步...', 'lyric_fail': '数据库中未找到歌词。',
           'ctrl_1': '[Z] 歌词 | [C] 可视化 | [X] 语言 | [M] 模式 | [L] 收藏 | [R] 重置',
           'ctrl_2': '[V] 搜索 | [Y] yt-dlp | [F] 播放 | [P] 上一首 | [N] 下一首 | [Q] 退出',
           'ctrl_3': '[7xz] 引擎 | [A] 自动DJ | [4a] 极光 | [x3] 视觉x3 | [1b] 动画 | [2e] 动画开关',
           'nav': '↑/↓: 滚动 • W/回车: 播放', 'search': '搜索: ',
           'no_engine': '未检测到播放器！请安装 mpv、ffplay、vlc，或运行 pip install pygame。', 'all_fail': '所有引擎均无法播放此文件。'},
    'de': {'no_music': 'Keine Musik wird abgespielt', 'track': 'Titel', 'm_single': 'Einzeln', 'm_rep1': 'Wiederholen', 'm_seq': 'Fortlaufend',
           'm_loopx': 'Alle wiederholen', 'm_shuffle': 'Zufällig', 'lyric_title': '✦ KARAOKE SYNCHRONER TEXT ✦',
           'visual_title': '⚡ QUANTUM MATRIX BASS SURGE ⚡', 'lyric_empty': 'Songtext nicht verfügbar.', 'lyric_dl': 'Synchronisiere mit LRCLIB...',
           'lyric_fail': 'Songtext nicht in der Datenbank gefunden.',
           'ctrl_1': '[Z] Text | [C] Visual | [X] Sprache | [M] Modus | [L] Favorit | [R] Reset',
           'ctrl_2': '[V] Suche | [Y] yt-dlp | [F] Abspielen | [P] Zurück | [N] Weiter | [Q] Beenden',
           'ctrl_3': '[7xz] Engine | [A] AutoDJ | [4a] Aura | [x3] VisX3 | [1b] Animation | [2e] Anim. An/Aus',
           'nav': '↑/↓: Scrollen • W/Enter: Abspielen', 'search': 'Suche: ',
           'no_engine': 'Kein Player gefunden! Installiere mpv, ffplay, vlc oder pip install pygame.',
           'all_fail': 'Alle Engines konnten diese Datei nicht abspielen.'},
    'ja': {'no_music': '再生中の曲はありません', 'track': 'トラック', 'm_single': 'シングル', 'm_rep1': '1曲リピート', 'm_seq': '順番再生',
           'm_loopx': '全曲リピート', 'm_shuffle': 'シャッフル', 'lyric_title': '✦ カラオケ同期歌詞 ✦',
           'visual_title': '⚡ クァンタムマトリックス・ベースサージ ⚡', 'lyric_empty': '歌詞がありません。', 'lyric_dl': 'LRCLIBと同期中...',
           'lyric_fail': 'データベースに歌詞が見つかりません。',
           'ctrl_1': '[Z] 歌詞 | [C] ビジュアル | [X] 言語 | [M] モード | [L] お気に入り | [R] リセット',
           'ctrl_2': '[V] 検索 | [Y] yt-dlp | [F] 再生 | [P] 前へ | [N] 次へ | [Q] 終了',
           'ctrl_3': '[7xz] エンジン | [A] オートDJ | [4a] オーラ | [x3] ビジュアルx3 | [1b] アニメ | [2e] アニメON/OFF',
           'nav': '↑/↓: スクロール • W/Enter: 再生', 'search': '検索: ',
           'no_engine': 'プレイヤーが見つかりません！mpv、ffplay、vlcをインストールするか、pip install pygame を実行してください。',
           'all_fail': 'すべてのエンジンでこのファイルを再生できませんでした。'},
    'ru': {'no_music': 'Музыка не воспроизводится', 'track': 'Трек', 'm_single': 'Одиночный', 'm_rep1': 'Повтор 1', 'm_seq': 'По порядку',
           'm_loopx': 'Повтор всех', 'm_shuffle': 'Перемешать', 'lyric_title': '✦ СИНХРОННЫЙ ТЕКСТ ПЕСНИ ✦',
           'visual_title': '⚡ QUANTUM MATRIX BASS SURGE ⚡', 'lyric_empty': 'Текст песни недоступен.', 'lyric_dl': 'Синхронизация с LRCLIB...',
           'lyric_fail': 'Текст песни не найден в базе данных.',
           'ctrl_1': '[Z] Текст | [C] Визуал | [X] Язык | [M] Режим | [L] Избранное | [R] Сброс',
           'ctrl_2': '[V] Поиск | [Y] yt-dlp | [F] Играть | [P] Пред. | [N] След. | [Q] Выход',
           'ctrl_3': '[7xz] Движок | [A] АвтоDJ | [4a] Аура | [x3] ВизуалX3 | [1b] Анимация | [2e] Анимация Вкл/Выкл',
           'nav': '↑/↓: Прокрутка • W/Enter: Играть', 'search': 'Поиск: ',
           'no_engine': 'Плеер не найден! Установите mpv, ffplay, vlc или выполните pip install pygame.',
           'all_fail': 'Все движки не смогли воспроизвести этот файл.'},
}
SUPPORTED_LANGS = ['en', 'zh', 'id', 'de', 'ja', 'ru']


def t(key):
    return LANG.get(current_lang, LANG['en']).get(key) or LANG['en'].get(key, key)


def status(msg):
    global engine_status_msg, engine_status_time
    engine_status_msg, engine_status_time = msg, time.time()


def info(msg):
    global info_msg, info_time
    info_msg, info_time = msg, time.time()


def title_of(path):
    return os.path.splitext(os.path.basename(path))[0] if path else ""


# ------------------------------------------------------------------ audio engines
def detect_audio_engines():
    """Find every usable player (Termux, Linux, macOS, Windows). Each engine may know how to start at an offset (seek)."""
    eng = []

    def add(name, cmd, seek=None):
        eng.append({"name": name, "cmd": cmd, "seek": seek})

    if shutil.which("mpv"):
        add("mpv", ["mpv", "--no-video", "--really-quiet", "--no-terminal"], lambda s: ["--start=%d" % s])
    if shutil.which("ffplay"):
        add("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], lambda s: ["-ss", str(int(s))])
    vlc = None
    if IS_WIN:
        for p in (r"C:\Program Files\VideoLAN\VLC\vlc.exe", r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"):
            if os.path.exists(p):
                vlc = p
                break
        vlc = vlc or shutil.which("vlc")
    else:
        vlc = shutil.which("cvlc") and "cvlc" or shutil.which("vlc") and "vlc"
    if vlc:
        add("VLC", [vlc, "-I", "dummy", "--no-video", "--play-and-exit", "--quiet"], lambda s: ["--start-time=%d" % s])
    if shutil.which("mplayer"):
        add("mplayer", ["mplayer", "-novideo", "-really-quiet"], lambda s: ["-ss", str(int(s))])
    if shutil.which("mpg123"):
        add("mpg123", ["mpg123", "-q"])
    if shutil.which("play"):
        add("SoX (play)", ["play", "-q"])
    if sys.platform == "darwin" and shutil.which("afplay"):
        add("afplay (Mac)", ["afplay"])
    if IS_WIN:
        for p in (r"C:\Program Files (x86)\foobar2000\foobar2000.exe", r"C:\Program Files\foobar2000\foobar2000.exe"):
            if os.path.exists(p):
                add("Foobar2000", [p, "/play"])
                break
    if sys.platform == "linux" and shutil.which("aplay"):
        add("aplay", ["aplay", "-q"])
    try:
        import pygame
        pygame.mixer.init()
        add("PyGame", "INTERNAL_PYGAME")
    except Exception:
        pass
    return eng


AVAILABLE_ENGINES = detect_audio_engines()


def engine_name():
    return AVAILABLE_ENGINES[ACTIVE_ENGINE_IDX]["name"] if AVAILABLE_ENGINES else "no engine"


# ------------------------------------------------------------------ settings / favorites
def _read_json(name):
    for base in (CONFIG_DIR, lib.LEGACY_DIR, os.getcwd()):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                continue
    return None


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
    except OSError:
        pass


def load_favorites():
    global favorites
    d = _read_json("rof_favorites.json")
    favorites = set(x for x in d if isinstance(x, str)) if isinstance(d, list) else set()


def save_favorites():
    _write_json(FAV_FILE, sorted(favorites))


def toggle_favorite(path=None):
    path = path or playing_song_name or (songs[selected_idx] if songs and selected_idx < len(songs) else None)
    if not path:
        return
    favorites.discard(path) if path in favorites else favorites.add(path)
    save_favorites()


def detect_system_language():
    try:
        for var in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
            val = os.environ.get(var)
            if val:
                code = val.split(':')[0].split('.')[0].split('_')[0].lower()
                if code in SUPPORTED_LANGS:
                    return code
    except Exception:
        pass
    return 'en'


def _snap():
    global _settings_snapshot
    _settings_snapshot = _settings_now() if "_settings_now" in globals() else {}


def load_settings():
    global anim_enabled, current_lang, volume, scan_home, extra_folders, exclude_dirs, min_size_kb
    global play_mode, auto_dj, aura_mode, x3_vis
    global media_art, media_video, media_lyrics, media_prefer_video, video_quality, video_max_mb, media_cache_mb
    global lyrics_mode, lyrics_youtube, sleep_zone, sleep_finish, notify_controls, sleep_fade
    current_lang = detect_system_language()
    d = _read_json("rof_settings.json")
    if not isinstance(d, dict):
        _snap()
        return
    anim_enabled = bool(d.get("anim_enabled", True))
    if d.get("language") in SUPPORTED_LANGS:
        current_lang = d["language"]
    volume = max(0, min(100, int(d.get("volume", volume) or 0)))
    scan_home = bool(d.get("scan_home", True))
    extra_folders = [x for x in d.get("folders", []) if isinstance(x, str)]
    exclude_dirs = [x for x in d.get("exclude_dirs", []) if isinstance(x, str)]
    min_size_kb = int(d.get("min_size_kb", 256))
    play_mode = int(d.get("play_mode", 0)) % 5
    auto_dj, aura_mode, x3_vis = bool(d.get("auto_dj")), bool(d.get("aura_mode")), bool(d.get("x3_vis"))
    media_art = d.get("media_art") if d.get("media_art") in ("auto", "local", "off") else "auto"
    media_video = d.get("media_video") if d.get("media_video") in ("auto", "local", "off") else "auto"
    media_lyrics = d.get("media_lyrics") if d.get("media_lyrics") in ("panel", "caption", "both", "off") else "both"
    media_prefer_video = bool(d.get("media_prefer_video", True))
    video_quality = int(d.get("video_quality", 480)) if int(d.get("video_quality", 480)) in (360, 480, 720) else 480
    video_max_mb = max(10, min(1000, int(d.get("video_max_mb", 80))))
    media_cache_mb = max(100, min(50000, int(d.get("media_cache_mb", 1500))))
    lyrics_mode = d.get("lyrics_mode") if d.get("lyrics_mode") in ("auto", "local") else "auto"
    lyrics_youtube = bool(d.get("lyrics_youtube", True))
    sleep_zone = d.get("sleep_zone") if d.get("sleep_zone") in [z[0] for z in SL.ZONES] else "local"
    sleep_finish = bool(d.get("sleep_finish", False))
    FX.preset = d.get("fx_preset") if d.get("fx_preset") in FX.PRESETS else "normal"
    try:
        FX.speed = max(0.5, min(2.0, float(d.get("fx_speed", 1.0))))
    except (TypeError, ValueError):
        FX.speed = 1.0
    FX.reverb = d.get("fx_reverb") if d.get("fx_reverb") in FX.REVERBS else "off"
    FX.normalize = bool(d.get("fx_norm", False))
    notify_controls, sleep_fade = bool(d.get("notify", True)), bool(d.get("sleep_fade", True))
    _snap()


_settings_snapshot = {}


def _settings_now():
    return {"anim_enabled": anim_enabled, "language": current_lang, "volume": volume, "scan_home": scan_home,
            "folders": list(extra_folders), "exclude_dirs": list(exclude_dirs), "min_size_kb": min_size_kb,
            "play_mode": play_mode, "auto_dj": auto_dj, "aura_mode": aura_mode, "x3_vis": x3_vis,
            "media_art": media_art, "media_video": media_video, "media_lyrics": media_lyrics, "media_prefer_video": media_prefer_video,
            "video_quality": video_quality, "video_max_mb": video_max_mb, "media_cache_mb": media_cache_mb,
            "lyrics_mode": lyrics_mode, "lyrics_youtube": lyrics_youtube, "sleep_zone": sleep_zone, "sleep_finish": sleep_finish,
            "fx_preset": FX.preset, "fx_speed": FX.speed, "fx_reverb": FX.reverb, "fx_norm": FX.normalize, "notify": notify_controls, "sleep_fade": sleep_fade}


def save_settings():
    """Writes only the keys THIS process changed, on top of what is on disk: a second window (or an old one still open)
    can no longer overwrite your newer settings with stale values when it closes."""
    global _settings_snapshot
    now = _settings_now()
    disk = None
    try:
        with open(SET_FILE, encoding="utf-8") as f:
            disk = json.load(f)
    except (OSError, ValueError):
        pass
    merged = dict(disk) if isinstance(disk, dict) else {}
    for k, v in now.items():
        if k not in merged or k not in _settings_snapshot or v != _settings_snapshot[k]:
            merged[k] = v
    _write_json(SET_FILE, merged)
    _settings_snapshot = now


# ------------------------------------------------------------------ library
def _roots():
    return lib.default_roots(extra_folders, scan_home)


def _sort_key(p):
    return os.path.basename(p).lower()


def get_audio_files():
    return sorted(library_mtimes, key=_sort_key)


def update_search(reset=True):
    global songs, selected_idx
    q = search_query.strip().lower()
    songs = [s for s in songs_all if not q or q in os.path.basename(s).lower()]
    selected_idx = 0 if reset else min(selected_idx, max(0, len(songs) - 1))


def refresh_playlist(use_cache=True):
    """Show the cached library immediately (no waiting); call scan_library_async() for the fresh one."""
    global songs_all, library_mtimes
    if use_cache and not songs_all:
        cached = lib.load_cache(_roots())
        if cached:
            library_mtimes = cached
            songs_all = sorted(cached, key=_sort_key)
    update_search(reset=False)


def _migrate_favorites():
    """Old versions stored bare file names; map them onto the full paths found by the scan."""
    global favorites
    legacy = [f for f in favorites if not os.path.isabs(f)]
    if not legacy:
        return
    by_name = {}
    for p in songs_all:
        by_name.setdefault(os.path.basename(p), p)
    favorites = set(f for f in favorites if os.path.isabs(f)) | set(by_name.get(f, f) for f in legacy)
    save_favorites()


def scan_library_sync():
    global songs_all, library_mtimes, library_version
    roots = _roots()
    found = lib.scan(roots, AUDIO_EXTS, min_size_kb * 1024, skip_names=exclude_dirs, stop=lambda: exit_flag)
    if exit_flag:
        return found
    lib.save_cache(found, roots)
    for p in queue_extra:
        if os.path.isfile(p):
            found.setdefault(p, 0.0)
    library_mtimes = found
    songs_all = sorted(found, key=_sort_key)
    _migrate_favorites()
    library_version += 1
    if on_library_changed:
        on_library_changed()
    else:
        update_search(reset=False)
    return found


def scan_library_async():
    global scanning
    with lock:
        if scanning:
            return False
        scanning = True

    def work():
        global scanning
        try:
            scan_library_sync()
        except Exception as e:
            status("scan: %s" % e)
        finally:
            scanning = False
    threading.Thread(target=work, daemon=True).start()
    return True


def add_external(paths):
    """Songs from anywhere (other apps, other folders): they join the list for this session."""
    global songs_all
    new = []
    for p in paths:
        p = os.path.abspath(p)
        if p not in queue_extra:
            queue_extra.append(p)
        if p not in library_mtimes:
            try:
                library_mtimes[p] = os.path.getmtime(p)
            except OSError:
                continue
            new.append(p)
    if new:
        songs_all = sorted(set(songs_all) | set(new), key=_sort_key)
        update_search(reset=False)


# ------------------------------------------------------------------ lyrics (the work is done in rofpalys_lyrics.py)
def process_lyrics_data(raw_text, source=""):
    """Parse LRC (synced) or plain text lyrics into the shared state. Instrumental parts become a ♪ line."""
    global current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_source
    lines, synced = LY.parse(raw_text)
    if synced:
        synced_lyrics = LY.add_breaks(lines)
        current_lyrics, is_synced_lyrics = [x[1] for x in synced_lyrics], True
    else:
        synced_lyrics, current_lyrics, is_synced_lyrics = [], lines, False
    lyrics_source = source


def _lyrics_cache_path(song_path):
    return LY.cache_path(song_path)


def fetch_lyrics_online(song_path, token):
    global current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_source
    artist, title = LY.guess(song_path)
    shown = ("%s - %s" % (artist, title)).strip(" -")
    current_lyrics = [t('lyric_dl'), "█▒▒▒▒▒▒▒▒▒", shown]
    for _ in range(20):                                      # wait a moment until the player knows the song length: it makes the match much better
        if duration_known or token != _lyr_token:
            break
        time.sleep(0.1)
    if token != _lyr_token:
        return
    dur = total_time_seconds if duration_known else -1.0
    raw, src, _ = LY.fetch_best(artist, title, dur, allow_youtube=lyrics_youtube, langs=(current_lang,), stop=lambda: token != _lyr_token or exit_flag)
    if token != _lyr_token:
        return
    if raw:
        process_lyrics_data(raw, src)
        LY.write_cache(song_path, raw, src)
    else:
        current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_source = [t('lyric_fail'), "T_T", shown], [], False, ""


def load_lyrics(song_path):
    """Order: .lrc/.txt next to the song, then the cache, then the internet (unless lyrics_mode is 'local')."""
    global current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_scroll, last_scroll_time, _lyr_token, _lyr_for, lyrics_source
    _lyr_token += 1
    token, _lyr_for = _lyr_token, song_path
    current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_source = [], [], False, ""
    lyrics_scroll, last_scroll_time = 0, 0.0
    side = LY.sidecar(song_path)
    if side:
        try:
            with open(side, encoding='utf-8', errors='replace') as f:
                process_lyrics_data(f.read(), "file")
            return
        except OSError:
            pass
    raw, src = LY.read_cache(song_path)
    if raw:
        process_lyrics_data(raw, src)
        return
    if lyrics_mode == "local":
        current_lyrics = [t('lyric_fail'), "T_T", title_of(song_path)]
        return
    current_lyrics = [t('lyric_dl')]
    threading.Thread(target=fetch_lyrics_online, args=(song_path, token), daemon=True).start()


def use_lyrics(raw, source):
    """The user picked these lyrics in the 'find lyrics' dialog: show them now and remember them for this song."""
    path = playing_song_name or _lyr_for
    process_lyrics_data(raw, source)
    if path:
        LY.write_cache(path, raw, source)


def reset_lyrics(path=None):
    """Forget the saved lyrics of a song and search again."""
    global _lyr_for
    path = path or playing_song_name or _lyr_for
    if not path:
        return
    LY.delete_cache(path)
    if path in (playing_song_name, _lyr_for):
        _lyr_for = None
        load_lyrics(path)


# ------------------------------------------------------------------ playback
def format_time(seconds):
    if seconds < 0:
        return "??:??"
    return "%02d:%02d" % (int(seconds // 60), int(seconds % 60))


def get_audio_duration(path):
    if shutil.which("ffprobe"):
        try:
            res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
                                 capture_output=True, text=True, timeout=4)
            if res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
    try:
        import mutagen
        f = mutagen.File(path)
        if f is not None and f.info.length > 0:
            return float(f.info.length)
    except Exception:
        pass
    return -1.0


def _playlist():
    for lst in (songs, songs_all):
        if playing_song_name in lst or (_ctx_song is not None and _ctx_song in lst):
            return lst
    return songs or songs_all


def get_position():
    return current_time_seconds if is_playing else 0.0


def get_mode_string():
    return [t('m_single'), t('m_rep1'), t('m_seq'), t('m_loopx'), t('m_shuffle')][play_mode]


def try_start_one_engine(engine, song_path, offset=0.0, use_fx=True):
    """Start one engine. Returns (handle, start_offset_really_used); handle is 'PYGAME', a Popen, or None.
    Sound effects (rofpalys_effects) are added when this player supports them; if it refuses them the song starts again without effects."""
    global _fx_speed_used
    off = offset if offset > 1 else 0.0
    _fx_speed_used = 1.0
    try:
        if engine["cmd"] == "INTERNAL_PYGAME":
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(song_path)
            pygame.mixer.music.play(start=off) if off else pygame.mixer.music.play()
            return "PYGAME", off
        cmd, used = list(engine["cmd"]), 0.0
        fx_args = FX.args_for(engine["name"]) if use_fx else []
        cmd += fx_args
        if off and engine.get("seek"):
            cmd += engine["seek"](off)
            used = off
        cmd.append(song_path)
        kw = {"creationflags": 0x08000000} if IS_WIN else {}
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        time.sleep(0.25)
        if proc.poll() is not None:
            if fx_args:
                status(t('fx_refused'))
                return try_start_one_engine(engine, song_path, offset, use_fx=False)
            return None, 0.0
        _fx_speed_used = FX.speed_for(engine["name"]) if fx_args else 1.0
        return proc, used
    except Exception:
        return None, 0.0


def _kill(handle, pygame_used, simulate=False):
    if pygame_used:
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass
    elif handle is not None and not simulate:
        try:
            if hasattr(signal, "SIGCONT"):
                os.kill(handle.pid, signal.SIGCONT)      # a frozen (paused) process cannot handle SIGTERM
        except Exception:
            pass
        try:
            handle.terminate()
            handle.wait(timeout=1)
        except Exception:
            try:
                handle.kill()
            except Exception:
                pass


def _halt_locked():
    global current_process
    _kill(current_process, _active_pygame, _use_simulate)
    current_process = None


def run_player_engine(song_path, start=0.0, gen=None):
    global current_process, is_playing, is_paused, progress_pct, start_time, ACTIVE_ENGINE_IDX
    global current_time_str, total_time_str, current_time_seconds, total_time_seconds, duration_known
    global _active_pygame, _use_simulate, playing_song_name, ab_a, ab_b
    gen = _gen if gen is None else gen

    def fail(msg):
        global is_playing, playing_song_name
        status(msg)
        with lock:
            if gen == _gen:
                is_playing, playing_song_name = False, None

    if not AVAILABLE_ENGINES:
        return fail(t('no_engine'))
    if not os.path.isfile(song_path):
        return fail(t('nofile') + os.path.basename(song_path))
    dur = get_audio_duration(song_path)
    with lock:
        if gen != _gen:
            return
        duration_known = dur > 0
        total_time_seconds = dur if duration_known else 1.0
        total_time_str = format_time(dur)
        current_time_seconds, current_time_str, progress_pct = 0.0, "00:00", 0.0

    n = len(AVAILABLE_ENGINES)
    handle, used, engine, use_pygame = None, 0.0, None, False
    for idx in [(ACTIVE_ENGINE_IDX + i) % n for i in range(n)]:
        cand = AVAILABLE_ENGINES[idx]
        handle, used = try_start_one_engine(cand, song_path, start)
        if handle is not None:
            engine, use_pygame, ACTIVE_ENGINE_IDX = cand, handle == "PYGAME", idx
            break
    if engine is None:
        return fail(t('all_fail'))
    simulate = engine["name"] == "Foobar2000"
    with lock:
        if gen != _gen:                                  # a newer song was requested while this one was starting
            _kill(handle, use_pygame, simulate)
            return
        current_process = None if use_pygame else handle
        _active_pygame, _use_simulate = use_pygame, simulate
        is_playing, is_paused = True, False
        spd = _fx_speed_used if _fx_speed_used > 0 else 1.0
        start_time = time.time() - used / spd
        current_time_seconds = used
    last_t, acc = time.time(), 0.0

    while True:
        now_t = time.time()
        dt_real, last_t = now_t - last_t, now_t
        if gen != _gen:
            return                                       # stop()/play_song() already cleaned up
        if exit_flag:
            _kill(handle, use_pygame, simulate)
            return
        if SL.due() and not SL.finish_song:                  # the sleep timer is up: stop right now (also while paused)
            SL.fire()
            info(t('sleep_done'))
            stop()
            _restore_volume()
            return
        _sleep_fade()
        if is_paused:
            time.sleep(0.1)
            continue
        acc += min(dt_real, 1.0)
        if acc >= 1.0:
            ST.tick(song_path, acc)                           # listening statistics: real seconds, not paused
            acc = 0.0
        finished = False
        if use_pygame:
            try:
                import pygame
                finished = not pygame.mixer.music.get_busy()
            except Exception:
                finished = True
        elif simulate:
            finished = time.time() - start_time >= (total_time_seconds if duration_known else 300.0)
        else:
            finished = handle.poll() is not None
        if finished:
            break
        elapsed = (time.time() - start_time) * spd
        if ab_a is not None and ab_b is not None and elapsed >= ab_b:
            if seek(ab_a):                                    # A-B repeat: jump back to A
                return
            _ab_clear()
        if auto_dj and duration_known and elapsed >= total_time_seconds - 10.0:
            _kill(handle, use_pygame, simulate)
            break
        with lock:
            current_time_seconds, current_time_str = elapsed, format_time(elapsed)
            progress_pct = min(1.0, elapsed / total_time_seconds) if duration_known else -1.0
        time.sleep(0.1)

    ST.tick(song_path, acc)
    with lock:
        if gen != _gen:
            return
        current_process = None
        is_playing = is_paused = False
        progress_pct, current_time_str, current_time_seconds = 0.0, "00:00", 0.0
    if not exit_flag:
        handle_song_end()


def play_song(song_path, start=0.0, record=True):
    global playing_song_name, _gen, is_paused, _ctx_song
    if not song_path:
        return
    with lock:
        prev = playing_song_name
        _gen += 1
        gen = _gen
        _halt_locked()
        is_paused = False
        playing_song_name = song_path
    if song_path in songs or song_path in songs_all:
        _ctx_song = song_path
    if prev != song_path:                                    # a different song starts
        if record and prev:
            Q.push_history(prev)
        ST.played(song_path)
        _ab_clear()
        SP.load(song_path)
    if song_path != _lyr_for:
        load_lyrics(song_path)
    threading.Thread(target=run_player_engine, args=(song_path, start, gen), daemon=True).start()


def stop():
    global _gen, is_playing, is_paused, progress_pct, current_time_str, current_time_seconds
    with lock:
        _gen += 1
        _halt_locked()
        is_playing = is_paused = False
        progress_pct, current_time_str, current_time_seconds = 0.0, "00:00", 0.0


def pause():
    """Freeze playback without losing the position. Returns False if this engine cannot pause."""
    global is_paused, _pause_t
    with lock:
        if not is_playing or is_paused:
            return False
        if _active_pygame:
            try:
                import pygame
                pygame.mixer.music.pause()
            except Exception:
                return False
        elif current_process is not None and hasattr(signal, "SIGSTOP"):
            try:
                os.kill(current_process.pid, signal.SIGSTOP)
            except Exception:
                return False
        else:
            return False
        is_paused, _pause_t = True, time.time()
    return True


def resume():
    global is_paused, start_time
    with lock:
        if not is_paused:
            return False
        if _active_pygame:
            try:
                import pygame
                pygame.mixer.music.unpause()
            except Exception:
                pass
        elif current_process is not None and hasattr(signal, "SIGCONT"):
            try:
                os.kill(current_process.pid, signal.SIGCONT)
            except Exception:
                pass
        start_time += time.time() - _pause_t               # paused time does not count as played time
        is_paused = False
    return True


def seek(sec):
    if not playing_song_name or not duration_known or not AVAILABLE_ENGINES:
        return False
    eng = AVAILABLE_ENGINES[ACTIVE_ENGINE_IDX]
    if eng["name"] != "PyGame" and not eng.get("seek"):
        status(t('noseek'))
        return False
    play_song(playing_song_name, max(0.0, min(sec, total_time_seconds - 2)))
    return True


def toggle_play():
    if playing_song_name is None:
        if songs:
            play_song(songs[min(selected_idx, len(songs) - 1)])
    elif is_paused:
        resume()
    elif is_playing:
        if not pause():
            stop()
    else:
        play_song(playing_song_name)


def _next_queued():
    while Q.upnext:
        p = Q.pop_next()
        if p and os.path.isfile(p):
            return p
    return None


def step(d=1):
    """Next (d=1) or previous (d=-1): the queue first, then the list; 'previous' restarts a song that already played a few seconds, otherwise it goes
    back to what you really heard before."""
    lst = _playlist()
    if d < 0:
        if is_playing and playing_song_name and current_time_seconds > 3.0:
            play_song(playing_song_name)
            return
        p = Q.pop_previous(playing_song_name)
        if p and os.path.isfile(p):
            play_song(p, record=False)
            return
    elif d > 0:
        nxt = _next_queued()
        if nxt:
            play_song(nxt)
            return
        if play_mode == 4 and lst:
            play_song(Q.shuffle_next(lst, playing_song_name))
            return
    if not lst:
        return
    ref = playing_song_name if playing_song_name in lst else _ctx_song
    if ref in lst:
        i = (lst.index(ref) + d) % len(lst)
    else:
        i = 0
    play_song(lst[i])


def handle_song_end():
    global playing_song_name
    if not playing_song_name:
        return
    if SL.active():                                          # sleep timer: repeat THIS song until the time is up
        if SL.due():
            SL.fire()
            info(t('sleep_done'))
            _restore_volume()
            return
        play_song(playing_song_name)
        return
    if play_mode == 1:                                       # repeat one beats the queue
        play_song(playing_song_name)
        return
    nxt = _next_queued()
    if nxt:
        play_song(nxt)
        return
    lst = _playlist()
    try:
        idx = lst.index(playing_song_name if playing_song_name in lst else _ctx_song)
    except ValueError:
        playing_song_name = None
        return
    if play_mode == 0:
        playing_song_name = None
    elif play_mode == 1:
        play_song(playing_song_name)
    elif play_mode == 2:
        if idx < len(lst) - 1:
            play_song(lst[idx + 1])
        else:
            playing_song_name = None
    elif play_mode == 3:
        play_song(lst[(idx + 1) % len(lst)])
    elif play_mode == 4:
        play_song(Q.shuffle_next(lst, playing_song_name))


# ------------------------------------------------------------------ volume
def _apply_volume(v):
    try:
        if _active_pygame:
            import pygame
            pygame.mixer.music.set_volume(v / 100.0)
    except Exception:
        pass
    cmds = [["pactl", "set-sink-volume", "@DEFAULT_SINK@", "%d%%" % v], ["termux-volume", "music", str(round(v * 15 / 100))],
            ["osascript", "-e", "set volume output volume %d" % v], ["amixer", "-q", "sset", "Master", "%d%%" % v]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
            break


def set_volume(v, apply=True):
    global volume
    volume = max(0, min(100, int(float(v))))
    if apply:
        _apply_volume(volume)


def change_volume(delta):
    set_volume(volume + delta)
    info("%s: %d%%" % (t('volume'), volume))
    save_settings()


# ------------------------------------------------------------------ yt-dlp / reset / shutdown
def download_and_play_yt(url):
    """Download audio with yt-dlp into ~/Music/Rofpalys, add it to the library and play it."""
    global is_downloading, dl_progress_text
    is_downloading, dl_progress_text = True, "0%"
    try:
        if not shutil.which("yt-dlp"):
            dl_progress_text = "yt-dlp not found!  (pip install yt-dlp)"
            time.sleep(2.5)
            return
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        before = set(os.listdir(DOWNLOAD_DIR))
        p = subprocess.Popen(["yt-dlp", "-f", "ba", "-x", "--audio-format", "mp3", "--newline", "--no-playlist", "-P", DOWNLOAD_DIR,
                              "-o", "%(title)s.%(ext)s", "--", url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        for ln in p.stdout:
            m = re.search(r"(\d+(?:\.\d+)?)%", ln)
            if m:
                dl_progress_text = m.group(1) + "%"
        p.wait()
        new = [os.path.join(DOWNLOAD_DIR, f) for f in set(os.listdir(DOWNLOAD_DIR)) - before if f.lower().endswith(AUDIO_EXTS)]
        if p.returncode != 0 or not new:
            dl_progress_text = "failed"
            time.sleep(2)
            return
        dl_progress_text = "done"
        add_external([max(new, key=os.path.getmtime)])
        play_song(max(new, key=os.path.getmtime))
        time.sleep(1)
    except Exception as e:
        dl_progress_text = "failed: %s" % e
        time.sleep(2)
    finally:
        is_downloading = False


# ------------------------------------------------------------------ sleep timer (the maths is in rofpalys_sleep.py)
def sleep_start_duration(seconds):
    SL.start_duration(seconds, sleep_finish)
    info(t('sleep_on') % SL.fmt_left(seconds))


def sleep_start_until(hh, mm, key):
    global sleep_zone
    sleep_zone = key
    SL.start_until(hh, mm, key, sleep_finish)
    save_settings()
    info(t('sleep_on') % ("%02d:%02d %s" % (hh, mm, SL.zone(key)[2])))


def sleep_cancel():
    SL.cancel()
    info(t('sleep_off'))


def sleep_set_finish(flag):
    global sleep_finish
    sleep_finish = bool(flag)
    SL.finish_song = sleep_finish
    save_settings()


# ------------------------------------------------------------------ queue, effects, A-B repeat, real spectrum, alarm, fades
def queue_add(paths, front=False):
    """'Add to queue' (end) or 'Play next' (front)."""
    paths = [p for p in paths if p]
    Q.add_many(paths, front)
    info(t('queue_n') % len(Q.upnext))


def queue_clear():
    Q.clear()


def fx_apply(preset=None, speed=None, reverb=None, normalize=None):
    """Change the sound effects. They apply at once: the song restarts from where it is."""
    if preset is not None:
        if preset not in FX.PRESETS:
            raise ValueError("preset")
        FX.preset = preset
    if speed is not None:
        FX.speed = max(0.5, min(2.0, float(speed)))
    if reverb is not None:
        if reverb not in FX.REVERBS:
            raise ValueError("reverb")
        FX.reverb = reverb
    if normalize is not None:
        FX.normalize = bool(normalize)
    save_settings()
    if FX.is_active() and AVAILABLE_ENGINES and not FX.supported(engine_name()):
        status(t('fx_needs'))
    else:
        info(t('fx_on') % FX.label())
    if playing_song_name and is_playing and not is_paused:
        play_song(playing_song_name, current_time_seconds)


def fx_label():
    return FX.label()


def _ab_clear():
    global ab_a, ab_b
    ab_a = ab_b = None


def ab_mark():
    """A-B repeat: first press sets A, second sets B (and loops A..B), third clears."""
    global ab_a, ab_b
    pos = current_time_seconds
    if not playing_song_name:
        return
    if ab_a is None:
        ab_a = pos
        info(t('ab_a'))
    elif ab_b is None:
        if pos - ab_a < 1.0:
            return
        ab_b = pos
        info(t('ab_b'))
    else:
        _ab_clear()
        info(t('ab_off'))


def get_levels(n=32):
    """n bar heights 0..1 that follow the REAL song at this moment (None when it is not analysed: callers keep their simulation)."""
    if not (is_playing and not is_paused and playing_song_name):
        return None
    lv = SP.levels(playing_song_name, current_time_seconds, n)
    if lv is None:
        return None
    prev = _lv_smooth.get(n)
    if prev and len(prev) == n:
        lv = [max(v, p * 0.80) for v, p in zip(lv, prev)]    # quick to rise, slow to fall: looks like a real analyser
    _lv_smooth[n] = lv
    return lv


def _sleep_fade():
    """During the last seconds of the sleep timer the volume goes down smoothly."""
    global _fading, _fade_t
    now = time.time()
    if now - _fade_t < 1.0:
        return
    if sleep_fade and SL.active() and not SL.finish_song and SL.remaining() <= FADE_SECS:
        _fade_t, _fading = now, True
        _apply_volume(max(0, int(volume * SL.remaining() / float(FADE_SECS))))
    elif _fading:
        _fade_t, _fading = now, False
        _apply_volume(volume)


def _restore_volume():
    global _fading
    if _fading:
        _fading = False
        _apply_volume(volume)


def fade_in(seconds=60):
    """Volume rises from very quiet to the set volume (used by the alarm)."""
    steps = 24

    def work():
        for i in range(1, steps + 1):
            if exit_flag:
                break
            _apply_volume(max(3, int(volume * i / float(steps))))
            time.sleep(max(0.05, seconds / float(steps)))
        _apply_volume(volume)
    threading.Thread(target=work, daemon=True).start()


def alarm_fire(a):
    """An alarm rang (called by rofpalys_alarm): start its song or playlist softly."""
    tgt, paths = a.get("target", {}), []
    if tgt.get("type") == "song":
        paths = [tgt.get("ref", "")]
    elif tgt.get("type") == "playlist":
        import rofpalys_playlists as PLS
        pl = PLS.get(tgt.get("ref"))
        paths = list(pl["paths"]) if pl else []
    paths = [p for p in paths if p and os.path.isfile(p)]
    if not paths:
        status(t('alarm_none'))
        return
    Q.clear()
    Q.add_many(paths[1:])
    add_external(paths[:1])
    play_song(paths[0])
    fade_in(a.get("ramp", 60))


# ------------------------------------------------------------------ reset
def _defaults():
    """Put every setting back to its factory value (in memory)."""
    global anim_enabled, current_lang, volume, scan_home, extra_folders, exclude_dirs, min_size_kb, play_mode, auto_dj, aura_mode, x3_vis
    global media_art, media_video, media_lyrics, media_prefer_video, video_quality, video_max_mb, media_cache_mb
    global lyrics_mode, lyrics_youtube, sleep_zone, sleep_finish, _settings_snapshot, notify_controls, sleep_fade
    anim_enabled, current_lang, volume, scan_home, extra_folders, exclude_dirs, min_size_kb = True, detect_system_language(), 80, True, [], [], 256
    play_mode, auto_dj, aura_mode, x3_vis = 0, False, False, False
    media_art, media_video, media_lyrics, media_prefer_video, video_quality, video_max_mb, media_cache_mb = "auto", "auto", "both", True, 480, 80, 1500
    lyrics_mode, lyrics_youtube, sleep_zone, sleep_finish = "auto", True, "local", False
    notify_controls, sleep_fade = True, True
    FX.reset()
    _settings_snapshot = {}


def reset_everything(keep_favorites=False):
    """DEEP reset: removes every file Rofpalys made for itself - settings, favorites, window state, statistics, lyrics, cover art and video cache,
    library cache and the files left by the very old versions. Never touches your songs, your .lrc files, the program files,
    or the audio you downloaded into Music/ROFPALys. Returns the list of what was removed."""
    global current_lyrics, synced_lyrics, is_synced_lyrics, playing_song_name, _lyr_for, lyrics_source
    stop()
    SL.cancel()
    removed = []
    names = ["rof_settings.json", "gui.json", "stats.json", "alarms.json"] + ([] if keep_favorites else ["rof_favorites.json", "playlists.json"])
    paths = [os.path.join(d, n) for d in (CONFIG_DIR, lib.LEGACY_DIR, os.getcwd()) for n in names]
    for pth in paths:                                     # the legacy / current-folder copies matter: the loader would bring old data back from them
        if os.path.isfile(pth):
            try:
                os.remove(pth)
                removed.append(pth)
            except OSError:
                pass
    if os.path.isdir(CACHE_DIR):
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        removed.append(CACHE_DIR)
    if not keep_favorites:
        favorites.clear()
    ST.reset()
    Q.reset()
    FX.reset()
    current_lyrics, synced_lyrics, is_synced_lyrics, lyrics_source = [], [], False, ""
    playing_song_name, _lyr_for = None, None
    _defaults()
    return removed


def deep_reset(full=False):
    """Forget favorites, cached lyrics and playback state (full=True: everything, see reset_everything). Never touches the user's own song or .lrc files."""
    global current_lyrics, synced_lyrics, is_synced_lyrics, play_mode, playing_song_name, _lyr_for
    stop()
    favorites.clear()
    try:
        os.remove(FAV_FILE)
    except OSError:
        pass
    shutil.rmtree(LYRICS_DIR, ignore_errors=True)
    current_lyrics, synced_lyrics, is_synced_lyrics = [], [], False
    play_mode, playing_song_name, _lyr_for = 0, None, None
    if full:
        reset_everything()
        return
    save_settings()


def shutdown(save=True):
    global exit_flag
    exit_flag = True
    if save:
        save_settings()
        ST.save(force=True)
    with lock:
        _halt_locked()

# END-OF-FILE rofpalys_engine.py

