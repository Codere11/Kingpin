"""workers.py -- THREE PROCESSES: THE FRAME, THE HUBS, THE SETTLEMENTS.

The frame is one core.  This file puts the simulation on the other two:

    PROCESS 0  (the parent)  the frame: input, the player, soldiers, bullets,
                             terrain, and every pixel that is drawn.
    PROCESS 1  (forked)      the 25 hubs, their people, and the free traders.
    PROCESS 2  (forked)      the 36 settlements, their books, and their people.

WHY PROCESSES AND NOT THREADS.  The one thing Python cannot do is run two
threads of this at once: the loop is Python and Cython and neither releases the
GIL.  A fork, on the other hand, was measured (forktest.py): the child wakes
holding the whole world, its copy is private, and it costs milliseconds.  So
the world is built once, in the parent, and forked -- twice.

THE CONTRACT, and it is the whole safety argument:

  * ONE OBJECT, ONE PROCESS.  A settlement man is stepped by process 2 and by
    nobody else.  A hub's man and a cart by process 1.  The player, the
    soldiers, the wolves, the bullets, the terrain: process 0.  No object is
    written by two processes, so there is nothing to race.
  * THE CHILD SENDS BACK WHAT THE FRAME NEEDS TO DRAW, and what the player's
    own menus read: each man's position, facing, hunger, health, the four face
    timers, what he is smoking, and -- for the men near the player -- his pack
    and purse.  Everything else (his trade, his plot, his debt, what he made
    today) stays in the child, where it is used.
  * THE PARENT SENDS THE PLAYER, and the events that cross the fence: a blow
    landed, a crime committed.  Nothing else.
  * ONE TICK, ONE MESSAGE, at the world's own 20 Hz.  The reply is read
    WITHOUT BLOCKING on the following frames, so the two children work while
    the frame is being drawn.  A lagging child costs latency, never a stall.
  * IF A CHILD DIES, `ok()` says so and main steps that lane itself, on the
    parent, exactly as before.  A dead worker is slower, not broken.

THE NOTICE BOARD IS NOT STALE. The frame draws it, so it ASKS: each tick it
names the towns on the board, and the lane answers with what they have going,
what their ledgers hold and what they pay. A hire and a sale are REQUESTS the
town performs; the frame is told what happened and moves the player's own pack
and purse (see Workers.watch/hire/sell). There are no elections and no
tournament to be stale -- both are deleted (Pivot.md S9.0: a dictatorship has
none).

ONE CREATION PATH IS STILL THE LANE'S: a child BORN in a settlement is created
by `Village.birth` in the other process, so the frame does not hold that man
until the next save and load. Births are gated by capacity, so a town at its
built size does not grow; a town that has lost men can. Closing it means the
lane sending the newborn's record and the frame building the man -- the next
thing to do, not something this file pretends it solved.
"""

from __future__ import annotations

import os
import time
import pickle
import select
import struct
import sys

import persist
# `threat_of` (both lanes) asks the village module who the player is. It was
# imported lazily inside start(), which is NOT this module's namespace -- so
# every call raised NameError, inside every man's tick, every tick. A lane
# whose men raise on the way to the fight never fights: measured, the error
# filled workers.log for the whole run.
try:
    import village as village_mod
except Exception:                      # a fork may import lazily; the lane
    village_mod = None                 # factories guard for None
import economy as economy_mod
import industry
import caravans as caravans_mod
import gate as gate_mod
import nemesis as nemesis_mod
import crop as crop_mod

LOG = os.path.join(persist.DIR, "workers.log")


def _log(text: str) -> None:
    try:
        os.makedirs(persist.DIR, exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(text + "\n")
    except Exception:
        pass


# -- framing ---------------------------------------------------------------
def _pack(obj) -> bytes:
    data = pickle.dumps(obj, 5)
    return struct.pack("<I", len(data)) + data


class _Pipe:
    """One end of a pipe: framed pickle messages, never blocking the frame."""

    def __init__(self, fd: int, big: bool = False) -> None:
        self.fd = fd
        self.buf = b""
        self.out = b""
        os.set_blocking(fd, False)
        if big:
            try:
                import fcntl
                fcntl.fcntl(fd, fcntl.F_SETPIPE_SZ, 1 << 20)
            except Exception:
                pass

    MAX_BACKLOG = 4 << 20          # 4 MB: beyond this the lane is not reading

    def send(self, obj) -> bool:
        """QUEUE IT. The bytes go out as fast as the pipe takes them.

        It used to write straight to the pipe and give up if the pipe was
        full -- but a write of a 100 KB frame into a 1 MB pipe can come back
        SHORT, and the rest of the frame was then dropped. The lane's reader
        counts a length prefix, so a partial frame is not a lost message: it is
        a DESYNCHRONISED STREAM, and every later message is parsed from the
        middle of the one before it.
        """
        if len(self.out) > self.MAX_BACKLOG:
            return False
        self.out += _pack(obj)
        self.pump()
        return True

    def pump(self) -> None:
        while self.out:
            try:
                n = os.write(self.fd, self.out)
            except BlockingIOError:
                return                      # the pipe is full; keep the rest
            except OSError:
                self.out = b""
                return
            if n <= 0:
                return
            self.out = self.out[n:]

    def recv(self) -> list:
        """Every complete message waiting, oldest first. Never blocks."""
        try:
            while True:
                chunk = os.read(self.fd, 1 << 20)
                if not chunk:
                    break
                self.buf += chunk
        except (BlockingIOError, InterruptedError):
            pass
        except OSError:
            return []
        out = []
        while len(self.buf) >= 4:
            n = struct.unpack("<I", self.buf[:4])[0]
            if len(self.buf) < 4 + n:
                break
            try:
                out.append(pickle.loads(self.buf[4:4 + n]))
            except Exception:
                pass
            self.buf = self.buf[4 + n:]
        return out

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


# -- the child -------------------------------------------------------------
def _child(req_fd: int, rep_fd: int, step) -> None:
    """Read a request, step the lane, send back what the frame needs."""
    # DIE WITH THE PARENT. An orphaned lane would go on simulating a world
    # nobody is watching, for ever, on a core.
    try:
        import ctypes, signal
        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGKILL)   # PR_SET_PDEATHSIG
    except Exception:
        pass
    buf = b""
    while True:
        try:
            chunk = os.read(req_fd, 1 << 16)
        except InterruptedError:
            continue
        except OSError:
            os._exit(0)
        if not chunk:
            os._exit(0)
        buf += chunk
        while len(buf) >= 4:
            n = struct.unpack("<I", buf[:4])[0]
            if len(buf) < 4 + n:
                break
            try:
                msg = pickle.loads(buf[4:4 + n])
            except Exception:
                buf = buf[4 + n:]
                continue
            buf = buf[4 + n:]
            try:
                out = step(msg)
            except BaseException as exc:
                import traceback
                _log("LANE ERROR %r\n%s" % (exc, traceback.format_exc()[-1200:]))
                out = {"error": repr(exc)[:200]}
            data = _pack(out)
            try:
                while data:
                    k = os.write(rep_fd, data)
                    data = data[k:]
            except OSError:
                os._exit(0)


# -- what the frame is told about a man ------------------------------------
# x, y, facing x/y, hunger, health, alive, asleep, indoors,
# work/attack/hurt/sly flashes, what he is smoking.
MAN_FIELDS = 13


def _man_record(n):
    fx, fy = n.facing
    fx_obj = getattr(n, "use_fx", None)
    return (round(n.x, 2), round(n.y, 2), round(fx, 3), round(fy, 3),
            round(n.hunger, 2), round(n.health, 2),
            bool(n.alive), bool(getattr(n, "asleep", False)),
            bool(getattr(n, "in_interior", False)),
            round(n.work_flash, 3), round(n.attack_flash, 3),
            round(n.hurt_flash, 3), round(n.sly_flash, 3),
            (fx_obj[0], round(fx_obj[1], 2)) if fx_obj else None)


def _apply_man(n, rec) -> None:
    was_alive = getattr(n, "alive", True)
    n.x, n.y, n.fx, n.fy, n.hunger, n.health, n.alive, n.asleep, \
        n.in_interior, n.work_flash, n.attack_flash, n.hurt_flash, \
        n.sly_flash, n.use_fx = rec
    if was_alive and not n.alive:
        # THE BODY STAYS WHERE HE FELL. He is dead in the lane, so the frame
        # learns it here, with his pack and his coat, and leaves a corpse.
        try:
            _facts = []
            if getattr(n, "secret_police", False):
                # A DEAD AGENT'S FOLDER: everything he was holding when he fell.
                try:
                    import nemesis as _nem
                    _facts = _nem.folder_messages(n)
                except Exception:
                    pass
            # HIS PACK, NOT JUST HIS LOOSE STOCK. A hired man's goods live in
            # `bag` (a real Inventory); reading only `stock` emptied every
            # worker's body on death.
            _pack = dict(getattr(n, "stock", None) or {})
            _rows = []
            try:
                _bag = getattr(n, "bag", None)
                for _s in (getattr(_bag, "slots", None) or ()):
                    if _s is not None:
                        _rows.append([_s.defn.id, int(_s.count), _s.quality,
                                      _s.payload if isinstance(_s.payload, str)
                                      else None])
            except Exception:
                _rows = []
            _W.deaths.append((round(n.x, 1), round(n.y, 1),
                              getattr(n, "name", "a body"),
                              _pack,
                              dict(getattr(n, "grade", None) or {}),
                              tuple(getattr(n, "clothing", (150, 110, 70))),
                              bool(getattr(n, "secret_police", False)),
                              _facts,
                              bool(getattr(n, "player_worker", False)),
                              _rows))
        except Exception:
            pass
    n.facing = (n.fx, n.fy)
    del n.fx, n.fy


# -- process 0's side ------------------------------------------------------
class Workers:
    def __init__(self) -> None:
        self.settle = None
        self.hub = None
        self.enabled = False
        self._events = []          # parent -> lanes, next request
        self._watch = []           # towns whose notice board is open
        self._reqs = []            # (rid, kind, ...) -- hire / sell requests
        self._cbs = {}             # rid -> the frame's callback
        self.offence_sink = None   # what to do with what a lane saw
        self.caught_sink = None    # ...and with a search that found something
        self._to_hub = []          # relay messages for the lane that walks carts
        # WHAT THE STALL IS, once a second: (x, y, name, on, goods, prices);
        # and what it sold, coming back the other way.
        self.stall = None
        self.stall_sink = None
        self.deaths: list = []        # bodies the frame has not made yet
        self._dmg_missed: dict = {}
        self._rid = 0
        self._frame = 0

    # -- the two lanes are started by start(), below ----------------------
    def _spawn(self, name, make_step, men, towns, extras):
        req_r, req_w = os.pipe()
        rep_r, rep_w = os.pipe()
        pid = os.fork()
        if pid == 0:                       # ---------------- the child
            for fd in (req_w, rep_r):
                try:
                    os.close(fd)
                except OSError:
                    pass
            # THE FACTORY RUNS HERE, IN THE CHILD. It installs the hooks that
            # notice what the lane does -- and a hook installed in the parent
            # would fire on the frame's own work as well.
            try:
                _step = make_step()
            except BaseException:
                import traceback
                _log("LANE %s FACTORY FAILED\n%s"
                     % (name, traceback.format_exc()[-900:]))
                os._exit(1)
            _child(req_r, rep_w, _step)
            os._exit(0)
        for fd in (req_r, rep_w):
            try:
                os.close(fd)
            except OSError:
                pass
        w = _Lane(name, pid, req_w, rep_r, men, towns, extras)
        _log("LANE %s started pid %d: %d men, %d towns"
             % (name, pid, len(men), len(towns)))
        return w

    def ok(self) -> bool:
        return (self.enabled
                and self.settle is not None and not self.settle.dead()
                and self.hub is not None and not self.hub.dead())

    # -- one world tick ----------------------------------------------------
    def tick(self, now, dt, phase, night, player, soldiers=()) -> None:
        """Hand the world's clock to both lanes. Never blocks."""
        if not self.enabled:
            return
        self._frame += 1
        events = self._events
        self._events = []
        msg = {"now": now, "dt": dt, "phase": phase, "night": bool(night),
               "player": (round(player.x, 2), round(player.y, 2),
                          bool(getattr(player, "wanted", False)),
                          bool(getattr(player, "dead", False))),
               "events": events,
               # THE SOLDIERS, so a refugee on the road can be cut down by
               # one. Position, nation, whether he is hunting.
               "soldiers": [(round(s.x, 1), round(s.y, 1),
                             getattr(s, "nation", None),
                             bool(getattr(s, "hostile", False)))
                            for s in soldiers if getattr(s, "alive", False)],
               # THE NOTICE BOARD, WHICH IS THE FRAME'S AND THE TOWN'S AT
               # ONCE: the frame draws it, the lane owns what it says. The
               # frame asks for the towns on it; the lane answers in the reply.
               "watch": list(self._watch),
               "req": list(self._reqs)}
        msg["stall"] = self.stall
        sent = True
        sent_settle = True
        # WHAT THE SEAT PAID THE FREE TRADERS GOES TO THE LANE THAT OWNS THEM.
        if self._to_hub:
            msg["relay"] = list(self._to_hub)
        if self.settle is not None and not self.settle.dead():
            sent_settle = self.settle.send(msg)
            sent = sent_settle and sent
        if self.hub is not None and not self.hub.dead():
            if self.hub.send(msg):
                # THE RELAY IS SPENT WHEN IT IS DELIVERED, not when both sends
                # happen to succeed -- otherwise a full pipe re-sent the
                # crown's stipend and the carts were paid three times.
                self._to_hub = []
        if sent:
            self._reqs = []
        for _lane in (self.settle, self.hub):
            if _lane is not None:
                _lane.req.pump()          # the frame keeps moving out

    def apply(self, world, combat) -> None:
        """Take whatever the lanes have finished. Never blocks."""
        if not self.enabled:
            return
        for lane in (self.settle, self.hub):
            if lane is None:
                continue
            frames = lane.recv()
            if not frames:
                continue
            msg = frames[-1]
            if msg.get("error") is not None:
                _log("LANE %s returned an error: %s" % (lane.name, msg["error"]))
                continue
            for n, rec in zip(lane.men, msg.get("men", ())):
                _apply_man(n, rec)
            for tx, ty, kind, planted, grow in msg.get("plots", ()):
                world.set_plot(tx, ty, kind, planted, grow)
            for f in msg.get("fires", ()):
                combat.fire(f[0], f[1], f[2], f[3], owner="enemy",
                            damage=f[4], team=f[5], spread=f[6])
            for i, vals in msg.get("towns", ()):
                if i < len(lane.towns):
                    v = lane.towns[i]
                    (v.provoked, v.battle, v.chaos, v.conquered,
                     v.nation, v.search_t, v.ledger_coins) = vals
            for ti, posts, ledger, prices in msg.get("watch", ()):
                if ti < len(lane.towns):
                    v = lane.towns[ti]
                    v._lanes_posts = list(posts)      # what the board shows
                    v.ledger_coins = ledger
                    v.prices.update(prices)
            if msg.get("census"):
                try:
                    import plog
                    items = sorted(msg["census"].items(),
                                   key=lambda kv: -kv[1][1])
                    plog.log("PURSES", " ".join(
                        "%s:%dmen/%d" % (k, int(v[0]), int(v[1]))
                        for k, v in items))
                except Exception:
                    pass
            if msg.get("relay"):
                self._to_hub.extend(msg["relay"])
            if msg.get("stall_sales") and self.stall_sink is not None:
                try:
                    self.stall_sink(msg["stall_sales"])
                except Exception as _exc:
                    _log("STALL SINK: %r" % (_exc,))
            if msg.get("caughts") and self.caught_sink is not None:
                try:
                    self.caught_sink(msg["caughts"])
                except Exception as _exc:
                    _log("CAUGHT SINK: %r" % (_exc,))
            if msg.get("offences") and self.offence_sink is not None:
                try:
                    self.offence_sink(msg["offences"])
                except Exception as _exc:
                    _log("OFFENCE SINK: %r" % (_exc,))
            for rid, payload in msg.get("done", ()):
                cb = self._cbs.pop(rid, None)
                if cb is not None:
                    try:
                        cb(payload)
                    except Exception as _exc:
                        _log("BOARD CALLBACK: %r" % (_exc,))
            for i, vals in msg.get("packs", ()):
                n = lane.men[i] if i < len(lane.men) else None
                if n is not None:
                    stock, coins, yearning, prices = vals
                    n.stock = dict(stock)
                    n.coins = coins
                    n.yearning = yearning
                    if prices is not None:
                        n.village.prices.update(prices)

    # -- the notice board, across the fence -------------------------------
    def watch(self, towns) -> None:
        """The towns whose board is on screen. Their state comes back next tick."""
        if self.settle is None:
            self._watch = []
            return
        out = []
        for v in towns:
            i = self.settle.town_index.get(id(v))
            if i is not None:
                out.append(i)
        self._watch = out

    def hire(self, town, kind, cb) -> None:
        self._request(("hire", self.settle.town_index.get(id(town))
                       if self.settle is not None else None, kind), cb)

    def sell(self, town, offers, cb) -> None:
        self._request(("sell", self.settle.town_index.get(id(town))
                       if self.settle is not None else None, list(offers)), cb)

    def _request(self, payload, cb) -> None:
        if not self.enabled or self.settle is None or payload[1] is None:
            if cb is not None:
                cb(None)
            return
        self._rid += 1
        self._cbs[self._rid] = cb
        self._reqs.append((self._rid,) + payload)

    # -- events that cross the fence --------------------------------------
    def take_deaths(self) -> list:
        """Drain the deaths the lanes have reported since the last frame."""
        got = self.deaths
        self.deaths = []
        return got

    def panic_at(self, x, y, radius: float = 600.0) -> None:
        """GUNFIRE, TOLD TO THE LANES: the crowd breaks in all directions."""
        if not self.enabled:
            return
        self._events.append(("panic", "settle", float(x), float(y),
                             float(radius)))
        _log("PANIC queued at %d,%d r=%d" % (int(x), int(y), int(radius)))

    def post(self, npc, xy) -> None:
        """TELL THE LANE WHERE THE MAN'S WORK IS (or that he has none)."""
        if not self.enabled or npc is None:
            return
        self._events.append(("post", "settle", getattr(npc, "id", None),
                             None if xy is None else float(xy[0]),
                             None if xy is None else float(xy[1])))
        _log("POST queued %r -> %r" % (getattr(npc, "id", None), xy))

    def damage(self, npc, amount) -> None:
        """THE EXACT MAN TAKES THE DAMAGE, in whichever lane owns him.

        Addressed by ID, not by position: an index into one lane's list is a
        different man in the other, and a blow that cannot be routed used to be
        dropped in complete silence -- the man the player was swinging at never
        lost a point of health while somebody else, somewhere, did.
        """
        if not self.enabled or npc is None:
            return
        key = str(getattr(npc, "id", ""))
        for lane in (self.settle, self.hub):
            if lane is None:
                continue
            if key in lane.ids:
                self._events.append(("dmg", lane.name, key, int(amount)))
                return
        now = time.monotonic()
        if now - self._dmg_missed.get(key, 0.0) > 5.0:
            self._dmg_missed[key] = now
            _log("DMG-DROPPED %s %s -- held by neither lane"
                 % (key, getattr(npc, "name", "?")))

    def crime(self, town, ids) -> None:
        if not self.enabled or town is None:
            return
        for lane in (self.settle, self.hub):
            if lane is None:
                continue
            i = lane.town_index.get(id(town))
            if i is not None:
                self._events.append(("crime", lane.name, i, list(ids)))
                return

    def stop(self) -> None:
        for lane in (self.settle, self.hub):
            if lane is not None:
                lane.stop()


class _Lane:
    def __init__(self, name, pid, w_fd, r_fd, men, towns, extras) -> None:
        self.name = name
        self.pid = pid
        self.req = _Pipe(w_fd)
        self.rep = _Pipe(r_fd, big=True)
        self.men = men
        self.towns = towns
        self.extras = extras
        self.index = {id(n): i for i, n in enumerate(men)}
        # AND BY NAME. An index is only meaningful to the lane that built the
        # list; an id means the same man in both.
        self.ids = {str(getattr(n, "id", "")) for n in men}
        self.town_index = {id(v): i for i, v in enumerate(towns)}

    def send(self, msg) -> None:
        self.req.send(msg)

    def recv(self) -> list:
        return self.rep.recv()

    def dead(self) -> bool:
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return True
        if pid == 0:
            return False
        _log("LANE %s (pid %d) has exited" % (self.name, self.pid))
        self.pid = -1
        return True

    def stop(self) -> None:
        try:
            os.kill(self.pid, 9)
        except (OSError, ProcessLookupError):
            pass
        self.req.close()
        self.rep.close()


# -- the two lanes ---------------------------------------------------------
ILLEGAL = tuple(nemesis_mod.ILLEGAL_LEAF) + tuple(nemesis_mod.ILLEGAL_DRUGS)


def _witness_ids(x, y, service):
    try:
        ws = nemesis_mod.witnesses_at(x, y, service)
    except Exception:
        return []
    return [str(getattr(w, "id", "?")) for w in ws
            if getattr(w, "secret_police", False)]


def _settlement_step(world, towns, men, player, hub_men, villages):
    """PROCESS 2: the settlements' books, and every settlement man."""

    class _Sink:
        def __init__(self):
            self.fires = []

        def fire(self, x, y, angle, distance, owner="player", damage=25,
                 team=None, spread=None, shooter=None):
            self.fires.append((round(x, 1), round(y, 1), round(angle, 4),
                               round(distance, 1), damage, team, spread))

        def spawn_swing(self, *a, **k):
            pass

        def spawn_impact(self, *a, **k):
            pass

        def spawn_flash(self, *a, **k):
            pass

    sink = _Sink()
    plots = []
    _orig_set = world.set_plot

    def _set_plot(tx, ty, kind, planted_at=None, grow=None):
        plots.append((tx, ty, kind, planted_at, grow))
        _orig_set(tx, ty, kind, planted_at, grow)

    world.set_plot = _set_plot

    # STEERING NEEDS THE TOWN'S WALLS, and the parent's grid is the frame's,
    # not this lane's. One static index for every town in the lane, built
    # once -- houses, walls, boards and benches do not move.
    import physics
    grid = physics.StaticGrid(96.0)
    for v in towns:
        for h in v.houses:
            grid.add(h.rect)
        for w in v.fence_walls:
            grid.add(w)
        grid.add(v.board)
        for wp in v.workplaces:
            grid.add(wp.rect)
    for n in men:
        n._rects = grid
        n._fences = towns

    # ---- A PLAN, NOT A NUDGE -------------------------------------------
    # `steering.steer` is local avoidance: it cannot solve a pinch between a
    # fence, a gate and a house, and a man told to walk to a yard on the other
    # side of a town orbited the joins for ever (measured: steer flipping
    # between +0.58,-0.82 and -0.58,+0.82 on alternate samples). The tree
    # already carries a real pathfinder -- pathfind.NavGrid / build / astar --
    # written for exactly this and never called by anything. This calls it.
    import pathfind as _path
    _navcache: dict = {}

    def _nav_for(n, now):
        """A small A* window around ONE man on his way to his post -- or a
        logger walking out to his tree (the gate is a pinch local steering
        cannot solve, so wood was never cut)."""
        p = getattr(n, "work_post", None)
        if p is None:
            _lt = getattr(n, "_log_tree", None)
            if getattr(n, "job", None) == "logger" and _lt is not None and not _lt.felled:
                p = (_lt.x, _lt.y)
            else:
                n._nav = None
                return
        gx = max(n.x - 700.0, min(n.x + 700.0, p[0]))
        gy = max(n.y - 700.0, min(n.y + 700.0, p[1]))
        x0, y0 = min(n.x, gx) - 260.0, min(n.y, gy) - 260.0
        x1, y1 = max(n.x, gx) + 260.0, max(n.y, gy) + 260.0
        key = (int(x0 // 240), int(y0 // 240), int(x1 // 240), int(y1 // 240),
               int(now // 2))
        got = _navcache.get(id(n))
        if got is not None and got[0] == key:
            got[1].time = now
            n._nav = got[1]
            return
        cols = max(1, int((x1 - x0) // _path.CELL) + 1)
        rows = max(1, int((y1 - y0) // _path.CELL) + 1)
        import pygame as _pg
        box = _pg.Rect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
        solid = []
        for v in towns:
            fr = getattr(v, "fence_rect", None)
            if fr is None or not fr.inflate(300, 300).colliderect(box):
                continue
            for h in getattr(v, "houses", ()) or ():
                solid.append(h.rect)
            for w in getattr(v, "fence_walls", ()) or ():
                solid.append(w)
            for wp in getattr(v, "workplaces", ()) or ():
                solid.append(wp.rect)
            b = getattr(v, "board", None)
            if b is not None:
                solid.append(b)
        try:
            g = _path.build(x0, y0, cols, rows, solid, towns, time=now)
        except Exception as exc:
            _log("NAV build: %r" % (exc,))
            n._nav = None
            return
        _navcache[id(n)] = (key, g)
        n._nav = g

    def threat_of(n):
        """WHO THIS MAN FIGHTS: the specific men who attacked him.

        A feud is with a person. He fights the men on his own list -- each of
        them until THAT man is dead or gone -- and nobody else: a square where
        everyone swings at "whoever is nearest" is how a town kills itself. A
        man who has not been attacked may still know a face, or stand in a town
        that has turned; he learns it ONCE (add_threat is idempotent), and it
        is never relearned sixty times a second.
        """
        if not getattr(n, "alive", True):
            return None
        try:
            foes = n.threat_list()
        except Exception:
            foes = []
        if foes:
            best, bd = None, 1e18
            for r in foes:
                if r is None or not getattr(r, "alive", True):
                    continue
                d = (r.x - n.x) ** 2 + (r.y - n.y) ** 2
                if d < bd:
                    best, bd = r, d
            if best is not None:
                return best
        if player.dead:
            return None
        d = (player.x - n.x) ** 2 + (player.y - n.y) ** 2
        if d > 900.0 * 900.0:
            return None
        knows = village_mod.PLAYER_ID in getattr(n, "knows", ())
        hot = (getattr(n, "hostile", False)
               or getattr(player, "wanted", False)
               or getattr(getattr(n, "village", None), "provoked", False)
               or getattr(n, "defender", False))
        if knows or hot:
            try:
                if n.add_threat(player):
                    plog.log("AGGRO", getattr(n, "name", "?"),
                             "now hunts the player",
                             "knows" if knows else "wanted")
            except Exception:
                pass
            return player
        return None

    class _S:
        pass

    by_id = {str(getattr(n, "id", "?")): n for n in men}

    stall = _StallProxy()

    timers = {"idle": 0.0, "walk": 0.0}

    # WHAT THE LANE DOES THAT THE SERVICE CARES ABOUT. A trader selling leaf or
    # a made drug is an offence the agents standing there can see; the sale
    # itself moves stock directly, so the one call every sale passes through
    # (economy._settle) is where it is noticed.
    offences = []
    caughts = []
    relay = []
    service = [n for n in men if getattr(n, "secret_police", False)]
    _orig_settle = economy_mod._settle

    def _settle(village, item, price, qty, seller, buyer):
        got = _orig_settle(village, item, price, qty, seller, buyer)
        try:
            if (got and seller is not None and item in ILLEGAL
                    and (getattr(seller, "job", None) == "trader"
                         or getattr(seller, "trade_state", "none") != "none")):
                offences.append((str(getattr(seller, "id", "?")), "sold", item,
                                 float(seller.x), float(seller.y),
                                 _witness_ids(seller.x, seller.y, service)))
        except Exception:
            pass
        return got

    economy_mod._settle = _settle

    def step(msg):
        del plots[:]
        del sink.fires[:]
        del offences[:]
        now, dt, phase = msg["now"], msg["dt"], msg["phase"]
        px, py, wanted, dead = msg["player"]
        player.x, player.y = px, py
        player.wanted, player.dead = wanted, dead
        # THE ROAD, AND THE NATION'S IDLE. Both move men between towns, so they
        # belong to the process that owns the men -- not to the frame.
        try:
            stubs = []
            for (sx, sy, snat, shost) in msg.get("soldiers", ()):
                st = _S()
                st.x, st.y, st.nation = sx, sy, snat
                st.hostile, st.alive, st.kind = shost, True, "soldier"
                stubs.append(st)
            village_mod.refugees_on_the_road(now, stubs)
        except Exception:
            pass
        timers["idle"] += dt
        if timers["idle"] >= 12.0:
            timers["idle"] = 0.0
            try:
                villages.send_idle(now)
            except Exception:
                pass
        for ev in msg["events"]:
            try:
                if ev[1] != "settle":
                    continue                       # another lane's business
                if ev[0] == "dmg":
                    _v = by_id.get(str(ev[2]))
                    if _v is not None:
                        try:
                            _v.take_damage(ev[3])
                            if getattr(_v, "alive", True):
                                _v.add_threat(player)   # he knows who hit him
                            _log("DMG %s -%s -> hp %s alive %s"
                                 % (getattr(_v, "name", "?"), ev[3],
                                    getattr(_v, "health", "?"),
                                    getattr(_v, "alive", "?")))
                        except Exception:
                            pass
                    else:
                        _log("DMG-MISS by_id %s" % ev[2])
                elif ev[0] == "crime":
                    if 0 <= ev[2] < len(towns):
                        towns[ev[2]].learn_killers(ev[3], now)
                        towns[ev[2]].provoke()
                elif ev[0] == "panic":
                    # A GUN WENT OFF HERE: the unarmed burst outward.
                    px, py = float(ev[2]), float(ev[3])
                    rad = float(ev[4]) if len(ev) > 4 else 600.0
                    for _n in men:
                        if not getattr(_n, "alive", True):
                            continue
                        if getattr(_n, "aggro", False) or getattr(_n, "weapon", None):
                            continue
                        if (_n.x - px) ** 2 + (_n.y - py) ** 2 > rad * rad:
                            continue
                        _n.panic = max(8.0, getattr(_n, "panic", 0.0))
                        _n.flee_dir = None      # he picks his own line
                elif ev[0] == "post":
                    # THE YARD CALLS: the man walks there, or is let go home.
                    _n = by_id.get(str(ev[2]))
                    if _n is not None:
                        if ev[3] is None:
                            _n.work_post = None
                            _n.player_worker = False
                        else:
                            _n.work_post = (float(ev[3]), float(ev[4]))
                            _n.player_worker = True
                        _log("POST applied %r %r" % (getattr(_n, "name", "?"),
                                                     getattr(_n, "work_post", None)))
            except Exception:
                pass
        for v in towns:
            try:
                r = gate_mod.tick_town(dt, v) if gate_mod is not None else None
                if r is not None and r[0] == "caught":
                    v.provoke()
                    # THE SERVICE IS TOLD: its agents in this town know.
                    caughts.append((str(getattr(r[1], "id", "?")),
                                    towns.index(v), int(r[2])))
            except Exception:
                pass
            try:
                v.update(dt, world, now, phase)
            except Exception as exc:
                _log("TOWN %s: %r" % (getattr(v, "name", "?"), exc))
            # THE CROWN HAS PAID MEN THIS LANE DOES NOT OWN. Hand the message
            # on; the lane that walks them hands over the coin.
            try:
                _rl = getattr(v, "_relay", None)
                if _rl:
                    relay.append((_rl[0], _rl[1], _rl[3]))  # ...and the day it is for
                    v._relay = None
                    # AND THE CHIEF, out of the same crown ledger. He is one
                    # man in one town, and this lane is the one that walks him.
                    _cw = int(_rl[2]) if len(_rl) > 2 else 0
                    _chief = next((n for n in men
                                   if getattr(n, "secret_police_chief", False)
                                   and getattr(n, "alive", True)), None)
                    if _chief is not None and _cw > 0 and v.ledger_coins >= _cw:
                        v.ledger_coins -= _cw
                        _chief.coins = int(getattr(_chief, "coins", 0) or 0) + _cw
                        economy_mod.flow(v, "pay_service", -_cw)
                        economy_mod._note(
                            "day %4d  %-14s SERVICE  crown paid %d to the chief %s"
                            % (int(float(msg["now"]) / economy_mod.DAY_LENGTH),
                               v.name, _cw, _chief.name))
            except Exception:
                pass
        timers["nav"] = timers.get("nav", 0.0) + dt
        if timers["nav"] >= 0.5:
            timers["nav"] = 0.0
            for _n in men:
                if getattr(_n, "work_post", None) is None \
                        and not (getattr(_n, "job", None) == "logger"):
                    continue
                try:
                    _nav_for(_n, now)
                except Exception as _ne:
                    _log("NAV %s: %r" % (getattr(_n, "name", "?"), _ne))
        for n in men:
            if not n.alive:
                continue
            try:
                n.tick(dt, world, now, phase, sink, bool(msg["night"]),
                       grid, threat_of)
            except Exception as exc:
                _log("MAN %s: %r" % (getattr(n, "name", "?"), exc))
        # ---- WHY IS A WALKING MAN WHERE HE IS? ---------------------------
        # Five seconds of truth for any man with a post: where he is, what the
        # steer gives him, and which fence (if any) claims to be in his way.
        timers["walk"] += dt
        if timers["walk"] >= 5.0:
            timers["walk"] = 0.0
            try:
                import steering as _st
                import fence as _fe
                for n in men:
                    _p = getattr(n, "work_post", None)
                    if _p is None or not getattr(n, "alive", True):
                        continue
                    _d = ((_p[0] - n.x) ** 2 + (_p[1] - n.y) ** 2) ** 0.5
                    if _d <= 25.0:
                        continue
                    _dir = _st.steer(n, _p[0], _p[1],
                                     getattr(n, "_rects", ()),
                                     getattr(n, "_fences", ()))
                    _cds = []
                    for v in towns:
                        try:
                            _cd = _fe.cross_dir(v, n.x, n.y, _p[0], _p[1])
                        except Exception:
                            _cd = None
                        if _cd is not None:
                            _cds.append("%s->%.2f,%.2f"
                                        % (v.name, _cd[0], _cd[1]))
                    _log("WALKD %-14s at %7.0f,%7.0f post %7.0f,%7.0f d %5.0f "
                         "steer %.2f,%.2f cross %s"
                         % (getattr(n, "name", "?"), n.x, n.y, _p[0], _p[1], _d,
                            _dir[0], _dir[1], ";".join(_cds) or "-"))
            except Exception as _we:
                _log("WALKD failed: %r" % (_we,))
        # THE NOTICE BOARD. What the town has going, what its ledger holds and
        # what its prices are -- computed HERE, where the town lives.
        watch = []
        for ti in msg.get("watch", ()):
            if 0 <= ti < len(towns):
                t = towns[ti]
                try:
                    posts = list(t.open_posts())
                except Exception:
                    posts = []
                watch.append((ti, posts, int(t.ledger_coins), dict(t.prices)))
        # AND THE TWO THINGS THE BOARD DOES. The town performs them; the frame
        # is told what happened, and moves the player's own coin and pack.
        done = []
        for req in msg.get("req", ()):
            rid, kind = req[0], req[1]
            try:
                if kind == "hire":
                    ti, trade = int(req[2]), req[3]
                    ok = False
                    if 0 <= ti < len(towns):
                        ok = bool(towns[ti].hire(player, trade))
                    done.append((rid, {
                        "hired": trade if ok else None,
                        "job": getattr(player, "job", None),
                        "wage": int(getattr(player, "wage", 0) or 0),
                        "farm_plot": getattr(player, "farm_plot", None),
                        "nation": getattr(player, "nation", None),
                        "town": ti}))
                elif kind == "sell":
                    ti, offers = int(req[2]), req[3]
                    taken, coin, units = {}, 0, 0
                    if 0 <= ti < len(towns):
                        t = towns[ti]
                        for item, qty, unit, grade in offers:
                            space = int(t.ledger_coins)
                            if space <= 0:
                                break
                            can = min(int(qty), space // max(1, int(unit)))
                            if can <= 0:
                                continue
                            economy_mod.store_add(t, item, can, int(grade))
                            t.ledger_coins = space - can * int(unit)
                            taken[item] = taken.get(item, 0) + can
                            coin += can * int(unit)
                            units += can
                    done.append((rid, {"sold": units, "coin": coin,
                                       "taken": taken}))
            except Exception as exc:
                _log("REQUEST %r: %r" % (kind, exc))
                done.append((rid, {"error": repr(exc)[:120]}))
        return _reply(msg, towns, men, plots, sink.fires, player, 0,
                      watch=watch, done=done, offences=offences,
                      relay=relay, caughts=caughts)

    return step


class _Box:
    """The four numbers `pathfind` needs from a rect."""
    __slots__ = ("left", "top", "right", "bottom")

    def __init__(self, x, y, w, h) -> None:
        self.left, self.top = float(x), float(y)
        self.right, self.bottom = float(x) + float(w), float(y) + float(h)

    def colliderect(self, other) -> bool:
        return (self.left < other.right and self.right > other.left
                and self.top < other.bottom and self.bottom > other.top)

    def inflate(self, dx, dy):
        return _Box(self.left - dx / 2.0, self.top - dy / 2.0,
                    (self.right - self.left) + dx, (self.bottom - self.top) + dy)


def pygame_rect(x, y, w, h) -> _Box:
    return _Box(x, y, w, h)


class _StallProxy:
    """THE PLAYER'S STALL, AS A CART SEES IT.

    A cart picks a hub by asking it what is on its shelf (`ledger_goods`) and
    pays into its `ledger_coins` (caravans.Caravan._buy). The stall is in the
    frame and the carts are in this process, so the stall stands here as a
    thing of exactly those attributes, fed once a second by the relay and
    reporting its sales back in the reply. It is not a hut and it is not a
    town; it is a counter.
    """

    is_hub = True
    is_stall = True
    # WHAT THE REPLY BUILDER READS OFF EVERY ENTRY IN THIS LANE'S `hubs`.
    # A stall is one of those entries now, so it must answer the same
    # questions a hut does (`provoked`, `battle`, ...) or the whole lane's
    # reply fails -- and a lane whose reply fails is a lane that never moves
    # a man, a cart or a coin again.
    provoked = False
    battle = False
    chaos = 0.0
    conquered = False
    nation = None
    search_t = 0.0
    ledger_coins = 0

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.name = "Market stall"
        self.on = False
        self.ledger_goods: dict = {}
        self.ledger_coins = 0
        self.prices: dict = {}          # (item, grade) -> the player's price
        self.sales_log: list = []       # [(item, grade, qty, coins)]
        self.fence_walls: list = []
        self.houses: list = []
        self.workplaces: list = []
        self.npcs: list = []

    def price_of(self, item, grade=None) -> int:
        import quality as _q
        g = int(_q.clamp(3 if grade is None else grade))
        return int(self.prices.get((item, g), 0) or 0)

    def lots(self) -> dict:
        """{(item, grade): [how many, price]} -- the counter, as a cart sees it."""
        out = {}
        for item, by_grade in (self._lots or {}).items():
            for g, row in by_grade.items():
                try:
                    qty = int(row[0])
                except Exception:
                    qty = int(row)
                out[(item, int(g))] = [qty, self.price_of(item, int(g))]
        return out

    # A stall is a PLACE, not a working hub: it has no fields to seed, no
    # watch to rotate and no men to feed. These are the hub calls this lane
    # makes on everything in its list.
    def update(self, *a, **k):
        return None

    def draw(self, *a, **k):
        return None

    def gate_list(self):
        return []

    def defenders(self):
        return []

    def free_post(self, npc):
        return None

    def offer_post(self, npc):
        return False

    def open_posts(self):
        return []

    def random_point(self, rng):
        return (self.x, self.y)

    def can_grow(self, now):
        return False

    def feed(self, rec) -> None:
        if rec is None:
            # NO STALL ANY MORE: a cart must not keep coming to a counter that
            # has been taken down.
            self.on = False
            self.ledger_goods = {}
            self.prices = {}
            return
        (self.x, self.y, self.name, on, lots) = (rec[0], rec[1], rec[2],
                                                 bool(rec[3]), rec[4] or {})
        self.prices = {}
        fresh = {}
        for item, by_grade in lots.items():
            for g, row in (by_grade or {}).items():
                try:
                    qty, price = int(row[0]), int(row[1])
                except Exception:
                    qty, price = int(row), 0
                if qty <= 0 or price <= 0:
                    continue
                fresh.setdefault(item, {})[int(g)] = qty
                self.prices[(item, int(g))] = price
        self._lots = fresh
        self.on = bool(on)
        if not on:
            self._lots = {}
            self.ledger_goods = {}
            self.ledger_coins = 0
            return
        # THE FRAME OWNS THE SHELF. Its count is the truth and this copy is
        # replaced by it every tick; what is sold here is reported and applied
        # there. If two carts were ever to buy the last cigar inside one tick,
        # the frame hands over what it has and credits only that (Stall.sold),
        # so a report can never create goods or coin.
        totals = {i: sum(int(q) for q in by.values()) for i, by in fresh.items()}
        if (totals != self.ledger_goods or bool(on) != self.on):
            _log("STALL fed on=%s lots=%r at %d,%d"
                 % (bool(on), {i: {int(g): int(v) for g, v in by.items()}
                               for i, by in fresh.items()},
                    int(self.x), int(self.y)))
        self.ledger_goods = totals


def _hub_step(world, hubs, men, carts, towns, player):
    """PROCESS 1: the hubs, their people, and the free traders."""
    from hubs import Hubs

    class _Sink:
        def __init__(self):
            self.fires = []

        def fire(self, x, y, angle, distance, owner="player", damage=25,
                 team=None, spread=None, shooter=None):
            self.fires.append((round(x, 1), round(y, 1), round(angle, 4),
                               round(distance, 1), damage, team, spread))

        def spawn_swing(self, *a, **k):
            pass

        def spawn_impact(self, *a, **k):
            pass

        def spawn_flash(self, *a, **k):
            pass

    sink = _Sink()
    plots = []
    _orig_set = world.set_plot

    def _set_plot(tx, ty, kind, planted_at=None, grow=None):
        plots.append((tx, ty, kind, planted_at, grow))
        _orig_set(tx, ty, kind, planted_at, grow)

    world.set_plot = _set_plot

    # WHAT A HUT DOES THAT THE SERVICE CARES ABOUT. The farmer turns leaf, the
    # bench makes the drug, and the cart sells it -- three ways of being seen
    # doing the one thing the state forbids.
    offences = []
    state = {"stipend_day": -1}
    service = [n for n in men if getattr(n, "secret_police", False)]
    _orig_harvest = economy_mod.harvest
    _orig_produce = industry.produce
    _orig_sell = caravans_mod.Caravan._sell

    def _harvest(village, npc, kind, rng):
        _orig_harvest(village, npc, kind, rng)
        try:
            if kind in crop_mod.LEAF_KINDS:
                offences.append((str(getattr(npc, "id", "?")), "grew",
                                 crop_mod.LEAF_ITEM.get(kind, kind),
                                 float(npc.x), float(npc.y),
                                 _witness_ids(npc.x, npc.y, service)))
        except Exception:
            pass

    def _produce(npc, dt, now):
        before = {k: int(v) for k, v in (getattr(npc, "stock", None) or {}).items()
                  if k in nemesis_mod.ILLEGAL_DRUGS}
        _orig_produce(npc, dt, now)
        try:
            for k in nemesis_mod.ILLEGAL_DRUGS:
                if int((getattr(npc, "stock", None) or {}).get(k, 0)) > before.get(k, 0):
                    offences.append((str(getattr(npc, "id", "?")), "made", k,
                                     float(npc.x), float(npc.y),
                                     _witness_ids(npc.x, npc.y, service)))
                    break
        except Exception:
            pass

    _orig_visitor = gate_mod.search_visitor
    _town_ix = {id(t): i for i, t in enumerate(towns)}

    def _visitor(dt, town, who):
        v = _orig_visitor(dt, town, who)
        try:
            if v == "caught":
                caughts.append((str(getattr(who, "id", "?")),
                                _town_ix.get(id(town), -1),
                                gate_mod.units_on(who)))
        except Exception:
            pass
        return v

    gate_mod.search_visitor = _visitor

    def _sell(self, town):
        n = self.npc
        before = {k: int((getattr(n, "stock", None) or {}).get(k, 0))
                  for k in nemesis_mod.ILLEGAL_LEAF + nemesis_mod.ILLEGAL_DRUGS}
        _orig_sell(self, town)
        try:
            for k in nemesis_mod.ILLEGAL_LEAF + nemesis_mod.ILLEGAL_DRUGS:
                if int((getattr(n, "stock", None) or {}).get(k, 0)) < before.get(k, 0):
                    offences.append((str(getattr(n, "id", "?")), "sold", k,
                                     float(n.x), float(n.y),
                                     _witness_ids(n.x, n.y, service)))
        except Exception:
            pass

    economy_mod.harvest = _harvest
    industry.produce = _produce
    caravans_mod.Caravan._sell = _sell

    import physics
    grid = physics.StaticGrid(96.0)
    for h in hubs:
        for w in getattr(h, "fence_walls", ()):
            grid.add(w)
        for house in getattr(h, "houses", ()):
            grid.add(house.rect)
        for wp in getattr(h, "workplaces", ()):
            grid.add(wp.rect)
    for n in men:
        n._rects = grid
        n._fences = hubs

    def threat_of(n):
        """WHO THIS MAN FIGHTS: the specific men who attacked him (see above)."""
        if not getattr(n, "alive", True):
            return None
        try:
            foes = n.threat_list()
        except Exception:
            foes = []
        if foes:
            best, bd = None, 1e18
            for r in foes:
                if r is None or not getattr(r, "alive", True):
                    continue
                d = (r.x - n.x) ** 2 + (r.y - n.y) ** 2
                if d < bd:
                    best, bd = r, d
            if best is not None:
                return best
        if player.dead:
            return None
        d = (player.x - n.x) ** 2 + (player.y - n.y) ** 2
        if d > 900.0 * 900.0:
            return None
        knows = village_mod.PLAYER_ID in getattr(n, "knows", ())
        hot = (getattr(n, "hostile", False)
               or getattr(player, "wanted", False)
               or getattr(getattr(n, "village", None), "provoked", False)
               or getattr(n, "defender", False))
        if knows or hot:
            try:
                if n.add_threat(player):
                    plog.log("AGGRO", getattr(n, "name", "?"),
                             "now hunts the player",
                             "knows" if knows else "wanted")
            except Exception:
                pass
            return player
        return None

    class _S:
        pass

    by_id = {str(getattr(n, "id", "?")): n for n in men}

    stall = _StallProxy()

    timers = {"idle": 0.0}

    # WHAT THE LANE DOES THAT THE SERVICE CARES ABOUT. A trader selling leaf or
    # a made drug is an offence the agents standing there can see; the sale
    # itself moves stock directly, so the one call every sale passes through
    # (economy._settle) is where it is noticed.
    offences = []
    caughts = []
    relay = []
    service = [n for n in men if getattr(n, "secret_police", False)]
    _orig_settle = economy_mod._settle

    def _settle(village, item, price, qty, seller, buyer):
        got = _orig_settle(village, item, price, qty, seller, buyer)
        try:
            if (got and seller is not None and item in ILLEGAL
                    and (getattr(seller, "job", None) == "trader"
                         or getattr(seller, "trade_state", "none") != "none")):
                offences.append((str(getattr(seller, "id", "?")), "sold", item,
                                 float(seller.x), float(seller.y),
                                 _witness_ids(seller.x, seller.y, service)))
        except Exception:
            pass
        return got

    economy_mod._settle = _settle

    def step(msg):
        del plots[:]
        del sink.fires[:]
        del offences[:]
        now, dt, phase = msg["now"], msg["dt"], msg["phase"]
        px, py, wanted, dead = msg["player"]
        player.x, player.y = px, py
        player.wanted, player.dead = wanted, dead
        # THE ROAD, AND THE NATION'S IDLE. Both move men between towns, so they
        # belong to the process that owns the men -- not to the frame.
        try:
            stubs = []
            for (sx, sy, snat, shost) in msg.get("soldiers", ()):
                st = _S()
                st.x, st.y, st.nation = sx, sy, snat
                st.hostile, st.alive, st.kind = shost, True, "soldier"
                stubs.append(st)
            village_mod.refugees_on_the_road(now, stubs)
        except Exception:
            pass
        timers["idle"] += dt
        if timers["idle"] >= 12.0:
            timers["idle"] = 0.0
            try:
                villages.send_idle(now)
            except Exception:
                pass
        for ev in msg["events"]:
            if len(ev) < 2 or ev[1] != "hub":
                continue                           # another lane's business
            if ev[0] == "dmg":
                _v = by_id.get(str(ev[2]))
                if _v is not None:
                    try:
                        _v.take_damage(ev[3])
                        if getattr(_v, "alive", True):
                            _v.add_threat(player)      # HE KNOWS WHO HIT HIM
                    except Exception:
                        pass
        # THE CROWN'S STIPEND. The seat paid it; these are the men it was for,
            # and this lane is the one that owns them.
        # THE STALL: where it is, what is on it, and what it costs. It joins
        # the list of places a cart may walk to the first time it is heard of.
        if "stall" in msg:
            try:
                stall.feed(msg["stall"])
                if stall.on and not any(h is stall for h in hubs):
                    hubs.append(stall)
                    _log("STALL joined the carts' map at %d,%d"
                         % (int(stall.x), int(stall.y)))
            except Exception as _se:
                _log("STALL relay: %r" % (_se,))
        for item in msg.get("relay", ()):
            try:
                if item[0] == "stipend":
                    # PAID ONCE FOR THE DAY IT IS FOR. The frame may deliver
                    # the same relay more than once when a pipe is busy; a
                    # day's pay is a day's pay.
                    _day = int(item[2]) if len(item) > 2 else -1
                    if _day >= 0 and _day <= state["stipend_day"]:
                        continue
                    if _day >= 0:
                        state["stipend_day"] = _day
                    per = int(item[1])
                    paid = 0
                    # ONLY THE TAGGED ONES. A free trader who is not the
                    # service's man is a criminal, and the crown does not pay
                    # criminals.
                    for c in carts:
                        n = getattr(c, "npc", None)
                        if (n is not None and getattr(n, "alive", True)
                                and getattr(n, "secret_police", False)):
                            n.coins = int(getattr(n, "coins", 0) or 0) + per
                            paid += per
                    _log("STIPEND paid %d to %d agent traders at %d each"
                         % (paid, paid // per if per else 0, per))
            except Exception as _ex:
                _log("RELAY %r: %r" % (item[:1], _ex))
        for hub in hubs:
            try:
                hub.update(dt, world, now, phase, sink, threat_of, grid)
            except Exception as exc:
                _log("HUB %s: %r" % (getattr(hub, "name", "?"), exc))
        for c in carts:
            try:
                c.tick(dt, hubs, towns, now)
            except Exception as exc:
                _log("CART: %r" % (exc,))
        sales = list(stall.sales_log)
        del stall.sales_log[:]
        return _reply(msg, hubs, men, plots, sink.fires, player, 1,
                      offences=offences, caughts=caughts, stall_sales=sales)

    return step


_DRAWN_NEAR = 1400.0     # a pack is synced for men this close to the player
_PACK_EVERY = 10         # ...and only every this many ticks (half a second)


_TICK = [0]
CENSUS_EVERY = 600        # 30 s of play at 20 Hz


def _census(men) -> dict:
    """WHO HOLDS THE COIN: every man's purse, added up by his trade."""
    agg: dict = {}
    for n in men:
        j = getattr(n, "job", None) or ("farm" if getattr(n, "farm_plot", None)
                                        is not None else "idler")
        a = agg.setdefault(j, [0, 0.0])
        a[0] += 1
        a[1] += float(getattr(n, "coins", 0) or 0)
    return agg


def _reply(msg, towns, men, plots, fires, player, kind,
           watch=(), done=(), offences=(), relay=(), caughts=(),
           stall_sales=()) -> dict:
    """WHAT THE FRAME NEEDS. Positions always; packs for the men he can reach."""
    recs = [_man_record(n) for n in men]
    packs = []
    # the ship-back is cheap because it is rare: every tenth tick, and only for
    # the men inside the player's reach -- the ones whose pack a menu can open.
    if int(msg.get("now", 0.0) * 20.0) % _PACK_EVERY == 0:
        near = []
        for i, n in enumerate(men):
            if not n.alive:
                continue
            if ((player.x - n.x) ** 2 + (player.y - n.y) ** 2
                    < _DRAWN_NEAR * _DRAWN_NEAR):
                near.append((i, (dict(getattr(n, "stock", {})), int(n.coins),
                                 round(float(getattr(n, "yearning", 0.0)), 3),
                                 None)))
        packs = near
    _TICK[0] += 1
    census = _census(men) if _TICK[0] % CENSUS_EVERY == 0 else None
    return {
        "men": recs,
        "census": census,
        "plots": plots,
        "fires": fires,
        "towns": [(i, (bool(v.provoked), bool(getattr(v, "battle", False)),
                       float(getattr(v, "chaos", 0.0)),
                       bool(getattr(v, "conquered", False)),
                       getattr(v, "nation", None),
                       float(getattr(v, "search_t", 0.0)),
                       # THE MONEY. Without this the frame's ledgers were
                       # frozen at load -- five minutes of watching a number
                       # that could not move, because the town that moves it
                       # lives in another process.
                       float(getattr(v, "ledger_coins", 0.0))))
                  for i, v in enumerate(towns)],
        "packs": packs,
        "watch": list(watch),
        "done": list(done),
        "offences": list(offences),
        "relay": list(relay),
        "caughts": list(caughts),
        "stall_sales": list(stall_sales),
        "now": msg.get("now", 0.0),
    }


# -- the entry point -------------------------------------------------------
_W = Workers()


def start(world, villages, hub_world, player) -> Workers:
    """Fork the two lanes. Returns the stub even when they are switched off."""
    if os.environ.get("KINGPIN_WORKERS", "1") == "0":
        _log("LANES disabled by KINGPIN_WORKERS=0")
        return _W
    # HOW MANY CORES MAY WE ACTUALLY TAKE (workers.py, which already existed):
    # affinity-aware, reserves two for the desktop and the OS, and refuses to
    # add lanes to a machine that is already loaded. Two lanes are needed for
    # the split; with fewer spare cores it is not worth forking at all.
    try:
        import workers as _plan
        spare = _plan.plan_workers()
    except Exception:
        spare = 2
    if spare < 2:
        _log("LANES: no spare cores (plan_workers=%d) -- single process" % spare)
        return _W
    try:
        import village as _v
        _towns = [v for v in villages.villages if not getattr(v, "is_hub", False)]
        _log("CENSUS towns %d  town.npcs %d  register %d  travellers %d"
             % (len(_towns), sum(len(v.npcs) for v in _towns),
                len(_v.PEOPLE), len(_v.TRAVELLERS)))
    except Exception as _ce:
        _log("CENSUS failed: %r" % (_ce,))
    _log("LANES: plan_workers=%d, taking 2 (hubs, settlements)" % spare)
    try:
        import village as village_mod
        settle_towns = [v for v in villages.villages
                        if not getattr(v, "is_hub", False)]
        hub_towns = list(hub_world.hubs)
        hub_men = [n for h in hub_towns for n in h.npcs]
        carts = list(getattr(hub_world, "_caravans", ()))
        hub_men += [c.npc for c in carts]
        seen = {id(n) for n in hub_men}
        # THE ROLL AND THE REGISTER ARE NOT THE SAME LIST. A town's roster is
        # the authority for who lives there; `village.PEOPLE` is the flat list
        # the frame used to walk, and it need not hold every man a town lists
        # (rebuild_people caps a town at its capacity). The lane must own every
        # man EITHER list names, or a man drops out of the simulation the
        # moment the frame hands the settlements over.
        settle_men = []
        got = set()
        for n in (list(village_mod.PEOPLE)
                  + [n for t in settle_towns for n in t.npcs]
                  + list(village_mod.TRAVELLERS)):
            i = id(n)
            if i in seen or i in got or not getattr(n, "alive", True):
                continue
            got.add(i)
            settle_men.append(n)
        _W.settle = _W._spawn(
            "settle", lambda: _settlement_step(world, settle_towns, settle_men,
                                               player, hub_men, villages),
            settle_men, settle_towns, None)
        _W.hub = _W._spawn(
            "hub", lambda: _hub_step(world, hub_towns, hub_men, carts,
                                     settle_towns, player),
            hub_men, hub_towns, None)
        _W.enabled = True
        _log("LANES UP: %d settlement men / %d towns, %d hub men / %d hubs"
             % (len(settle_men), len(settle_towns), len(hub_men), len(hub_towns)))
    except Exception as exc:
        import traceback
        _log("LANES FAILED TO START: %r\n%s" % (exc, traceback.format_exc()))
        _W.enabled = False
    return _W
