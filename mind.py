"""mind.py -- ONE MAN'S INNER LIFE, in one place.

The mood decides everything: whether he chats, flies into an insulting spree,
or goes and punches the man he hates most. Extracted whole out of village.py's
tick, so the tick only asks "what does his mind say this frame?".
"""
import economy

CONSUME_BREAK_SECONDS = 180.0   # the raised breaking point lasts three minutes


def apply_mood(npc, delta, reason=None):
    """THE ONLY WRITER OF MOOD. Every effect in the world -- a kind word, a
    corpse, the day's coin, a fight won -- lands here, so the clamp and the
    arithmetic live in one place. `reason` feeds the log; high-volume callers
    (socio, grief) pass None and stay silent."""
    old = float(getattr(npc, "mood", 50.0))
    new = max(0.0, min(100.0, old + delta))
    npc.mood = new
    if reason:
        economy._note("MOOD %-16s %+.0f (%.0f -> %.0f) %s"
                      % (getattr(npc, "name", "?"), delta, old, new, reason))
    return new


def break_threshold(npc):
    """The mood below which a man BREAKS. Consumption raises it +10 at a time:
    the fix lifts his mood and his breaking point together, so a satisfied man
    still snaps at the same underlying misery -- the smoke does not save him."""
    return float(getattr(npc, "_break_off", 0.0))


def consume(npc, item, now, genetics=None):
    """A man has started to savour something (a smoke, a drink, a chew).
    Three minutes of it: +10 mood and +10 to his breaking point, both
    temporary. The item is in his hand until he finishes it."""
    old = float(getattr(npc, "mood", 50.0))
    # Alcohol is a smaller base lift than a cigar or a mushroom.  Its local
    # strain can push that *base* up by as much as 300% (a +15 mood swing on
    # a base of 5), which is what makes a famous local brew matter.
    _base = 5.0 if item in economy.DRINKS else 10.0
    _extra = 0.0
    if isinstance(genetics, dict):
        try:
            _extra = _base * max(0.0, float((genetics.get("bonuses") or {}).get("mood", 0.0)))
        except Exception:
            _extra = 0.0
    apply_mood(npc, _base + _extra, reason="consumed %s" % item)
    if item == "chili_beer" or (isinstance(genetics, dict)
                                and genetics.get("full_heal")):
        try:
            npc.health = npc.max_health
        except Exception:
            pass
    if item == "chili_mezcal" or (isinstance(genetics, dict)
                                  and genetics.get("max_health")):
        if not getattr(npc, "chili_mezcal_used", False):
            try:
                old_max = float(npc.max_health)
                import stats as _stats
                _base = float(_stats.body_for(npc))
                if _base > 0.0:
                    npc.health_mult = (old_max / _base) * 1.35
                npc.max_health = old_max * 1.35
                npc.health = min(npc.max_health,
                                 float(npc.health) + (npc.max_health - old_max))
                npc.chili_mezcal_used = True
            except Exception:
                pass
    if isinstance(genetics, dict):
        _b = genetics.get("bonuses") or {}
        if item == "banana_liqueur":
            try:
                if float(_b.get("speed", 0.0)) > 0.0:
                    npc.speed_boost_t = max(
                        float(getattr(npc, "speed_boost_t", 0.0)), 180.0)
            except Exception:
                pass
        if item == "chocolate" and not getattr(npc, "cocoa_tasted", False):
            try:
                _bonus = max(0.0, min(0.50, float(_b.get("stamina", 0.0))))
                if _bonus > 0.0:
                    npc.max_stamina = float(npc.max_stamina) * (1.0 + _bonus)
                    npc.stamina = npc.max_stamina
                    npc.cocoa_tasted = True
            except Exception:
                pass
    new = float(getattr(npc, "mood", 50.0))
    # remember exactly how much mood the fix actually added, so the expiry
    # removes exactly that (clamping at 100 cannot leak a phantom 10).
    npc._consume_mood_off = float(getattr(npc, "_consume_mood_off", 0.0)) + (new - old)
    if item in ("beer", "liqueur", "mezcal", "govbeer",
                "chili_beer", "chili_mezcal", "banana_liqueur"):
        npc.drunk_level = float(getattr(npc, "drunk_level", 0.0) or 0.0) + 1.0
    elif item == "dried_mushroom":
        npc.high_level = float(getattr(npc, "high_level", 0.0) or 0.0) + 1.0
    # REMEMBER THE FIRST TASTE.  A product is not a need until he has tried
    # it at least once; economy.wants()/needs() read this before opening a
    # craving for cigars, beer, liqueur or mezcal.
    try:
        tried = getattr(npc, "consumed_items", None)
        if not isinstance(tried, dict):
            tried = npc.consumed_items = {}
        tried[item] = int(tried.get(item, 0) or 0) + 1
    except Exception:
        pass
    npc._break_off = float(getattr(npc, "_break_off", 0.0)) + 10.0
    npc._break_off_until = now + CONSUME_BREAK_SECONDS
    try:
        import mood as _mood
        _mood.add_thought(npc, "luxury", 6.0, now, CONSUME_BREAK_SECONDS)
        if getattr(npc, "break_state", "normal") == "normal":
            if float(getattr(npc, "high_level", 0.0) or 0.0) >= 3.0:
                _mood.set_break(npc, "tripping", now, seconds=60.0)
            elif float(getattr(npc, "drunk_level", 0.0) or 0.0) >= 3.0:
                _mood.set_break(npc, "drunk", now, seconds=60.0)
    except Exception:
        pass


def _consume_expire(npc, now):
    """Three minutes are up: the mood and the raised breaking point both
    come back down."""
    _until = getattr(npc, "_break_off_until", 0.0)
    if _until and now >= _until:
        _off = float(getattr(npc, "_consume_mood_off", 0.0))
        if _off:
            apply_mood(npc, -_off, reason="consumption wore off")
        npc._consume_mood_off = 0.0
        npc._break_off = 0.0
        npc._break_off_until = 0.0


def step(npc, now, dt, others, combat=None):
    """The man's inner life after the old town simulation was removed.

    Consuming a luxury still lifts the mood and the temporary breaking point.
    The old spree/brawl/chat loops belonged to the legacy town lattice and are
    gone; the new mood/break system in `mood.py` replaces them.
    """
    _consume_expire(npc, now)
