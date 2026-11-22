#!/usr/bin/env python3
"""Fast headless check of the doctor's make-and-deliver loop."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def main():
    import industry
    import village

    hut = industry.Workplace("medicine_hut", 0.0, 0.0, 1234)
    camp = SimpleNamespace(
        x=0.0, y=0.0, g=None, people=[], ledger_goods={
            "tobacco": 1, "dried_mushroom": 1, "beer": 1},
        farmers=[], warriors=[], handlers=[], workers=[], loggers=[],
        artisans=[], researchers=[], doctors=[], miners=[], smiths=[],
        weavers=[], spicemen=[], gunsmiths=[], unemployed=[])
    g = SimpleNamespace(placed_work=[hut], built_chests=[], now=0.0,
                        cam_x=-500.0, cam_y=-500.0, vw=1280, vh=720)
    camp.g = g

    doc = village.NPC(0.0, 0.0, 11, name="Tala", npc_id="doctor_test",
                      role="Doctor")
    doc.native = True
    doc.native_role = "doctor"
    doc.job = "doctor"
    doc.native_camp = camp

    patient = village.NPC(6.0, 0.0, 12, name="Peta", npc_id="patient_test",
                          role="Farmer")
    patient.native = True
    patient.native_role = "farmer"
    patient.job = "farmer"
    patient.native_camp = camp
    patient.max_health = 100
    patient.health = 1
    patient.medicines_received = 0
    patient.mental_known = False
    camp.people = [doc, patient]
    camp.farmers = [patient]

    # The sign-post assignment must be able to put a man in the doctor role.
    import colony
    sign = SimpleNamespace(doctors=1)
    colony._assign_jobs(g, camp, sign)
    assert doc in camp.doctors, "sign-post did not assign a doctor"

    for _ in range(300):
        doc._work_doctor(0.1)
        if patient.medicines_received:
            break

    assert patient.medicines_received == 1, \
        "medicine not delivered: %r" % patient.medicines_received
    assert patient.mental_known, "medical record not unlocked"
    assert patient.health == patient.max_health, "patient not healed"
    assert camp.ledger_goods.get("tobacco", 0) == 0
    assert camp.ledger_goods.get("dried_mushroom", 0) == 0
    assert camp.ledger_goods.get("beer", 0) == 0
    print("DOCTOR SELFTEST: PASS -- produced one medicine and unlocked the record")


if __name__ == "__main__":
    main()
