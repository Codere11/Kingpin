"""mind.py -- ONE MAN'S INNER LIFE, in one place.

The mood decides everything: whether he chats, flies into an insulting spree,
or goes and punches the man he hates most. Extracted whole out of village.py's
tick, so the tick only asks "what does his mind say this frame?".
"""
import economy
import comm
import brawl


def step(npc, now, dt, others, combat=None):
    """The man's whole mind, one step: spree, brawl, chat."""
    _spree(npc, now, dt)
    _brawl(npc, now, dt, others, combat)
    _chat(npc, now, dt, others, combat)


def _spree(npc, now, dt):
    """THE FIRST BREAK: below 30 mood, every 30s a coin-flip begins an
    insulting spree. When it ends, catharsis lifts him +40 for three days."""
    _spree_until = getattr(npc, "_spree_until", 0.0)
    if _spree_until and now >= _spree_until:
        npc._spree_until = 0.0
        npc.mood = min(100.0, float(getattr(npc, "mood", 50.0)) + comm.CATHARSIS_MOOD)
        npc._catharsis_end = now + comm.CATHARSIS_DAYS * economy.DAY_LENGTH
        economy._note("SPREE-END %s catharsis +%d"
                      % (getattr(npc, "name", "?"), comm.CATHARSIS_MOOD))
    _cath_end = getattr(npc, "_catharsis_end", 0.0)
    if _cath_end and now >= _cath_end:
        npc.mood = max(0.0, float(getattr(npc, "mood", 50.0)) - comm.CATHARSIS_MOOD)
        npc._catharsis_end = 0.0
    if not getattr(npc, "_spree_until", 0.0) \
            and float(getattr(npc, "mood", 50.0)) < comm.SPREE_MIN_MOOD \
            and not getattr(npc, "asleep", False) \
            and not getattr(npc, "in_interior", False):
        npc._spree_timer = getattr(npc, "_spree_timer", comm.SPREE_ROLL_SECONDS) - dt
        if npc._spree_timer <= 0.0:
            npc._spree_timer = comm.SPREE_ROLL_SECONDS
            if npc.rng.random() < 0.5:
                npc._spree_until = now + comm.SPREE_SECONDS
                economy._note("SPREE-BEGIN %s mood %.0f"
                              % (getattr(npc, "name", "?"), npc.mood))


def _brawl(npc, now, dt, others, combat):
    """THE MAJOR BREAK: below 20 mood, a man goes and punches the one he
    hates most -- and a brawl spreads from there."""
    try:
        brawl.step(npc, now, dt, others, combat)
    except Exception:
        pass


def _chat(npc, now, dt, others, combat):
    """A WORD NOW AND THEN: praise, insult or threaten a neighbour, on a
    cooldown. Relayed to the frame so the player can hear it."""
    npc._chat_timer = getattr(npc, "_chat_timer", 0.0) - dt
    if npc._chat_timer <= 0.0 and not getattr(npc, "asleep", False) \
            and not getattr(npc, "in_interior", False):
        npc._chat_timer = 0.7
        try:
            _res = comm.npc_try_chat(npc, others, now)
            if _res is not None:
                economy._note("CHAT day %d  %-18s %-8s %s"
                              % (int(now / economy.DAY_LENGTH),
                                 getattr(npc, "name", "?"),
                                 _res[1], getattr(_res[0], "name", "?")))
                # RELAY IT TO THE FRAME: if the player is there, he hears it.
                try:
                    if combat is not None and hasattr(combat, "chats"):
                        combat.chats.append((round(npc.x, 1),
                                             round(npc.y, 1),
                                             _res[1],
                                             getattr(npc, "name", "?")))
                except Exception:
                    pass
        except Exception:
            pass
