#!/usr/bin/env python3
"""The NPC card must not leak a mind that has no medical record."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


class Subject:
    name = "Test Subject"
    native = True
    job = "farmer"
    native_role = "farmer"
    mbti = "INTJ"
    traits = ["smart"]
    medicines_received = 0
    mental_known = False
    mood = 24.0
    mood_target = 18.0
    mood_thoughts = {"insulted": {"delta": -8.0, "stacks": 2}}
    break_state = "normal"
    skills = None


def main():
    import pygame
    pygame.init()
    import ui

    card = ui.PersonaCard()
    subject = Subject()

    lines = card._medical_lines(subject)
    text = " ".join(line for line, _color in lines)
    assert "No medical record" in text, text
    assert "Mood about 20" in text, text
    assert "Worse: Insulted -16" in text, text
    assert "MBTI" not in text, text
    assert "smart" not in text, text
    assert "INTJ" not in text, text

    subject.medicines_received = 1
    subject.mental_known = True
    lines = card._medical_lines(subject)
    text = " ".join(line for line, _color in lines)
    assert "MBTI INTJ" in text, text
    assert "smart" in text, text
    assert "Medicine 1" in text, text

    subject.medicines_received = 0
    subject.mental_known = False
    lines = card._medical_lines(subject)
    text = " ".join(line for line, _color in lines)
    assert "No medical record" in text, text
    print("CARD SELFTEST: PASS -- mind hidden without medicine, shown after it")


if __name__ == "__main__":
    main()
