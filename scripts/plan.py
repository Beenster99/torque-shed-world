#!/usr/bin/env python3
"""Which cells a bake run makes: the cells asked for, less those the index already has for this release (unless
REBAKE is "true": then the cells the index has are baked again, with newer tools, and those it has as empty are left).

    python3 scripts/plan.py "54.3,-1.9 54.25,-2.5,54.5,-1.75" [RELEASE] [REBAKE] >> "$GITHUB_OUTPUT"

Each item is a point (LAT,LON: the cell it is in) or a box (SOUTH,WEST,NORTH,EAST: every cell it touches). Writes
`cells=<JSON list of [row, column, lat, lon]>` (lat, lon the cell's middle) and `release=<Overture release>`. A run
bakes at most MAX cells (a workflow's matrix has room for 256): ask again for the rest."""
import json
import math
import os
import sys

CELL_DEG = 0.25          # tools/region_bake.py CELL_DEG
MAX = 250
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.json")


def cell_of(lat, lon):
    return int(math.floor((lat + 90.0) / CELL_DEG)), int(math.floor((lon + 180.0) / CELL_DEG))


def cells_of(item):
    v = [float(x) for x in item.split(",")]
    if len(v) == 2:
        return [cell_of(*v)]
    if len(v) == 4:
        s, w, n, e = v
        a, b = cell_of(s, w), cell_of(n - 1e-9, e - 1e-9)
        return [(i, j) for i in range(a[0], b[0] + 1) for j in range(a[1], b[1] + 1)]
    raise SystemExit("not a point or a box: %s" % item)


def main(argv):
    with open(INDEX) as f:
        index = json.load(f)
    release = (argv[2] if len(argv) > 2 and argv[2] else "") or index["release"]
    have = index["cells"] if release == index["release"] else {}
    rebake = len(argv) > 3 and argv[3] == "true"
    want = []
    for item in argv[1].split():
        for c in cells_of(item):
            key = "%d_%d" % c
            if c in want:
                continue
            if (rebake and key in have and not have[key].get("empty")) or (not rebake and key not in have):
                want.append(c)
    if len(want) > MAX:
        print("asked for %d cells: baking the first %d" % (len(want), MAX), file=sys.stderr)
        want = want[:MAX]
    rows = [[i, j, round((i + 0.5) * CELL_DEG - 90.0, 6), round((j + 0.5) * CELL_DEG - 180.0, 6)] for i, j in want]
    print("cells=%s" % json.dumps(rows, separators=(",", ":")))
    print("release=%s" % release)


if __name__ == "__main__":
    main(sys.argv)
