# BUGS

## B1. PLACED BLOCK ROWS STILL SHOW "TEETH" (open — the current bug)

**Symptom (his words):** a row of placed planks/hides forms like **teeth** —
every block is separated by a line — when it should be one solid wall: "I see
the row fine, but not anything behind it."

**What the game does, and what has already been tried:**

1. Each block used to draw its own dark shadow/border on **all four sides**, so
   two neighbours each put a dark line on their shared edge. Changed so an edge
   is drawn **only on exposed sides** (no neighbour) — `block._edges` +
   `draw_blocks` merge a row into one wall.
2. The build-grid mesh (white lines, `block.draw_grid`) was drawn **ON TOP of**
   the placed blocks, so every seam had a white grid line through it. Changed
   the order in `render.py` so the grid draws **under** the blocks.

**Verified at the drawing-function level:** sampling `draw_grid` then
`draw_blocks` into one surface, the seam between two planks reads pure wood
`(118,78,44)` and a wood→hide seam reads `(118,78,44) → (124,86,54)` with **no
line in between**.

**But he still sees teeth in the running game.** So the cause is NOT in the
block face/edge drawing — it is downstream of it. Candidates, not yet ruled
out:

- **The zoom scale-up (`_present`, `main.py`)** — the view surface (568×320) is
  scaled to the window by `ZOOM = 2.25` with `pygame.transform.scale`
  (nearest-neighbour). A 32 px tile → 72 px, but the seam pixel is resampled
  against its neighbour, and any 1-pixel feature at the seam becomes a ~2 px
  visible line.
- **The vision mask / night shade** drawn over the world after the blocks.
- **A stale binary** — the "teeth" he saw may predate the grid-order fix. The
  fix is built and pushed, but not yet confirmed by him in a fresh run.

**Next step:** confirm on the current build (`./GetWorld`, commit `d599851`)
whether the teeth persist; if they do, capture one real frame and sample the
seam pixels on the scaled window to see which pass (scale / mask / night) draws
the line.

---

## Still open (carried over, untouched)

- **The freeze on breaking into a house.** Instrumented with a hang watchdog —
  the next freeze writes every thread stack to `saves/hang.log`. Read that file
  instead of guessing.
- **A guard is too easy to kill** (40 hp villager with no gun vs an armed
  player). Design question logged, not changed.
- **Selling to one man can bankrupt him.** Proposed fix logged (two days' worth,
  then refuse); not changed.
- **`E` with the body/folder panel open falls through and freezes the world**
  (panel open should swallow `E`). Logged, not fixed.
