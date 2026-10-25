#!/usr/bin/env python3
"""Makes the trees (the game's tools/tree_bake.py: the canopy's height and how thick it is near the roads, from Meta and
WRI's canopy height map, and the leaves where OpenStreetMap has them) of the baked cells of one 5 degree block, into
OUT/cROW_COL.trees for index.py to merge (tree/ and the index's "trees"). For cells baked before trees were made; cells
baked since get theirs as they are baked. Each 1 degree square's roads and woods are fetched once, and each canopy tile
(about 170 MB) once, then deleted when no square left wants it.

    python3 scripts/tree_backfill.py GAME_TOOLS_DIR --only R_C --out DIR [--release RELEASE] [--threads N]"""
import argparse
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release", help="the Overture release (default: the latest)")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import coast_bake as cb
    import route_bake as rb
    import tree_bake as tb
    release = args.release or rb.latest_release()
    with open(idx.INDEX) as f:
        index = json.load(f)
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only)
    squares = {}
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares.setdefault((row // 4, col // 4), []).append((row, col))
    # How many squares still want each canopy tile.
    wants = {}
    for (sr, sc) in squares:
        s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
        for t in tb.tiles_over((s, w, s + 1.0, w + 1.0)):
            wants[t] = wants.get(t, 0) + 1
    lock = threading.Lock()
    os.makedirs(args.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as cache:
        tiles = tb.Tiles(cache, log=lambda m: print(m, flush=True))

        def square(item):
            (sr, sc), members = item
            s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
            box = (s, w, s + 1.0, w + 1.0)
            for attempt in range(4):
                try:
                    _, roads, woods = tb.fetch_square(box, release, cache)
                    break
                except OSError:
                    if attempt == 3:
                        raise
            for row, col in members:
                got = tb.cell_trees(row, col, tiles, roads, woods)
                with open(os.path.join(args.out, "c%s.trees" % got["cell"]), "w") as f:
                    json.dump(got, f, separators=(",", ":"))
            done = []
            with lock:
                for t in tb.tiles_over(box):
                    wants[t] -= 1
                    if wants[t] == 0:
                        done.append(t)
            tiles.drop(done)
            print("square %d_%d: %d cells" % (sr, sc, len(members)), flush=True)
            return len(members)

        with ThreadPoolExecutor(args.threads) as pool:
            n = sum(pool.map(square, sorted(squares.items())))
    print("trees: %d cells of block %s in %d squares (Overture %s)" % (n, args.only, len(squares), release))
    return 0


if __name__ == "__main__":
    sys.exit(main())
