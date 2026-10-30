#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - statistics words: texts (English / Indonesian), number formats, text reports for the terminal
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""Everything that turns the numbers of rofpalys_analytics_calc.py into words: the texts of the statistics window and of `rofpalys stats`, durations, dates, one-line
descriptions of every kind of event, the written definitions ('what exactly is a play?') and the plain-text reports with bars, sparklines and the hour heat map.
No files, no engine, no Tk. The window and the terminal both use these, so they always say the same thing."""
import os

import rofpalys_analytics_calc as C

__version__ = "1.0"

TX = {
    "en": dict(
        stats="Statistics", today="Today", yesterday="Yesterday", w7="Last 7 days", d30="Last 30 days", d90="Last 90 days", month="This month", year="This year", all="All time",
        listening="Listening", appopen="Rofpalys open", plays="Plays", starts="Started", songs="Songs", artists="Artists", folders="Folders", streak="Streak", days="days",
        completed="Completed", skipped="Skipped", completion="Completion", skip_rate="Skip rate", repeat="Replays", peak_hour="Peak hour", peak_day="Busiest weekday",
        avg_active="Per active day", avg_cal="Per calendar day", night="Night", morning="Morning", afternoon="Afternoon", evening="Evening", total="Total",
        overview="Overview", live="Live", top_songs="Top songs", top_artists="Top artists", by_day="Day by day", by_time="Time of day", activity="Activity", records="Records & quality",
        tab_overview="Overview", tab_live="Today", tab_songs="Songs", tab_artists="Artists", tab_days="Days", tab_time="Time", tab_activity="Activity", tab_records="Records",
        rank="#", title="Title", artist="Artist", time="Time", done="Done", skips="Skips", last="Last", by="Rank by", by_plays="Plays", by_time_="Time",
        rule="Counting rule", r_lastfm="Last.fm style", r_spotify="Spotify style", r_starts="Every start", r_finished="Completed only",
        now_playing="Now playing", nothing="Nothing is playing", session="This session", up="Open for", heard="Listened", this_song="This song", vs_yday="vs yesterday",
        avg7="7-day average", longest_streak="Longest streak", current_streak="Current streak", best_day="Best day", most_plays="Most songs in a day", most_repeat="Most repeats in a day",
        longest_bout="Longest listening bout", longest_session="Longest session", most_open="Most open time in a day", none="Nothing yet - play some music and come back",
        quality="Data quality", integrity="Integrity", chain_ok="Chain verified", chain_bad="Chain BROKEN", records_n="Records", since="Since", observed="Measured live", inferred="Inferred across gaps",
        gaps="Unobserved gaps", clocks="Clock changes", recovered="Recoveries after a stop", verify="Verify now", export="Export", define="How the numbers are counted",
        rec_on="Recording", rec_off="Not recording here", verified="Verified", exported="Written to", copied="Copied", fav_on="added", fav_off="removed", of_started="of %d started",
        sessions_n="Sessions", counts_in="counts as a play in", counted="counted", heard_only="heard 30 s+", not_counted="not counted", per_day="per day", today_so_far="today so far",
        weekdays=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), weekdays_long=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        months=("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), close="Close",
        no_recorder="The recorder is not running in this program (the numbers below are from the saved log)", surfaces="Where you used it", kinds="What you did",
        events="Events", filter_all="All", per_hour="Listening per hour", per_weekday="Listening per weekday", heat="When you listen (weekday x hour)", minutes="minutes", hours_="hours",
        detail="Song details", first_played="First played", plays_14="Last 30 days", rank_of="Rank", of="of", date="Date", sessions="Sessions", open_="Open", not_medical="Audit-grade logging; not a medical device",
        unit_m="m", unit_h="h", unit_s="s", unit_d="d", tip_f7="F7 opens statistics", not_verified="Not checked yet - press Verify now", integrity_note="Every record carries the fingerprint (SHA-256) of the one before it. Change or remove a single record and the chain no longer matches - Verify shows exactly where.", checking="Checking the log ...", song_1="song", song_n="songs", day_1="day", day_n="days",
        k_play="Started", k_fin="Ended", k_pause="Paused", k_resume="Resumed", k_seek="Jumped", k_vol="Volume", k_mode="Play mode", k_fav="Favourite", k_sleep="Sleep timer", k_queue="Up next",
        k_fx="Effect", k_lyrics="Lyrics", k_ui="Window / setting", k_sess="Opened", k_end="Closed", k_gap="Gap", k_clock="Clock", k_recover="Recovered",
        w_finished="finished", w_left="left early", w_stopped="stopped", w_quit="program closed", w_crash="program stopped unexpectedly"),
    "id": dict(
        stats="Statistik", today="Hari ini", yesterday="Kemarin", w7="7 hari terakhir", d30="30 hari terakhir", d90="90 hari terakhir", month="Bulan ini", year="Tahun ini", all="Sepanjang waktu",
        listening="Mendengarkan", appopen="Rofpalys dibuka", plays="Diputar", starts="Dimulai", songs="Lagu", artists="Artis", folders="Folder", streak="Beruntun", days="hari",
        completed="Selesai", skipped="Dilewati", completion="Tuntas", skip_rate="Dilewati", repeat="Diulang", peak_hour="Jam puncak", peak_day="Hari tersibuk",
        avg_active="Per hari aktif", avg_cal="Per hari kalender", night="Malam", morning="Pagi", afternoon="Siang", evening="Petang", total="Total",
        overview="Ringkasan", live="Langsung", top_songs="Lagu teratas", top_artists="Artis teratas", by_day="Hari demi hari", by_time="Waktu dalam sehari", activity="Aktivitas", records="Rekor & mutu data",
        tab_overview="Ringkasan", tab_live="Hari ini", tab_songs="Lagu", tab_artists="Artis", tab_days="Hari", tab_time="Waktu", tab_activity="Aktivitas", tab_records="Rekor",
        rank="#", title="Judul", artist="Artis", time="Waktu", done="Tuntas", skips="Lewati", last="Terakhir", by="Urutkan", by_plays="Putaran", by_time_="Waktu",
        rule="Aturan hitung", r_lastfm="Gaya Last.fm", r_spotify="Gaya Spotify", r_starts="Setiap mulai", r_finished="Hanya yang selesai",
        now_playing="Sedang diputar", nothing="Tidak ada yang diputar", session="Sesi ini", up="Terbuka", heard="Didengar", this_song="Lagu ini", vs_yday="dibanding kemarin",
        avg7="Rata-rata 7 hari", longest_streak="Beruntun terpanjang", current_streak="Beruntun sekarang", best_day="Hari terbaik", most_plays="Lagu terbanyak dalam sehari", most_repeat="Ulang terbanyak dalam sehari",
        longest_bout="Mendengar nonstop terlama", longest_session="Sesi terpanjang", most_open="Terbuka terlama dalam sehari", none="Belum ada - putar musik dulu lalu kembali ke sini",
        quality="Mutu data", integrity="Keutuhan", chain_ok="Rantai terverifikasi", chain_bad="Rantai RUSAK", records_n="Catatan", since="Sejak", observed="Diukur langsung", inferred="Disimpulkan saat celah",
        gaps="Celah tak teramati", clocks="Perubahan jam", recovered="Pulih setelah berhenti", verify="Periksa sekarang", export="Ekspor", define="Cara angka dihitung",
        rec_on="Merekam", rec_off="Tidak merekam di sini", verified="Terverifikasi", exported="Ditulis ke", copied="Disalin", fav_on="ditambah", fav_off="dihapus", of_started="dari %d dimulai",
        sessions_n="Sesi", counts_in="terhitung sebagai putaran dalam", counted="terhitung", heard_only="didengar 30 dtk+", not_counted="tidak terhitung", per_day="per hari", today_so_far="hari ini sejauh ini",
        weekdays=("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"), weekdays_long=("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"),
        months=("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"), close="Tutup",
        no_recorder="Pencatat tidak berjalan di program ini (angka di bawah dari log tersimpan)", surfaces="Dipakai lewat", kinds="Yang kamu lakukan",
        events="Kejadian", filter_all="Semua", per_hour="Mendengar per jam", per_weekday="Mendengar per hari", heat="Kapan kamu mendengar (hari x jam)", minutes="menit", hours_="jam",
        detail="Rincian lagu", first_played="Pertama diputar", plays_14="30 hari terakhir", rank_of="Peringkat", of="dari", date="Tanggal", sessions="Sesi", open_="Terbuka", not_medical="Pencatatan tingkat audit; bukan alat medis",
        unit_m="m", unit_h="j", unit_s="d", unit_d="hr", tip_f7="F7 membuka statistik", not_verified="Belum diperiksa - tekan Periksa sekarang", integrity_note="Setiap catatan membawa sidik jari (SHA-256) catatan sebelumnya. Ubah atau hapus satu catatan saja dan rantai tidak cocok lagi - Periksa menunjukkan tepatnya di mana.", checking="Memeriksa log ...", song_1="lagu", song_n="lagu", day_1="hari", day_n="hari",
        k_play="Mulai", k_fin="Berakhir", k_pause="Jeda", k_resume="Lanjut", k_seek="Lompat", k_vol="Volume", k_mode="Mode putar", k_fav="Favorit", k_sleep="Timer tidur", k_queue="Antrean",
        k_fx="Efek", k_lyrics="Lirik", k_ui="Jendela / pengaturan", k_sess="Dibuka", k_end="Ditutup", k_gap="Celah", k_clock="Jam", k_recover="Dipulihkan",
        w_finished="selesai", w_left="ditinggal", w_stopped="dihentikan", w_quit="program ditutup", w_crash="program berhenti mendadak"),
}
MODE_NAMES = {"en": ("Single", "Repeat one", "Sequential", "Loop all", "Shuffle"), "id": ("Sekali", "Ulang satu", "Berurutan", "Ulang semua", "Acak")}
SYMBOL = {"play": "▶", "fin": "■", "pause": "‖", "resume": "▶", "seek": "↔", "vol": "≋", "mode": "⇄", "fav": "♥", "sleep": "☾", "queue": "≡", "fx": "◈", "lyrics": "♪",
          "ui": "◉", "sess": "●", "end": "○", "gap": "!", "clock": "!", "recover": "+"}


def lang():
    """The language of the text reports: ROFPALYS_LANG, then the player's own setting when it is loaded, then the system language; Indonesian for 'id', else English."""
    v = (os.environ.get("ROFPALYS_LANG") or "").strip().lower()
    if not v:
        try:
            import sys
            e = sys.modules.get("rofpalys_engine")
            v = str(getattr(e, "current_lang", "") or "").lower()
        except Exception:
            v = ""
    if not v:
        v = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "").lower()
    return "id" if v.startswith("id") else "en"


def T(lg, key):
    return TX.get(lg, TX["en"]).get(key, TX["en"].get(key, key))


# ---------------------------------------------------------------- formats
def fmt_dur(s, lg="en", secs=False):
    """1h 05m / 5m 03s / 12s  (Indonesian: 1j 05m ...). secs=True keeps the seconds also above one hour."""
    s = max(0, int(round(s)))
    h_, m_, d_, s_ = T(lg, "unit_h"), T(lg, "unit_m"), T(lg, "unit_d"), T(lg, "unit_s")
    if s >= 86400:
        return "%d%s %02d%s" % (s // 86400, d_, s % 86400 // 3600, h_)
    if s >= 3600:
        return ("%d%s %02d%s %02d%s" % (s // 3600, h_, s % 3600 // 60, m_, s % 60, s_)) if secs else ("%d%s %02d%s" % (s // 3600, h_, s % 3600 // 60, m_))
    if s >= 60:
        return "%d%s %02d%s" % (s // 60, m_, s % 60, s_)
    return "%d%s" % (s, s_)


def fmt_axis(s, lg="en"):
    """A short label for a chart axis: 45s / 30m / 2.5h / 3d."""
    s = max(0.0, float(s))
    if s >= 86400:
        v = s / 86400.0
        return ("%d%s" if v >= 10 or abs(v - round(v)) < 0.05 else "%.1f%s") % (round(v) if v >= 10 or abs(v - round(v)) < 0.05 else v, T(lg, "unit_d"))
    if s >= 3600:
        v = s / 3600.0
        return ("%d%s" if v >= 10 or abs(v - round(v)) < 0.05 else "%.1f%s") % (round(v) if v >= 10 or abs(v - round(v)) < 0.05 else v, T(lg, "unit_h"))
    if s >= 60:
        return "%d%s" % (round(s / 60.0), T(lg, "unit_m"))
    return "%d%s" % (round(s), T(lg, "unit_s"))


def count_of(n, lg, one, many):
    """'1 song' / '5 songs' (Indonesian has no plural: '5 lagu')."""
    n = int(n)
    return "%d %s" % (n, T(lg, one if n == 1 else many))


def n_songs(n, lg="en"):
    return count_of(n, lg, "song_1", "song_n")


def n_days(n, lg="en"):
    return count_of(n, lg, "day_1", "day_n")


def fmt_clock(s):
    s = max(0, int(s))
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def fmt_mmss(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60)


def fmt_pct(x):
    return "%d%%" % round(100 * x)


def fmt_num(n, lg="en"):
    t = "{:,}".format(int(n))
    return t.replace(",", ".") if lg == "id" else t


def fmt_date(key, lg="en", year=False):
    y, m, d = key.split("-")
    mo = T(lg, "months")[int(m) - 1]
    wd = T(lg, "weekdays")[C.weekday(C.key_index(key))]
    return "%s %d %s%s" % (wd, int(d), mo, (" " + y) if year else "")


def fmt_stamp(t_ms, z, lg="en"):
    k = C.day_key(C.day_index(t_ms, z))
    return "%s %s" % (fmt_date(k, lg, True), C.clock(t_ms, z)[:5])


def delta_text(now, before, lg="en"):
    if before <= 0:
        return ""
    r = (now - before) / before
    return ("+" if r >= 0 else "−") + "%d%%" % round(abs(r) * 100)


# ---------------------------------------------------------------- tiny charts made of characters
_BLOCKS = "▏▎▍▌▋▊▉█"
_SPARK = "▁▂▃▄▅▆▇█"
_SHADE = " ░▒▓█"


def hbar(frac, width):
    frac = max(0.0, min(1.0, frac))
    full = int(frac * width)
    rest = frac * width - full
    part = _BLOCKS[int(rest * 8) - 1] if int(rest * 8) > 0 and full < width else ""
    return ("█" * full + part).ljust(width)


def spark(vals, lo=0.0):
    if not vals:
        return ""
    hi = max(vals)
    if hi <= lo:
        return _SPARK[0] * len(vals)
    return "".join(_SPARK[min(7, int((v - lo) / (hi - lo) * 7.999))] for v in vals)


def shade(v, hi):
    if hi <= 0 or v <= 0:
        return _SHADE[0]
    return _SHADE[1 + min(3, int(v / hi * 3.999))]


# ---------------------------------------------------------------- one line per event
def ev_text(ev, lg="en"):
    """[t, z, kind, small] -> 'HH:MM:SS  symbol  words'."""
    t, z, k, s = ev
    lab = T(lg, "k_" + k) if ("k_" + k) in TX["en"] else k
    title = s.get("title") or ""
    art = s.get("artist") or ""
    who = (title + (" - " + art if art else "")) if title else ""
    if k == "play":
        body = who
    elif k == "fin":
        body = "%s  (%s, %s %s)" % (who, T(lg, "w_" + s.get("why", "left")) if ("w_" + s.get("why", "left")) in TX["en"] else s.get("why", ""), T(lg, "heard").lower(), fmt_mmss(s.get("listened", 0)))
    elif k in ("pause", "resume"):
        body = ((who + "  @ ") if who else "@ ") + fmt_mmss(s.get("pos", 0)) if "pos" in s else who
    elif k == "seek":
        body = "%s → %s" % (fmt_mmss(s.get("from", 0)), fmt_mmss(s.get("to", 0))) if "from" in s else ""
    elif k == "vol":
        body = "%s → %s%%" % (s.get("from", "?"), s.get("to", "?"))
    elif k == "mode":
        names = MODE_NAMES.get(lg, MODE_NAMES["en"])
        try:
            body = names[int(s.get("to"))]
        except (TypeError, ValueError, IndexError):
            body = str(s.get("name", s.get("to", "")))
    elif k == "fav":
        body = ("+ " if s.get("on") else "− ") + (title or "")
    elif k == "sleep":
        body = ("on, " + fmt_dur(s.get("left", 0), lg)) if s.get("on") else "off"
    elif k == "queue":
        body = "%s" % s.get("n", "")
    elif k == "fx":
        body = str(s.get("label", ""))
    elif k == "lyrics":
        body = str(s.get("source") or "-")
    elif k == "ui":
        w = s.get("what", "")
        body = w + ((": " + str(s.get("from")) + " → " + str(s.get("to"))) if "from" in s else "")
    elif k == "sess":
        body = "%s %s" % (s.get("surface", ""), s.get("ver", ""))
    elif k == "end":
        body = "%s  (%s)" % (fmt_dur(s.get("up", 0), lg), T(lg, "w_" + s.get("why", "exit")) if ("w_" + s.get("why", "exit")) in TX["en"] else s.get("why", ""))
    elif k == "gap":
        body = fmt_dur(s.get("s", 0), lg)
    elif k == "clock":
        body = "%+d s" % round(s.get("delta", 0))
    else:
        body = ""
    return "%s  %s  %-14s %s" % (C.clock(t, z), SYMBOL.get(k, "·"), lab, body.strip())


# ---------------------------------------------------------------- the written definitions
def definitions(lg="en"):
    if lg == "id":
        return """CARA ANGKA DIHITUNG  (aturan ini ada di rofpalys_analytics_calc.py; log mentah tidak pernah berubah, angka bisa dihitung ulang kapan saja)

Waktu mendengar     Detik saat audio benar-benar berjalan: posisi lagu maju dan tidak dijeda. Diukur dari posisi lagu, bukan dari jam saja, jadi jeda,
                    lompat (seek) dan lagu yang macet tidak ikut terhitung. Potongan yang melewati tengah malam atau pergantian jam dibagi tepat.
Rofpalys dibuka     Dari program dibuka sampai ditutup (GUI, terminal, atau daemon), per hari, per jam, dan per cara pakai.
Dimulai             Satu lagu mulai diputar (termasuk ulang otomatis dan ulang manual).
Diputar (default)   Gaya Last.fm: didengar minimal 30 detik DAN (setengah lagu ATAU 4 menit). Lagu harus lebih panjang dari 30 detik.
  Gaya Spotify      Didengar minimal 30 detik.
  Setiap mulai      Semua lagu yang dimulai.
Selesai             Lagu berakhir sendiri, atau kamu sampai 90% lagu.
Dilewati            Ditinggalkan sebelum 30 detik didengar (batas yang sama dengan Spotify).
Hari beruntun       Hari berturut-turut dengan minimal 1 menit mendengar. Hari ini tidak memutus rantai sampai hari ini berakhir.
Mendengar nonstop   Rangkaian mendengar yang jedanya paling lama 5 menit.
Hari                Hari kalender lokal dengan selisih UTC yang tercatat pada saat kejadian; jadi pindah zona waktu tidak merusak hari lama.

MUTU DATA (gaya ALCOA+: jelas asalnya, terbaca, tercatat saat kejadian, asli, akurat, lengkap, konsisten, awet, tersedia)
- Setiap kejadian ditulis sekali, ke log tambah-saja (append-only), dengan nomor urut, waktu UTC dalam milidetik, selisih zona, id sesi, dan hash berantai
  (SHA-256 dari catatan sebelumnya + isi catatan). Mengubah/menghapus satu baris memutus rantai dan terlihat di `rofpalys stats verify`.
- Penulisan memakai satu panggilan tulis per baris; kejadian penting di-fsync. Jika program mati mendadak, baris setengah jadi dikarantina (tidak dihapus
  diam-diam), sesi yang menggantung ditutup dengan tanda "dipulihkan", dan waktu terakhir yang sudah tercatat tetap dihitung.
- Durasi dihitung dari jam monoton (kebal terhadap perubahan jam sistem); lompatan jam dicatat. Saat program tertahan (mis. HP tidur), celahnya dicatat
  dan waktu hanya dihitung bila posisi lagu membuktikan bahwa audio berjalan (ditandai "disimpulkan").
- Ketelitian: pengambilan contoh tiap 0,5 detik; kesalahan batas paling banyak sekitar 0,5 detik per awal/akhir potongan.
- `rofpalys stats verify --deep` menghitung ulang semuanya dari log mentah dan membandingkannya dengan ringkasan tersimpan.
- Semua data tinggal di perangkat ini. Tidak ada yang dikirim ke mana pun.
- Ini pencatatan tingkat audit, bukan alat medis dan tidak bersertifikat."""
    return """HOW THE NUMBERS ARE COUNTED  (the rules live in rofpalys_analytics_calc.py; the raw log never changes, the numbers can be recomputed any time)

Listening time      Seconds in which audio really ran: the song position advanced and it was not paused. It is measured from the song position, not
                    from the clock alone, so pauses, seeks and stalled playback are not counted. Stretches across midnight or an hour change are split exactly.
Rofpalys open       From the program starting to it closing (GUI, terminal or daemon), per day, per hour and per way of using it.
Started             One song began to play (also automatic repeat and manual repeat).
Plays (default)     Last.fm style: listened at least 30 s AND (half the song OR 4 minutes). The song must be longer than 30 s.
  Spotify style     Listened at least 30 s.
  Every start       Every song that began.
Completed           The song ended by itself, or you reached 90 % of it.
Skipped             Left before 30 s were heard (the same limit Spotify uses).
Streak              Consecutive days with at least 1 minute of listening. Today does not break a streak until today is over.
Listening bout      A run of listening whose pauses are at most 5 minutes long.
Day                 The local calendar day with the UTC offset that was valid at that moment, so a time-zone change never damages old days.

DATA QUALITY (ALCOA+ style: attributable, legible, contemporaneous, original, accurate, complete, consistent, enduring, available)
- Every event is written once, to an append-only log, with a sequence number, the UTC time in milliseconds, the UTC offset, a session id and a chained hash
  (SHA-256 of the previous record + this record). Changing or deleting one line breaks the chain and shows up in `rofpalys stats verify`.
- One write call per line; important events are fsynced. If the program dies suddenly, a half-written line is quarantined (never silently deleted), the dangling
  session is closed with a "recovered" mark, and the last time that was recorded still counts.
- Durations come from the monotonic clock (immune to system clock changes); clock jumps are recorded. When the program is held up (the phone sleeping, say)
  the gap is recorded and time is only counted when the song position proves the audio kept running (marked "inferred").
- Precision: sampling every 0.5 s; the boundary error is at most about 0.5 s per start / end of a stretch.
- `rofpalys stats verify --deep` recomputes everything from the raw log and compares it with the saved summary.
- All data stays on this device. Nothing is sent anywhere.
- This is audit-grade logging, not a medical device and not certified."""


# ---------------------------------------------------------------- text reports
def _row(cells, widths, aligns):
    out = []
    for c, w, a in zip(cells, widths, aligns):
        c = str(c)
        out.append(c.ljust(w) if a == "l" else c.rjust(w))
    return "  ".join(out).rstrip()


def _cut(s, n):
    s = str(s)
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"


def render_overview(ov, lg="en", top_songs=None, top_artists=None, width=78):
    L = []
    t = lambda k: T(lg, k)
    L.append("ROFPALYS  %s    %s" % (t("stats").upper(), fmt_stamp(ov["now"], ov["z"], lg)))
    L.append("─" * min(width, 78))
    heads = [("today", "today"), ("yesterday", "yesterday"), ("w7", "7d"), ("d30", "30d"), ("month", "month"), ("year", "year"), ("all", "all")]
    w0 = max(len(t(h)) for h, _ in heads)
    L.append(_row(["", t("listening"), t("appopen"), t("plays"), t("starts"), t("songs")], [w0, 11, 12, 8, 8, 6], "lrrrrr"))
    for h, key in heads:
        x = ov[key]
        L.append(_row([t(h), fmt_dur(x["listen"], lg), fmt_dur(x["open"], lg), fmt_num(x["lastfm"], lg), fmt_num(x["starts"], lg), fmt_num(x["songs"], lg)], [w0, 11, 12, 8, 8, 6], "lrrrrr"))
    L.append("")
    s = ov["streak"]
    L.append("%s: %d %s   %s: %d %s%s" % (t("current_streak"), s["current"], t("days"), t("longest_streak"), s["longest"], t("days"),
                                          ("  (%s → %s)" % (s["longest_from"], s["longest_to"])) if s["longest"] else ""))
    L.append("%s: %s   %s: %s" % (t("avg_active"), fmt_dur(ov["avg_active_day"], lg), t("avg_cal"), fmt_dur(ov["avg_calendar_day"], lg)))
    L.append("%s: %s   %s: %s   %s: %s" % (t("completion"), fmt_pct(ov["completion"]), t("skip_rate"), fmt_pct(ov["skip_rate"]), t("repeat"), fmt_pct(ov["repeat_ratio"])))
    if ov["peak_hour"] is not None:
        L.append("%s: %02d:00   %s: %s" % (t("peak_hour"), ov["peak_hour"], t("peak_day"), T(lg, "weekdays_long")[ov["peak_weekday"]]))
        sh = ov["shares"]
        L.append("%s %s   %s %s   %s %s   %s %s" % (t("night"), fmt_pct(sh["night"]), t("morning"), fmt_pct(sh["morning"]), t("afternoon"), fmt_pct(sh["afternoon"]), t("evening"), fmt_pct(sh["evening"])))
    for title, rows in ((t("top_songs"), top_songs), (t("top_artists"), top_artists)):
        if rows:
            L.append("")
            L.append(title + "  (" + t("all") + ")")
            mx = max(r["plays"] for r in rows) or 1
            for i, r in enumerate(rows, 1):
                nm = r["title"] + (" - " + r["artist"] if r.get("artist") and r["title"] != r["artist"] else "")
                L.append("%2d. %s %4d  %s" % (i, hbar(r["plays"] / mx, 14), r["plays"], _cut(nm, width - 28)))
    return "\n".join(L)


def render_rank(rows, lg="en", width=78, level="song"):
    t = lambda k: T(lg, k)
    if not rows:
        return t("none")
    mx = max(r["plays"] for r in rows) or 1
    L = []
    name_w = max(10, width - 52)
    L.append(_row(["#", t("title") if level == "song" else (t("artist") if level == "artist" else t("folders")), "", t("plays"), t("time"), t("done"), t("skips"), t("last")],
                  [3, name_w, 10, 6, 9, 5, 5, 6], "llrrrrrr"))
    for i, r in enumerate(rows, 1):
        nm = r["title"] + (" - " + r["artist"] if level == "song" and r.get("artist") else "")
        last = C.day_key(C.day_index(r["last"], 0))[5:] if r.get("last") else ""
        L.append(_row([i, _cut(nm, name_w), hbar(r["plays"] / mx, 10), r["plays"], fmt_dur(r["time"], lg), fmt_pct(r["completion"]), fmt_pct(r["skip_rate"]), last],
                      [3, name_w, 10, 6, 9, 5, 5, 6], "llrrrrrr"))
    return "\n".join(L)


def render_days(rows, lg="en", width=78):
    t = lambda k: T(lg, k)
    mx = max([r["listen"] for r in rows] + [1])
    L = [_row([t("date"), "", t("listening"), t("appopen"), t("plays"), t("starts"), t("title")], [11, 18, 10, 10, 6, 6, 20], "llrrrrl")]
    for r in rows:
        L.append(_row([fmt_date(r["key"], lg), hbar(r["listen"] / mx, 18), fmt_dur(r["listen"], lg) if r["listen"] else "·", fmt_dur(r["open"], lg) if r["open"] else "·",
                       r["plays"] or "·", r["starts"] or "·", _cut((r["top"] or "").rsplit("/", 1)[-1], max(10, width - 60))], [11, 18, 10, 10, 6, 6, 20], "llrrrrl"))
    L.append("")
    L.append(spark([r["listen"] for r in rows]) + "   " + t("listening"))
    return "\n".join(L)


def render_hours(tot, lg="en"):
    t = lambda k: T(lg, k)
    h = tot["hours"]
    mx = max(h) or 1
    L = [t("per_hour")]
    for i in range(24):
        L.append("%02d  %s %s" % (i, hbar(h[i] / mx, 40), fmt_dur(h[i], lg) if h[i] else ""))
    return "\n".join(L)


def render_heat(hm, lg="en"):
    t = lambda k: T(lg, k)
    m, n = hm["m"], hm["n"]
    avg = [[(m[w][h] / n[w]) if n[w] else 0.0 for h in range(24)] for w in range(7)]
    hi = max(max(r) for r in avg)
    L = [t("heat"), "    " + "".join(("%-6s" % ("%02d" % h)) if h % 3 == 0 else "" for h in range(24))]      # a label every 3 hours = every 6 characters
    for w in range(7):
        L.append("%-4s" % T(lg, "weekdays")[w] + "".join(shade(avg[w][h], hi) * 2 for h in range(24)))
    L.append("    " + _SHADE[1] + " < " + _SHADE[2] + " < " + _SHADE[3] + " < " + _SHADE[4] + "   (" + t("avg_cal").lower() + ")")
    return "\n".join(L)


def render_records(rc, lg="en"):
    t = lambda k: T(lg, k)
    L = []
    if rc["best_day"][0]:
        L.append("%-28s %s  (%s)" % (t("best_day"), fmt_dur(rc["best_day"][1], lg), fmt_date(rc["best_day"][0], lg, True)))
    if rc["most_plays_day"][0]:
        L.append("%-28s %d  (%s)" % (t("most_plays"), rc["most_plays_day"][1], fmt_date(rc["most_plays_day"][0], lg, True)))
    if rc["most_repeats"][0] and rc["most_repeats"][2] > 1:
        L.append("%-28s %dx  (%s, %s)" % (t("most_repeat"), rc["most_repeats"][2], _cut(rc["most_repeats"][1].rsplit("/", 1)[-1], 30), fmt_date(rc["most_repeats"][0], lg, True)))
    if rc["longest_bout"][1] > 0:
        a, lis, pl = rc["longest_bout"]
        L.append("%-28s %s, %d %s" % (t("longest_bout"), fmt_dur(lis, lg), pl, t("songs").lower()))
    if rc["longest_session"][1] > 0:
        a, sec, surf, pl = rc["longest_session"]
        L.append("%-28s %s  (%s)" % (t("longest_session"), fmt_dur(sec, lg), surf))
    if rc["most_open_day"][0]:
        L.append("%-28s %s  (%s)" % (t("most_open"), fmt_dur(rc["most_open_day"][1], lg), fmt_date(rc["most_open_day"][0], lg, True)))
    s = rc["streak"]
    L.append("%-28s %d %s" % (t("longest_streak"), s["longest"], t("days")))
    return "\n".join(L) if L else t("none")


def render_quality(q, ver, lg="en"):
    t = lambda k: T(lg, k)
    L = ["%-28s %s" % (t("integrity"), (t("chain_ok") if ver.get("ok") else t("chain_bad")) + "  (n=%s, %s)" % (ver.get("records", 0), ver.get("head", "")))]
    L.append("%-28s %s" % (t("records_n"), fmt_num(q["records"], lg)))
    if q.get("first"):
        L.append("%-28s %s" % (t("since"), fmt_stamp(q["first"], ver.get("z", 0), lg)))
    L.append("%-28s %s (%s)" % (t("observed"), fmt_dur(q["live_s"], lg), fmt_pct(q["live_share"])))
    L.append("%-28s %s (%s)" % (t("inferred"), fmt_dur(q["inferred_s"], lg), fmt_pct(q["inferred_share"])))
    L.append("%-28s %d  (%s)" % (t("gaps"), q["gaps"], fmt_dur(q["gap_s"], lg)))
    L.append("%-28s %d" % (t("clocks"), q["clock_jumps"]))
    L.append("%-28s %d" % (t("recovered"), q["recovered"]))
    for e in ver.get("errors", [])[:5]:
        L.append("!! " + e)
    for e in ver.get("warnings", [])[:5]:
        L.append("?  " + e)
    L.append(t("not_medical"))
    return "\n".join(L)


def render_events(evs, lg="en", n=40):
    return "\n".join(ev_text(e, lg) for e in evs[-n:]) if evs else T(lg, "none")


def render_kinds(kinds, lg="en"):
    if not kinds:
        return ""
    mx = max(kinds.values()) or 1
    L = [T(lg, "kinds")]
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        nm = k.split(":")[0]
        lab = T(lg, "k_" + nm) if ("k_" + nm) in TX["en"] else nm
        if k.startswith("ui:"):
            lab += " " + k[3:]
        L.append("  %-22s %s %d" % (lab, hbar(v / mx, 20), v))
    return "\n".join(L)


# END-OF-FILE rofpalys_analytics_text.py

