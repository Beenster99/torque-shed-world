#!/usr/bin/env python3
"""Makes the coast (the game's tools/coast_bake.py: where the land is, for the Route planner TV close in), or with
--what spans the bridges and tunnels (tools/span_bake.py), of every baked cell the index has, fetching Overture's data
once per 1 degree square, and merges them into sketch/ and the index's "sketches" (see index.py). For cells baked
before these were made; cells baked since get theirs as they are baked.

    python3 scripts/coast_backfill.py GAME_TOOLS_DIR [--what coast|spans] [--only R_C] [--release RELEASE]"""
import argparse
import json
import math
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--what", choices=["coast", "spans"], default="coast")
    ap.add_argument("--only", help="just this 5 degree block (R_C)")
    ap.add_argument("--release", help="the Overture release (default: the latest)")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import coast_bake as cb
    import route_bake as rb
    if args.what == "spans":
        import span_bake as sp
        fetch = sp.fetch_segments
        make = sp.cell_spans
    else:
        fetch = cb.fetch_land
        make = cb.cell_coast
    release = args.release or rb.latest_release()
    with open(idx.INDEX) as f:
        index = json.load(f)
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and (not args.only or idx.block_of(c) == args.only))
    # The cells by 1 degree square (4 by 4 cells), so each square's land is fetched once.
    squares = {}
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares.setdefault((row // 4, col // 4), []).append((row, col))
    with tempfile.TemporaryDirectory() as out:
        def square(item):
            (sr, sc), members = item
            s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
            for attempt in range(4):
                try:
                    geoms = fetch((s, w, s + 1.0, w + 1.0), release)
                    break
                except OSError:
                    if attempt == 3:
                        raise
            paths = []
            for row, col in members:
                got = make(geoms, row, col)
                path = os.path.join(out, "c%s.sketch" % got["cell"])
                with open(path, "w") as f:
                    json.dump(got, f, separators=(",", ":"))
                paths.append(path)
            print("square %d_%d: %d cells" % (sr, sc, len(members)), flush=True)
            return paths
        with ThreadPoolExecutor(8) as pool:
            paths = [p for ps in pool.map(square, sorted(squares.items())) for p in ps]
        n = idx.merge_sketches(paths, index)
    with open(idx.INDEX, "w") as f:
        json.dump(index, f, indent=1, sort_keys=False)
        f.write("\n")
    print("%s: %d cells in %d squares (Overture %s)" % (args.what, n, len(squares), release))
    return 0


if __name__ == "__main__":
    sys.exit(main())
