#!/usr/bin/env python3
"""Makes the features (the game's tools/feature_bake.py: the things worth stopping for, from the Overture themes the
other bakers don't read) of the baked cells of one 5 degree block, into OUT/cROW_COL.features for index.py to merge
(feature/ and the index's "features"). Only the cells whose features are missing, or were made from another Overture
release or another list of classes (feature_bake.py's classes hash), are made again: adding a kind to the game's baker
costs one incremental pass, not a world re-bake. Each 1 degree square's roads and map rows are fetched once.

    python3 scripts/feature_backfill.py GAME_TOOLS_DIR --only R_C --out DIR [--release RELEASE] [--threads N] [--all]"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def wanted(cell, release, classes, root=idx.ROOT):
    """Whether cell "ROW_COL"'s features file is missing, or was made from another release or classes."""
    path = os.path.join(root, "feature", "c%s.json" % cell)
    if not os.path.exists(path):
        return True
    try:
        with open(path) as f:
            have = json.load(f)
    except (OSError, ValueError):
        return True
    return have.get("release") != release or have.get("classes") != classes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release", help="the Overture release (default: the index's)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--all", action="store_true", help="make every cell's again, whatever it was made from")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import coast_bake as cb
    import feature_bake as fb
    with open(idx.INDEX) as f:
        index = json.load(f)
    release = args.release or index["release"]
    classes = fb.classes_hash()
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only
                   and (args.all or wanted(c, release, classes)))
    squares = {}
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares.setdefault((row // 4, col // 4), []).append((row, col))
    os.makedirs(args.out, exist_ok=True)

    def square(item):
        (sr, sc), members = item
        s, w, _, _ = cb.cell_box(sr * 4, sc * 4)
        for attempt in range(4):
            try:
                fetched = fb.fetch_square((s, w, s + 1.0, w + 1.0), release, log=lambda m: None)
                break
            except OSError:
                if attempt == 3:
                    raise
        for row, col in members:
            got = fb.cell_features_of(fetched, row, col, release)
            fb.write(os.path.join(args.out, "c%s.features" % got["cell"]), got)
        print("square %d_%d: %d cells" % (sr, sc, len(members)), flush=True)
        return len(members)

    with ThreadPoolExecutor(args.threads) as pool:
        n = sum(pool.map(square, sorted(squares.items())))
    print("features: %d cells of block %s in %d squares (Overture %s, classes %s)" % (n, args.only, len(squares), release,
                                                                                    classes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
