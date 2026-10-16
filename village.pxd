# cython: language_level=3
#
# THE MAN, DECLARED TO THE COMPILER.
#
# Cython compiles village.py either way, but a plain Python class stores every
# attribute in a dict, and a dict lookup is ~50 ns. A man's step does sixty of
# them, twice a second each, for two and a half thousand men -- which is most
# of what the frame was paying for.
#
# Declaring them here makes each of these a C struct member: reading npc.x
# becomes a pointer offset instead of a hash. The logic in village.py does not
# change at all -- not one line -- because this file only says WHERE the fields
# live, never what the code does with them.
#
#   * __dict__ is declared FIRST and deliberately. Everything NOT listed here
#     still lives in a normal dict, so the attribute a fence gives a village,
#     or the stock the economy gives a man, keeps working exactly as before.
#     Nothing can break from an attribute I failed to anticipate -- it just
#     stays dynamic, which is what it was.
#   * public, not cdef-only, because the rest of the game is Python and reads
#     these fields directly: npc.hunger, npc.x, npc.alive.
#   * Only fields with an unambiguous numeric type are typed. Anything whose
#     first value is None or a string is left in the dict, because a C double
#     cannot hold None and I would rather lose a little speed than a behaviour.
#   * Fields that already exist as CLASS attributes on NPC (asleep,
#     in_interior, trade_state, loan_clock, home_house, wants_product,
#     wants_drink, use_fx) are deliberately NOT declared: their class default
#     is part of the game's behaviour -- trade_state defaults to "none", and a
#     C field would default to None, which is a different game.
#
# Pickling is unaffected: __dict__ plus the declared fields round-trip, which
# the world cache depends on.

cdef class NPC:
    cdef dict __dict__

    # -- position and body ------------------------------------------------
    cdef public double x
    cdef public double y
    cdef public double _px
    cdef public double _py
    cdef public double radius
    cdef public double spacing
    cdef public double speed
    cdef public double base_speed
    cdef public double stamina
    cdef public double max_stamina

    # -- hunger and health ------------------------------------------------
    cdef public double hunger
    cdef public double yearning
    cdef public double health
    cdef public double max_health
    cdef public double hit_flash
    # The working face's timer. Same shape as hit_flash and for the same
    # reason: it is read and written for EVERY man EVERY frame, and a dict
    # lookup on the hot path is exactly what this file exists to remove.
    cdef public double work_flash
    # ...and the war face's, on the same terms. One blow raises it and
    # anything can happen next, so it outlives the swing that set it.
    cdef public double attack_flash
    cdef public double hurt_flash
    cdef public double bleed
    cdef public double drip_timer
    cdef public double panic
    cdef public double flee

    # -- timers -----------------------------------------------------------
    cdef public double pause
    cdef public double stuck
    cdef public double _steer_timer
    cdef public double _trade_timer
    cdef public double _shop_timer
    cdef public double chop_timer
    cdef public double produce_acc
    cdef public double attack_cd
    cdef public double reload_timer
    cdef public double tool_uses

    # -- what he is -------------------------------------------------------
    cdef public double shoot_skill
    cdef public double combat_speed
    cdef public bint alive
    cdef public bint aggro
    cdef public bint defender
    cdef public bint is_commander
    cdef public bint is_soldier
    cdef public bint on_duty
    cdef public bint king_run
    cdef public bint _dead_settled
