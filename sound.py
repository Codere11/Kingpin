"""sound.py -- one-shot sound effects.

Every sound is one-shot: each call to play() fires it once and never loops.
A missing file is silent, and a machine with no audio device is silent too --
sound can never crash the game or the headless tests.
"""
from __future__ import annotations

import os
import time

import pygame

_SOUND_DIR = os.path.join(os.path.dirname(__file__), "Sounds")

_mixer_ok = None          # None = not tried yet
_cache: dict = {}
_volume = 1.0
_muted = False
_last: dict = {}          # name -> time.time(), for throttled ambient sounds


def _ensure() -> bool:
    global _mixer_ok
    if _mixer_ok is None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            _mixer_ok = True
        except Exception:
            _mixer_ok = False
    return _mixer_ok


def _load(name: str):
    got = _cache.get(name)
    if got is not None:
        return got
    path = os.path.join(_SOUND_DIR, "%s.ogg" % name)
    snd = None
    try:
        if os.path.exists(path):
            snd = pygame.mixer.Sound(path)
    except Exception:
        snd = None
    _cache[name] = snd
    return snd


def play(name: str, volume: float = 1.0, min_gap: float = 0.0) -> None:
    """Fire a sound once. `min_gap` throttles the same name (ambient calls)."""
    if _muted or volume <= 0.0:
        return
    if min_gap > 0.0:
        now = time.time()
        if now - _last.get(name, 0.0) < min_gap:
            return
        _last[name] = now
    if not _ensure():
        return
    snd = _load(name)
    if snd is None:
        return
    try:
        snd.set_volume(min(1.0, max(0.0, volume * _volume)))
        snd.play()
    except Exception:
        pass


def set_volume(v: float) -> None:
    global _volume
    _volume = min(1.0, max(0.0, v))


def toggle_mute() -> bool:
    global _muted
    _muted = not _muted
    return _muted
