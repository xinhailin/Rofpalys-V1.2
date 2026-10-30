#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - CyroKayAI turbo: use every core of the processor (phone, tablet, PC) for the heavy maths of the lyrics
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""What this file does, and what it cannot do - honestly:
  * It finds out how many CPU cores the device has (and, where Android lets us read it, which ones are the fast 'big' cores) and splits the
    heavy work (the Fourier analysis of a song, many songs at once) over them.  numpy does the number crunching in compiled code (on a phone
    numpy / OpenBLAS use the NEON vector unit of the ARM processor); this file makes sure all cores take part.
  * It lowers the priority of the background work a little (os.nice) so the music and the screen stay smooth while CyroKayAI thinks.
  * It does NOT use the phone's GPU or NPU: Python in Termux has no way to reach them. 'Working directly with the processor' means: all cores,
    vectorised maths, no wasted work (caches), and a benchmark so you can SEE the speed (rofpalys lyrics bench).
Everything falls back to plain single-core Python when threads / processes are not allowed, so it can never break the player."""
import os
import sys
import time

__version__ = "1.0"
_CACHE = {}


def _int_env(name, default):
    try:
        v = int(os.environ.get(name, ""))
        return v if v > 0 else default
    except ValueError:
        return default


def logical_cores():
    """CPU cores the operating system lets this program use."""
    if "n" in _CACHE:
        return _CACHE["n"]
    n = 0
    try:
        n = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        pass
    if not n:
        n = os.cpu_count() or 1
    _CACHE["n"] = max(1, n)
    return _CACHE["n"]


def core_speeds():
    """[max MHz per core] when the kernel tells us (Linux / Android: /sys/devices/system/cpu/cpuN/cpufreq/cpuinfo_max_freq), else []."""
    if "speeds" in _CACHE:
        return _CACHE["speeds"]
    out = []
    for i in range(64):
        p = "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq" % i
        try:
            with open(p) as f:
                out.append(int(f.read().strip()) // 1000)
        except (OSError, ValueError):
            if i >= logical_cores() + 2:
                break
    _CACHE["speeds"] = out
    return out


def big_cores():
    """Number of fast cores (phones mix 'big' and 'little' cores). Without frequency information every core counts as big."""
    sp = core_speeds()
    if len(sp) < 2 or max(sp) <= 0:
        return logical_cores()
    top = max(sp)
    return max(1, sum(1 for s in sp if s >= 0.6 * top))


def workers(limit=8):
    """How many parallel workers to use: ROFPALYS_CORES wins, else the fast cores (at least 1, at most `limit`). On a 1-core device: 1."""
    forced = _int_env("ROFPALYS_CORES", 0)
    if forced:
        return max(1, min(forced, 64))
    return max(1, min(limit, big_cores() if logical_cores() > 2 else logical_cores()))


def tune_blas():
    """Let numpy's linear algebra (OpenBLAS / NEON) use the same number of threads. Must run BEFORE numpy is imported to be certain; later it is a hint."""
    n = str(workers())
    for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(k, n)


def be_nice(level=5):
    """Lower the priority of THIS process / thread a bit so playback never stutters (best effort; ignored where not allowed)."""
    if os.environ.get("ROFPALYS_NICE", "1") == "0":
        return False
    try:
        os.nice(level)
        return True
    except (AttributeError, OSError):
        return False


def parallel_map(fn, items, mode="thread", n=None, stop=None):
    """[fn(x) for x in items] spread over the cores. mode 'thread' (numpy releases the GIL in its heavy loops, no copying) or 'process'.
    If anything about parallel work fails (no semaphores on this phone, no fork, ...), the rest is done in this thread: the result is always complete."""
    items = list(items)
    n = n or workers()
    if n <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    out = [None] * len(items)
    done = [False] * len(items)
    try:
        if mode == "process" and hasattr(os, "fork"):
            from concurrent.futures import ProcessPoolExecutor
            import multiprocessing
            ex = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("fork"))
        else:
            from concurrent.futures import ThreadPoolExecutor
            ex = ThreadPoolExecutor(max_workers=n)
        with ex:
            futs = [ex.submit(fn, x) for x in items]
            for i, f in enumerate(futs):
                if stop and stop():
                    for g in futs:
                        g.cancel()
                    break
                out[i] = f.result()
                done[i] = True
    except Exception:
        pass
    for i, x in enumerate(items):                       # whatever did not finish (or the pool could not start) is done here
        if not done[i] and not (stop and stop()):
            out[i] = fn(x)
    return out


def describe():
    sp = core_speeds()
    s = "%d core(s) usable" % logical_cores()
    if sp:
        s += "  ·  speeds MHz: %s  ·  fast cores: %d" % (",".join(str(x) for x in sp), big_cores())
    return s + "  ·  CyroKayAI workers: %d" % workers()


def _np_info():
    try:
        import numpy as np
        info = getattr(np, "show_config", None)
        return "numpy %s" % np.__version__
    except Exception:
        return "numpy: not installed (pkg install python-numpy) -> simple single-core mode"


def bench(path=None, quiet=False):
    """Measure the speed. Returns {'cores', 'serial_s', 'parallel_s', 'speedup', ...}. Without a song a generated test signal (60 s) is used."""
    try:
        import numpy as np
    except Exception:
        np = None
    res = {"cores": logical_cores(), "workers": workers(), "numpy": np is not None}
    if np is None:
        if not quiet:
            print(describe() + "\n" + _np_info())
        return res
    n = 16000 * 60
    rng = np.random.default_rng(3)
    x = (rng.standard_normal(n).astype(np.float32) * 0.1)
    win = np.hanning(1024).astype(np.float32)
    view = np.lib.stride_tricks.sliding_window_view(x, 1024)[::320]
    blocks = [(s, min(len(view), s + 512)) for s in range(0, len(view), 512)]

    def work(b):
        fr = view[b[0]:b[1]] * win
        X = np.fft.rfft(fr, axis=1)
        P = X.real * X.real + X.imag * X.imag
        ac = np.fft.irfft(np.sqrt(P) ** 0.67, n=1024, axis=1)
        return float(ac[:, 1].sum())
    t0 = time.time()
    for b in blocks:
        work(b)
    res["serial_s"] = time.time() - t0
    t0 = time.time()
    parallel_map(work, blocks, "thread", workers())
    res["parallel_s"] = time.time() - t0
    res["speedup"] = res["serial_s"] / max(1e-6, res["parallel_s"])
    res["seconds_of_music_per_second"] = 60.0 / max(1e-6, res["parallel_s"])
    if not quiet:
        print(describe())
        print(_np_info())
        print("Fourier analysis of 60 s of music: 1 core %.3f s  ·  %d workers %.3f s  ->  x%.2f faster  (%.0f s of music analysed per second)" %
              (res["serial_s"], workers(), res["parallel_s"], res["speedup"], res["seconds_of_music_per_second"]))
    return res


if __name__ == "__main__":
    bench()
    sys.exit(0)

# END-OF-FILE rofpalys_CyroKayAI_turbo.py

