# cython: language_level=3
#
# THE MAN'S BODY, DECLARED TO THE COMPILER.
#
# economy.needs() is called once per man per tick -- 47,000 times a second --
# and it is the function that reads npc.hunger, npc.yearning, npc.stock,
# npc.asleep, npc.health and npc.max_health, over and over, by name.
#
# Declaring the parameter as NPC is the whole point. With npc typed, every
# npc.hunger inside becomes a C struct read instead of a dictionary lookup,
# and the function becomes a C function. Without it, Cython still looks the
# attribute up at runtime, at which point compiling the module buys nothing --
# which is exactly what my first attempt measured.
#
# economy.py does NOT import village, so this cimport cannot make a cycle:
# village imports economy, and this direction is compile-time only.

from village cimport NPC

cpdef bint needs(NPC npc, double dt)
