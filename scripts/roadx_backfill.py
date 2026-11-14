#!/usr/bin/env python3
"""Makes the road itself (the game's tools/roadx_bake.py: lanes, roundabouts, lights, crossings, humps, barriers, from
OpenStreetMap) of the baked cells of one 5 degree block, into OUT/cROW_COL.roadx for index.py to merge (roadx/ and the
index's "roadx"). The extract (Geofabrik's Great Britain one) is cut to each 1 degree square once with osmium-tool.

    python3 scripts/roadx_backfill.py GAME_TOOLS_DIR --pbf GB.osm.pbf --only R_C --out DIR [--squares LAT,LON ...]
                                      [--release RELEASE]"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--pbf", required=True)
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--squares", nargs="*", default=[], help="just these 1 degree squares (LAT,LON of their corner)")
    ap.add_argument("--release", help="the Overture release (default: the index's)")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import coast_bake as cb
    import roadx_bake as rb
    with open(idx.INDEX) as f:
        index = json.load(f)
    release = args.release or index["release"]
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only)
    squares = {}
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares.setdefault((row // 4, col // 4), []).append((row, col))
    only = {tuple(int(float(v)) for v in s.split(",")) for s in args.squares}
    os.makedirs(args.out, exist_ok=True)
    os.makedirs("cuts", exist_ok=True)
    n = 0
    for (sr, sc), members in sorted(squares.items()):
        s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
        if only and (int(round(s)), int(round(w))) not in only:
            continue
        cut = os.path.join("cuts", "s%d_%d.osm.pbf" % (sr, sc))
        # (a little over the square's edge, so a way crossing it is whole)
        subprocess.run(["osmium", "extract", "-b", "%.3f,%.3f,%.3f,%.3f" % (w - 0.02, s - 0.02, w + 1.02, s + 1.02),
                        "-s", "smart", "--overwrite", "-o", cut, args.pbf], check=True)
        for baked in rb.bake_cells(cut, members, release, log=lambda m: None):
            with open(os.path.join(args.out, "c%s.roadx" % baked["cell"]), "w") as f:
                json.dump(baked, f, separators=(",", ":"))
            print(rb.report(baked), flush=True)
            n += 1
        os.remove(cut)
    print("roadx: %d cells of block %s (Overture %s)" % (n, args.only, release))
    return 0


if __name__ == "__main__":
    sys.exit(main())
