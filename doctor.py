"""doctor.py -- Phase 0 skeleton for the camp doctor.

Nothing is produced or prescribed yet.  The constants are here so the lab and
the later UI agree on one name and one recipe instead of inventing strings.
"""

from __future__ import annotations

MEDICINE = "medicine"
MEDICINE_HUT = "medicine_hut"
DOCTOR_JOB = "doctor"
DAILY_MEDICINE = 2

# One unit of medicine.  Ingredient names are placeholders until Phase 6
# decides what the world actually grows.
RECIPE = {
    "herb": 2,
    "water": 1,
}
