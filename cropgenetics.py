"""cropgenetics.py -- settlement crop strains and their slow local drift.

Every settlement/crop strain rolls 1-3 targets.  Every harvest advances ALL
of them.  A three-target strain is rare and simply better ground; there is no
"one target per harvest" balancing rule.

Strains are plain data on the camp, so they save with the settlement.  Crop
lots carry a copy of the strain in their item genetics field.
"""

from __future__ import annotations

import hashlib
import math
import random


# target -> (maximum bonus, label)
COMMON_TARGETS = (
    ("yield", 0.35, "Yield"),
    ("sell", 0.50, "Local value"),
    ("seeds", 0.35, "Seed yield"),
    ("mood", 2.00, "Mood"),
    ("speed", 0.50, "Speed boost"),
    ("stamina", 0.50, "Max stamina"),
    ("drought", 0.50, "Drought resistance"),
    ("rain", 0.50, "Rain resistance"),
)
QUALITY_TARGETS = (
    ("quality_s", 6, "Quality S"),
    ("quality_ss", 7, "Quality SS"),
    ("quality_sss", 8, "Quality SSS"),
)

QUALITY_CROPS = ("plant", "mushroom", "agave", "chili", "pipeleaf", "cocoa",
                 "highflower")
CROP_NAMES = {
    "wheat": "Wheat", "berries": "Berries", "cactus": "Cactus",
    "plant": "Tobacco", "mushroom": "Red Mushroom", "agave": "Agave",
    "cotton": "Cotton", "chili": "Chili", "hardberry": "Hardberry",
    "pipeleaf": "Pipeleaf", "banana": "Banana", "cocoa": "Cocoa",
    "honeyflower": "Honeyflower", "highflower": "Highflower",
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
    """Apply a quality target as a grade floor, not merely a ceiling.

    A strain with the S target must actually be able to produce S; the base
    crop is A, so a target of S at high progress raises the result to S.
    """
    base = max(0, min(5, int(grade)))
    for target, target_grade, _label in QUALITY_TARGETS:
        p = _target_progress(strain, target)
        if p > 0.0:
            unlocked = 5 + int(math.floor(p * (target_grade - 5) + 0.5))
            base = max(base, unlocked)
    return min(8, base)


def artisan_mult(skill: float) -> float:
    """A maker's hands, on the same curve as a brewer's.

    Mid-skill (4/8) extracts 75%; max (8/8) extracts 150%.  Cigars and dried
    mushrooms use the artisan's hands, not the farmer's, for this scaling.
    """
    s = max(0.0, min(8.0, float(skill or 0.0)))
    if s <= 4.0:
        return 0.75
    return 0.75 + 0.75 * ((s - 4.0) / 4.0)


def brewer_mult(skill: float) -> float:
    """Kept as the alcohol name; the mathematics is the same."""
    return artisan_mult(skill)


def tree_genetics(kind: str, x: float, y: float, seed: int = 1) -> dict:
    """A portable local strain for fruit taken from a tropical palm.

    Bananas can carry the speed target; cocoa can carry the stamina target.
    Whether the target is actually unlocked is deterministic in the tree's
    position, so the same palm always gives the same lot.
    """
    raw = ("palm|%s|%.1f|%.1f|%s" % (kind, x, y, seed)).encode("utf-8")
    code = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big")
    rng = random.Random(code)
    target = "speed" if kind == "banana" else "stamina"
    label = "Banana" if kind == "banana" else "Cocoa"
    caps = {row[0]: row[1] for row in COMMON_TARGETS}
    targets = []
    progress = {}
    if rng.random() < 0.62:
        targets = [target]
        progress[target] = rng.uniform(0.05, 1.0)
    return {
        "crop": kind,
        "settlement": "Tropics",
        "source_name": "Tropics %s" % label,
        "name": "Tropics %s" % label,
        "targets": targets,
        "progress": progress,
        "harvests": 0,
        "generation": 1,
        "quality_cap": 5,
        "bonuses": {k: caps.get(k, 0.0) * progress.get(k, 0.0)
                    for k in progress},
    }


def extract(source, skill: float, product_name: str = "",
            kind: str = "alcohol", drink_name: str = "") -> dict | None:
    """Copy a crop strain into a made article, scaled by the maker's hands.

    Alcohol uses the brewer's curve; cigars and dried mushrooms use the
    artisan's.  The mathematics is deliberately identical -- one crop strain,
    one extraction rule, three trades.  The article keeps the source
    settlement/crop name and a scaled copy of every bonus.
    """
    if not isinstance(source, dict):
        return None
    if drink_name and not product_name:
        product_name = drink_name
    bonus = source.get("bonuses")
    if not isinstance(bonus, dict):
        # Old/manual records: derive from progress.
        p = source.get("progress") or {}
        bonus = {
            key: cap * max(0.0, min(1.0, float(p.get(key, 0.0))))
            for key, cap, _label in COMMON_TARGETS
        }
    mult = brewer_mult(skill) if kind == "alcohol" else artisan_mult(skill)
    scaled = {str(k): float(v) * mult for k, v in bonus.items()}
    src_name = source.get("name") or source.get("settlement") or ""
    name = ("%s %s" % (src_name, product_name)).strip()
    special = any(v >= 0.15 for v in scaled.values())
    return {
        "crop": source.get("crop", ""),
        "settlement": source.get("settlement", ""),
        "source_name": src_name,
        "name": name,
        "targets": list(source.get("targets", ())),
        "progress": dict(source.get("progress", {})),
        "bonuses": scaled,
        "kind": str(kind),
        "product": str(product_name),
        "quality_cap": int(source.get("quality_cap", 5) or 5),
        "maker_skill": float(skill or 0.0),
        "brewer_skill": float(skill or 0.0),
        "extraction": mult,
        "special": bool(special),
    }


def display_name(stack) -> str:
    gen = getattr(stack, "genetics", None)
    if isinstance(gen, dict) and gen.get("name"):
        return str(gen["name"])
    return getattr(getattr(stack, "defn", None), "name", "item")
