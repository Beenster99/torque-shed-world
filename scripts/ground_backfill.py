#!/usr/bin/env python3
"""Makes the ground and the paths (the game's tools/ground_bake.py and paths_bake.py: water, land cover, land use, trees
and car parks; footpaths, bridleways and cycleways beside the roads) of the baked cells of one 5 degree block, into
OUT/cROW_COL.ground and OUT/cROW_COL.paths for index.py to merge (ground/ and paths/, the index's "grounds" and
"paths"). Only the cells whose files are missing, or were made from another Overture release or another list of classes,
are made again. Each 1 degree square's roads, ground and paths are fetched once, and each row is handed only to the
cells its box touches.

    python3 scripts/ground_backfill.py GAME_TOOLS_DIR --only R_C --out DIR [--release RELEASE] [--threads N] [--all]
        [--cells ROW_COL,...]"""
import argparse
import json
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402

# Roads fetched this far (degrees) round a square, so a cell at its edge knows the roads just over it.
PAD = 0.01


def wanted(cell, folder, release, classes, root=idx.ROOT):
    """Whether cell "ROW_COL"'s file in folder is missing, or was made from another release or classes."""
    path = os.path.join(root, folder, "c%s.json" % cell)
    if not os.path.exists(path):
        return True
    try:
        with open(path) as f:
            have = json.load(f)
    except (OSError, ValueError):
        return True
    return have.get("release") != release or have.get("classes") != classes


def bounds(fb, wkb):
    """A geometry's (south, west, north, east), or None if it doesn't parse."""
    try:
        pts, lines, rings = fb.parse_any(wkb)
    except (ValueError, struct.error):
        return None
    every = list(pts) + [p for ln in lines for p in ln] + [p for r in rings for p in r]
    if not every:
        return None
    lons = [p[0] for p in every]
    lats = [p[1] for p in every]
    return min(lats), min(lons), max(lats), max(lons)


def by_cell(fb, cb, rows, members, geometry, margin=0.0):
    """rows filed under each member cell (row, col) whose box (grown by margin degrees) their geometry's box touches."""
    out = {m: [] for m in members}
    boxes = {}
    for m in members:
        s, w, n, e = cb.cell_box(*m)
        boxes[m] = (s - margin, w - margin, n + margin, e + margin)
    for r in rows:
        b = bounds(fb, geometry(r))
        if b is None:
            continue
        for m, (s, w, n, e) in boxes.items():
            if b[0] <= n and b[2] >= s and b[1] <= e and b[3] >= w:
                out[m].append(r)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release", help="the Overture release (default: the index's)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--all", action="store_true", help="make every cell's again, whatever it was made from")
    ap.add_argument("--cells", default="", help="just these cells (ROW_COL,...) of the block")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import coast_bake as cb
    import feature_bake as fb
    import ground_bake as gb
    import paths_bake as pb
    import stream_bake as sb
    with open(idx.INDEX) as f:
        index = json.load(f)
    release = args.release or index["release"]
    g_classes, p_classes = gb.classes_hash(), pb.classes_hash()
    only = {c for c in args.cells.split(",") if c}
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only
                   and (not only or c in only)
                   and (args.all or wanted(c, "ground", release, g_classes) or wanted(c, "paths", release, p_classes)))
    squares = {}
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares.setdefault((row // 4, col // 4), []).append((row, col))
    os.makedirs(args.out, exist_ok=True)
    g_reach = max(r for t in gb.CLASSES.values() for _, r, _, _ in t.values() if r is not None)

    def square(item):
        (sr, sc), members = item
        t0 = time.time()
        s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
        box = (s, w, s + 1.0, w + 1.0)
        for attempt in range(4):
            try:
                roads = sb.fetch_roads((box[0] - PAD, box[1] - PAD, box[2] + PAD, box[3] + PAD), release)
                ground = gb.fetch(box, release, log=lambda m: None)
                paths = pb.fetch(box, release, log=lambda m: None)
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
        t1 = time.time()
        g_by = by_cell(fb, cb, ground, members, lambda r: r[1]["geometry"])
        p_by = by_cell(fb, cb, paths, members, lambda r: r["geometry"])
        r_by = by_cell(fb, cb, roads, members, lambda r: r, PAD)
        for row, col in members:
            cbox = cb.cell_box(row, col)
            near = r_by[(row, col)]
            g_field = gb.RoadField(near, cbox, g_reach) if near else None
            p_field = gb.RoadField(near, cbox, pb.REACH_M) if near else None
            got = gb.cell_ground(g_by[(row, col)], g_field, row, col, release)
            gb.write(os.path.join(args.out, "c%s.ground" % got["cell"]), got)
            got = pb.cell_paths(p_by[(row, col)], p_field, row, col, release)
            gb.write(os.path.join(args.out, "c%s.paths" % got["cell"]), got)
        print("square %d_%d: %d cells, fetched in %.0f s, made in %.0f s (%d roads, %d ground rows, %d paths)"
              % (sr, sc, len(members), t1 - t0, time.time() - t1, len(roads), len(ground), len(paths)), flush=True)
        return len(members)

    with ThreadPoolExecutor(args.threads) as pool:
        n = sum(pool.map(square, sorted(squares.items())))
    print("ground and paths: %d cells of block %s in %d squares (Overture %s, classes %s / %s)"
          % (n, args.only, len(squares), release, g_classes, p_classes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
