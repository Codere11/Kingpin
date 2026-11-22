"""doctor.py -- medicine, the doctor's station, and the medical record.

The mind is discovered, not inspected: the first medicine a person receives
sets `medicines_received > 0` and `mental_known = True` permanently.  This
module holds the rules; village._work_doctor drives the actual walk-and-work.
"""

from __future__ import annotations

MEDICINE = "medicine"
MEDICINE_HUT = "medicine_hut"
DOCTOR_JOB = "doctor"

# One medicine: one tobacco, one dried mushroom, one alcoholic drink.
RECIPE = {
    "tobacco": 1,
    "dried_mushroom": 1,
}
ALCOHOL = ("beer", "liqueur", "mezcal", "govbeer")

MEDICINE_SECONDS = 8.0
DOSES_PER_BATCH = 1

# The doctor does not scan the whole camp every frame. Two seconds is enough
# for a patient to be found, and keeps hundreds of people cheap.
SCAN_SECONDS = 2.0
