#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Rofpalys - sound effects: equalizer presets, speed, "slowed + reverb", nightcore, normalize
# Copyright (C) 2026 rofpalys-nagiryu
# License: GPL-3.0-or-later  (see: rofpalys --license)
"""No UI, no engine. Turns the chosen effects into command-line arguments for the player that is used.
Works with mpv (best) and ffplay. Other players (mpg123, afplay, PyGame ...) cannot apply effects and simply play normally.
The filters are the standard ffmpeg audio filters (equalizer, aecho, dynaudnorm, atempo)."""

PRESETS = ("normal", "bass", "vocal", "treble", "lofi", "slowed", "nightcore")
REVERBS = ("off", "light", "hall")
SPEEDS = (0.5, 0.75, 0.85, 1.0, 1.15, 1.25, 1.5, 2.0)

# effect state (the engine saves these in the settings file)
preset, speed, reverb, normalize = "normal", 1.0, "off", False

_EQ = {
    "bass": ["equalizer=f=60:t=q:w=1:g=6", "equalizer=f=150:t=q:w=1:g=3"],
    "vocal": ["equalizer=f=120:t=q:w=1:g=-3", "equalizer=f=2000:t=q:w=1:g=3", "equalizer=f=4000:t=q:w=1:g=2"],
    "treble": ["equalizer=f=6000:t=q:w=1:g=4", "equalizer=f=10000:t=q:w=1:g=5"],
    "lofi": ["highpass=f=120", "lowpass=f=4500", "acompressor=threshold=0.15:ratio=3"],
}
_ECHO = {"light": "aecho=0.8:0.8:40:0.3", "hall": "aecho=0.8:0.88:60|120:0.4|0.25"}
SUPPORTED = ("mpv", "ffplay")


def supported(engine_name):
    return engine_name in SUPPORTED


def effective():
    """(speed, tape, reverb) after the preset: 'slowed' and 'nightcore' also change the speed. tape=True: the pitch follows the speed."""
    sp, rv, tape = speed, reverb, False
    if preset == "slowed":
        sp, rv, tape = min(sp, 0.82) if sp >= 1.0 else sp, ("hall" if rv == "off" else rv), True
    elif preset == "nightcore":
        sp, tape = max(sp, 1.25), True
    return sp, tape, rv


def is_active():
    sp, _, rv = effective()
    return preset != "normal" or abs(speed - 1.0) > 0.01 or reverb != "off" or normalize


def filters(for_ffplay=False):
    """List of ffmpeg audio filters for the current settings."""
    f = list(_EQ.get(preset, []))
    sp, tape, rv = effective()
    if rv in _ECHO:
        f.append(_ECHO[rv])
    if normalize:
        f.append("dynaudnorm=f=150:g=15")
    if for_ffplay and abs(sp - 1.0) > 0.01:
        f.append("atempo=%.3f" % sp)                    # ffplay has no speed option: tempo only, the pitch stays
    return f


def speed_for(engine_name):
    """How fast the song really plays with this player (1.0 if it cannot change speed). The engine needs it to keep the clock right."""
    if engine_name in SUPPORTED:
        return max(0.5, min(2.0, effective()[0]))
    return 1.0


def args_for(engine_name):
    """Extra arguments that go before the file name."""
    if not is_active() or engine_name not in SUPPORTED:
        return []
    sp, tape, _ = effective()
    if engine_name == "mpv":
        a = []
        if abs(sp - 1.0) > 0.01:
            a += ["--speed=%.3f" % sp, "--audio-pitch-correction=%s" % ("no" if tape else "yes")]
        f = filters()
        if f:
            a.append("--af=lavfi=[%s]" % ",".join(f))
        return a
    f = filters(for_ffplay=True)                        # ffplay
    return ["-af", ",".join(f)] if f else []


def label():
    parts = []
    if preset != "normal":
        parts.append(preset)
    sp, _, rv = effective()
    if abs(sp - 1.0) > 0.01 and preset not in ("slowed", "nightcore"):
        parts.append("%.2gx" % sp)
    if rv != "off" and preset != "slowed":
        parts.append("reverb")
    if normalize:
        parts.append("norm")
    return " + ".join(parts) or "off"


def cycle_preset():
    global preset
    preset = PRESETS[(PRESETS.index(preset) + 1) % len(PRESETS)]
    return preset


def reset():
    global preset, speed, reverb, normalize
    preset, speed, reverb, normalize = "normal", 1.0, "off", False


# END-OF-FILE rofpalys_effects.py

