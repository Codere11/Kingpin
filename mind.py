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


def consume(npc, item, now):
    """A man has started to savour something (a smoke, a drink, a chew).
    Three minutes of it: +10 mood and +10 to his breaking point, both
    temporary. The item is in his hand until he finishes it."""
    old = float(getattr(npc, "mood", 50.0))
    apply_mood(npc, 10.0, reason="consumed %s" % item)
    new = float(getattr(npc, "mood", 50.0))
    # remember exactly how much mood the fix actually added, so the expiry
    # removes exactly that (clamping at 100 cannot leak a phantom 10).
    npc._consume_mood_off = float(getattr(npc, "_consume_mood_off", 0.0)) + (new - old)
    npc._break_off = float(getattr(npc, "_break_off", 0.0)) + 10.0
    npc._break_off_until = now + CONSUME_BREAK_SECONDS


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
