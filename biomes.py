"""Biomes from two slow noise axes: temperature and humidity.

Both are large, smooth fields, so a biome is a wide region and neighbouring
biomes fade into one another over a long gradient -- you never get tundra
touching desert. The biome is a 3x3 table over (temperature, humidity); the
ground colour is a continuous blend of the four nearest table entries, and the
tree species/density blend the same way.
"""

from __future__ import annotations

import numpy as np
from palette import rich

from noise import fbm, value_noise

TEMP_SCALE = 0.0000031          # ~300 km features: five times larger biomes
HUM_SCALE = 0.0000037

# rows: cold -> hot ; cols: dry -> wet
GRID = (
    ("tundra",  "steppe",   "taiga"),
    ("prairie", "woodland", "marsh"),
    ("desert",  "savanna",  "jungle"),
)

# ground palette per biome: a shadow tone and a highlight tone
BIOMES = {
    "tundra":   {"dark": rich((198, 208, 218)), "lite": rich((236, 242, 249))},
    "steppe":   {"dark": rich((132, 138, 128)), "lite": rich((184, 186, 174))},
    "taiga":    {"dark": rich((186, 198, 210)), "lite": rich((224, 232, 242))},
    "prairie":  {"dark": rich((126, 134, 68)),  "lite": rich((188, 184, 104))},
    "woodland": {"dark": rich((74, 112, 56)),   "lite": rich((136, 166, 86))},
    "marsh":    {"dark": rich((64, 90, 58)),    "lite": rich((112, 138, 82))},
    "desert":   {"dark": rich((206, 184, 128)), "lite": rich((240, 224, 168))},
    "savanna":  {"dark": rich((150, 138, 72)),  "lite": rich((198, 184, 108))},
    "jungle":   {"dark": rich((44, 90, 52)),    "lite": rich((96, 152, 72))},
}


def surface(t, h) -> str:
    """What is on top of the ground: snow, sand, marsh or grass."""
    t = float(t)
    h = float(h)
    if t < 0.32:
        return "snow"
    if t > 0.62 and h < 0.34:
        return "sand"
    if h > 0.72:
        return "marsh"
    return "grass"


def snow_factor(t, h) -> float:
    return _ssf((0.34 - float(t)) / 0.12)


def sand_factor(t, h) -> float:
    return _ssf((float(t) - 0.60) / 0.12) * _ssf((0.36 - float(h)) / 0.14)


def snow_factor_array(t, h):
    return _ssfa((0.34 - np.asarray(t, np.float32)) / 0.12)


def sand_factor_array(t, h):
    t = np.asarray(t, np.float32)
    h = np.asarray(h, np.float32)
    return _ssfa((t - 0.60) / 0.12) * _ssfa((0.36 - h) / 0.14)


def biome_name(t, h) -> str:
    r = int(round(max(0.0, min(1.0, float(t))) * 2))
    c = int(round(max(0.0, min(1.0, float(h))) * 2))
    return GRID[r][c]


def predator_kind(t, h) -> str:
    """What hunts here: white wolves in snow, snakes in desert, hyenas in
    savanna, ordinary wolves elsewhere."""
    if surface(t, h) == "snow":
        return "white_wolf"
    name = biome_name(t, h)
    if name == "desert":
        return "snake"
    if name == "savanna":
        return "hyena"
    return "wolf"


def rabbit_fur(t, h) -> str:
    if surface(t, h) == "snow":
        return "white"
    name = biome_name(t, h)
    if name in ("desert", "savanna"):
        return "yellow"
    if name in ("woodland", "jungle", "marsh"):
        return "brown"
    return "grey"


def npc_wear(t, h) -> str:
    """How the locals dress: furs in the snow, Tuareg robes in the desert,
    striped cloth on the savanna, ordinary clothes elsewhere."""
    if surface(t, h) == "snow":
        return "fur"
    name = biome_name(t, h)
    if name == "desert":
        return "tuareg"
    if name == "savanna":
        return "zebra"
    return "normal"


def crop_kinds(t, h):
    """(food crop, leaf crop) grown in this biome. The two crop slots stay the
    same everywhere -- only what grows in them changes."""
    if surface(t, h) == "snow":
        return "berries", "mushroom"
    if biome_name(t, h) == "desert":
        return "cactus", "agave"
    return "wheat", "plant"


def can_plant(t, h, kind: str) -> bool:
    """Whether a crop can be grown here. Desert crops won't take in the snow,
    and snow crops won't take in the desert."""
    if surface(t, h) == "snow" and kind in ("cactus", "agave"):
        return False
    if biome_name(t, h) == "desert" and kind in ("berries", "mushroom"):
        return False
    # COTTON is a savanna crop: it grows where it naturally grows wild.
    if kind == "cotton" and biome_name(t, h) != "savanna":
        return False
    # CHILI grows on the savanna and in the woodland.
    if kind == "chili" and biome_name(t, h) not in ("savanna", "woodland"):
        return False
    return True


_SNOW_COL = {"dark": rich((214, 224, 236)), "lite": rich((247, 251, 255))}
_SAND_COL = {"dark": rich((212, 192, 138)), "lite": rich((244, 230, 178))}


def _ssf(x: float) -> float:
    x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
    return x * x * (3.0 - 2.0 * x)


def _ssfa(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _override(which: str, base, t, h):
    """Force real snow / real sand so the ground matches what sits on it."""
    t = np.asarray(t, np.float32)
    h = np.asarray(h, np.float32)
    snow = _ssfa((0.34 - t) / 0.12)[..., None]
    snow_col = np.array(_SNOW_COL[which], np.float32)
    base = base * (1.0 - snow) + snow_col * snow
    sand = (_ssfa((t - 0.60) / 0.12) * _ssfa((0.36 - h) / 0.14))[..., None]
    sand_col = np.array(_SAND_COL[which], np.float32)
    return base * (1.0 - sand) + sand_col * sand


def _override_scalar(which: str, base, t: float, h: float):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else float(t))
    h = 0.0 if h < 0.0 else (1.0 if h > 1.0 else float(h))
    snow = _ssf((0.34 - t) / 0.12)
    sc = _SNOW_COL[which]
    out = [base[i] * (1.0 - snow) + sc[i] * snow for i in range(3)]
    sand = _ssf((t - 0.60) / 0.12) * _ssf((0.36 - h) / 0.14)
    sc2 = _SAND_COL[which]
    return [out[i] * (1.0 - sand) + sc2[i] * sand for i in range(3)]

# trees that grow in each biome (relative weights)
TREES = {
    "tundra":   {"bare": 1.0},
    "steppe":   {"bare": 0.30, "broadleaf": 0.70},
    "taiga":    {"conifer": 1.0},
    "prairie":  {"broadleaf": 1.0},
    "woodland": {"broadleaf": 1.0},
    "marsh":    {"broadleaf": 1.0},
    "desert":   {"cactus": 1.0},
    "savanna":  {"acacia": 1.0},
    "jungle":   {"jungle": 1.0},
}

# overall tree density per biome
DENSITY = {
    "tundra": 0.09, "steppe": 0.16, "taiga": 1.10,
    "prairie": 0.24, "woodland": 1.00, "marsh": 0.55,
    "desert": 0.14, "savanna": 0.34, "jungle": 1.30,
}

_DARK = np.array([[BIOMES[GRID[r][c]]["dark"] for c in range(3)]
                  for r in range(3)], dtype=np.float32)
_LITE = np.array([[BIOMES[GRID[r][c]]["lite"] for c in range(3)]
                  for r in range(3)], dtype=np.float32)


# The climate never changes, and the whole game asks the same questions over
# and over -- the foliage test, the ground, the woods -- every single frame.
# Memoised by position: same answer, computed once.
_TEMP_MEMO: dict = {}
_HUM_MEMO: dict = {}
_MEMO_CAP = 500000


# THE COUNTRY THE GAME HAS ALWAYS HAD, AND THE WASTE AROUND IT.
# The settled world is the old square; the map is five times its area, and
# everything past the old edge is frozen. It gets colder the further out you
# go, so the rim is snow, rock and almost nothing to eat.
CORE_HALF = 100000.0
WASTE_HALF = CORE_HALF * 5.0               # five times the LENGTH: 500,000


def _waste_ramp(x, y) -> float:
    """There is no frozen rim any more. The whole west is normal, infinite
    procedural country; the only border is the Minecraft-style world border at
    a huge figure. This stays as a named hook so callers that asked about the
    waste (wild plants, density) simply get the answer 'none'."""
    return 0.0


def temperature(x, y, seed: int):
    if isinstance(x, np.ndarray) or isinstance(y, np.ndarray):
        xs = np.asarray(x, np.float32)
        ys = np.asarray(y, np.float32)
        v = fbm(xs * TEMP_SCALE, ys * TEMP_SCALE, seed + 71, octaves=3)
        t = np.clip((v - 0.5) * 2.15 + 0.5, 0.0, 1.0)
        return t
    key = (float(x), float(y), seed)
    got = _TEMP_MEMO.get(key)
    if got is None:
        v = fbm(np.float32(key[0]) * TEMP_SCALE, np.float32(key[1]) * TEMP_SCALE,
                seed + 71, octaves=3)
        got = float(np.clip((float(v) - 0.5) * 2.15 + 0.5, 0.0, 1.0))
        if len(_TEMP_MEMO) < _MEMO_CAP:
            _TEMP_MEMO[key] = got
    return got


def humidity(x, y, seed: int):
    if isinstance(x, np.ndarray) or isinstance(y, np.ndarray):
        v = fbm(np.asarray(x, np.float32) * HUM_SCALE + 1731.0,
                np.asarray(y, np.float32) * HUM_SCALE - 921.0, seed + 29, octaves=2)
        return np.clip((v - 0.5) * 1.9 + 0.5, 0.0, 1.0)
    key = (float(x), float(y), seed)
    got = _HUM_MEMO.get(key)
    if got is None:
        v = fbm(np.float32(key[0]) * HUM_SCALE + 1731.0,
                np.float32(key[1]) * HUM_SCALE - 921.0, seed + 29, octaves=2)
        got = float(np.clip((float(v) - 0.5) * 1.9 + 0.5, 0.0, 1.0))
        if len(_HUM_MEMO) < _MEMO_CAP:
            _HUM_MEMO[key] = got
    return got


def _cell(t, h):
    """Integer corner + fractional position within the 3x3 table."""
    t = np.clip(np.asarray(t, np.float32), 0.0, 1.0) * 2.0
    h = np.clip(np.asarray(h, np.float32), 0.0, 1.0) * 2.0
    t0 = np.clip(np.floor(t), 0.0, 1.0)
    h0 = np.clip(np.floor(h), 0.0, 1.0)
    return t0.astype(np.intp), h0.astype(np.intp), t - t0, h - h0


def blend_array(which: str, t, h):
    """Ground colour channel-blended over the table. Returns shape (..., 3)."""
    arr = _DARK if which == "dark" else _LITE
    t = np.asarray(t, np.float32)
    h = np.asarray(h, np.float32)
    r0, c0, ft, fh = _cell(t, h)
    ft = ft[..., None]
    fh = fh[..., None]
    v00 = arr[r0, c0]
    v01 = arr[r0, c0 + 1]
    v10 = arr[r0 + 1, c0]
    v11 = arr[r0 + 1, c0 + 1]
    top = v00 * (1.0 - fh) + v01 * fh
    bot = v10 * (1.0 - fh) + v11 * fh
    return _override(which, top * (1.0 - ft) + bot * ft, t, h)


def mix(t: float, h: float):
    """Scalar blend: (dark_rgb, lite_rgb, species_weights, density)."""
    ti = min(2.0, max(0.0, float(t)) * 2.0)
    hi = min(2.0, max(0.0, float(h)) * 2.0)
    r0 = min(1, int(ti))
    c0 = min(1, int(hi))
    ft = ti - r0
    fh = hi - c0
    dark = [0.0, 0.0, 0.0]
    lite = [0.0, 0.0, 0.0]
    spec: dict[str, float] = {}
    density = 0.0
    for dr, dc, wt, wh in ((0, 0, 1 - ft, 1 - fh), (0, 1, 1 - ft, fh),
                           (1, 0, ft, 1 - fh), (1, 1, ft, fh)):
        w = wt * wh
        if w <= 0.0:
            continue
        name = GRID[r0 + dr][c0 + dc]
        info = BIOMES[name]
        for i in range(3):
            dark[i] += info["dark"][i] * w
            lite[i] += info["lite"][i] * w
        density += DENSITY[name] * w
        for sp, sw in TREES[name].items():
            spec[sp] = spec.get(sp, 0.0) + sw * w
    return (_override_scalar("dark", dark, t, h),
            _override_scalar("lite", lite, t, h), spec, density)


def pick_species(spec: dict, rng) -> str:
    total = sum(spec.values())
    if total <= 0.0:
        return "broadleaf"
    roll = rng.random() * total
    acc = 0.0
    for name, weight in spec.items():
        acc += weight
        if roll <= acc:
            return name
    return next(iter(spec))
