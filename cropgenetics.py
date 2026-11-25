"""cropgenetics.py -- settlement crop strains and their slow local drift.

Every settlement/crop strain rolls 1-3 targets.  Every harvest advances ALL
of them.  A three-target strain is rare and simply better ground; there is no
"one target per harvest" balancing rule.

Strains are plain data on the camp, so they save with the settlement.  Crop
lots carry a copy of the strain in their item genetics field.
"""

from __future__ import annotations

import hashlib
import random


# target -> (maximum bonus, label)
COMMON_TARGETS = (
    ("yield", 0.35, "Yield"),
    ("sell", 0.50, "Alcohol value"),
    ("seeds", 0.35, "Seed yield"),
    ("mood", 0.40, "Alcohol mood"),
    ("drought", 0.50, "Drought resistance"),
    ("rain", 0.50, "Rain resistance"),
)
QUALITY_TARGETS = (
    ("quality_s", 6, "Quality S"),
    ("quality_ss", 7, "Quality SS"),
    ("quality_sss", 8, "Quality SSS"),
)

QUALITY_CROPS = ("plant", "mushroom", "agave", "chili")
CROP_NAMES = {
    "wheat": "Wheat", "berries": "Berries", "cactus": "Cactus",
    "plant": "Tobacco", "mushroom": "Red Mushroom", "agave": "Agave",
    "cotton": "Cotton", "chili": "Chili",
}

STEP = 0.02                  # one harvest, 2% of the target per trait
NAME_AT = 0.50               # average progress at which the local name appears


def _quality_crop(crop: str) -> bool:
    return crop in QUALITY_CROPS


def _target_rows(crop: str):
    rows = list(COMMON_TARGETS)
    if _quality_crop(crop):
        rows += list(QUALITY_TARGETS)
    return rows


def _seed(camp, crop: str) -> int:
    raw = "%s|%s|%s" % (getattr(camp, "_save_uid", ""),
                        getattr(camp, "seed", 0), crop)
    return int.from_bytes(hashlib.blake2b(raw.encode("utf-8"),
                                          digest_size=8).digest(), "big")


def ensure(camp, crop: str):
    """Get or create this camp's strain for one crop."""
    if camp is None:
        return None
    strains = getattr(camp, "crop_strains", None)
    if not isinstance(strains, dict):
        strains = camp.crop_strains = {}
    got = strains.get(crop)
    if isinstance(got, dict):
        return got
    rng = random.Random(_seed(camp, crop))
    roll = rng.random()
    count = 1 if roll < 0.25 else (2 if roll < 0.80 else 3)
    rows = _target_rows(crop)
    picked = rng.sample(rows, min(count, len(rows)))
    strain = {
        "crop": crop,
        "settlement": getattr(camp, "name", "Settlement"),
        "targets": [row[0] for row in picked],
        "progress": {row[0]: 0.0 for row in picked},
        "harvests": 0,
        "generation": 1,
        "name": "",
    }
    strains[crop] = strain
    return strain


def advance(camp, crop: str):
    """One harvest from this settlement advances every target a little."""
    strain = ensure(camp, crop)
    if strain is None:
        return None
    for target in strain.get("targets", ()):
        strain["progress"][target] = min(
            1.0, float(strain["progress"].get(target, 0.0)) + STEP)
    strain["harvests"] = int(strain.get("harvests", 0)) + 1
    strain["generation"] = int(strain.get("generation", 1)) + 1
    vals = list(strain.get("progress", {}).values())
    avg = sum(vals) / max(1, len(vals))
    if avg >= NAME_AT and not strain.get("name"):
        label = CROP_NAMES.get(crop, crop.title())
        strain["name"] = "%s %s" % (getattr(camp, "name", "Settlement"), label)
    return strain


def genetics(camp, crop: str) -> dict | None:
    """The portable crop-lot copy.  It never references the camp object."""
    strain = ensure(camp, crop)
    if strain is None:
        return None
    return {
        "crop": crop,
        "settlement": strain.get("settlement", ""),
        "targets": list(strain.get("targets", ())),
        "progress": dict(strain.get("progress", {})),
        "harvests": int(strain.get("harvests", 0)),
        "generation": int(strain.get("generation", 1)),
        "name": strain.get("name", ""),
        "quality_cap": quality_cap(strain),
        "bonuses": bonuses(strain),
    }


def _target_progress(strain, target: str) -> float:
    return max(0.0, min(1.0, float(strain.get("progress", {}).get(target, 0.0))))


def bonuses(strain) -> dict:
    rows = {row[0]: row[1] for row in COMMON_TARGETS}
    return {
        "yield": rows["yield"] * _target_progress(strain, "yield"),
        "sell": rows["sell"] * _target_progress(strain, "sell"),
        "seeds": rows["seeds"] * _target_progress(strain, "seeds"),
        "mood": rows["mood"] * _target_progress(strain, "mood"),
        "drought": rows["drought"] * _target_progress(strain, "drought"),
        "rain": rows["rain"] * _target_progress(strain, "rain"),
    }


def yield_mult(strain) -> float:
    return 1.0 + bonuses(strain)["yield"]


def seed_mult(strain) -> float:
    return 1.0 + bonuses(strain)["seeds"]


def quality_cap(strain) -> int:
    """Base crop quality is A (5); only a quality target can lift the cap."""
    cap = 5
    for target, grade, _label in QUALITY_TARGETS:
        p = _target_progress(strain, target)
        if p > 0.0:
            cap = max(cap, 5 + int(round(p * (grade - 5))))
    return min(8, cap)


def cap_quality(strain, grade: int) -> int:
    return max(0, min(quality_cap(strain), int(grade)))


def display_name(stack) -> str:
    gen = getattr(stack, "genetics", None)
    if isinstance(gen, dict) and gen.get("name"):
        return str(gen["name"])
    return getattr(getattr(stack, "defn", None), "name", "item")
