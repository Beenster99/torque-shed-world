#!/usr/bin/env python3
"""Adds the entries a bake run made (entries/*.json, one a cell) to index.json.

    python3 scripts/index.py entries/

An entry is {cell: "ROW_COLUMN", release, hash, bytes, url, tools} for a baked cell, or {cell, release, empty: true} for
one with no roads (the sea, mostly: not baked again). Entries from another release than the index's are left out.

A baked cell's main-roads sketch (entries/cROW_COL.sketch, by the game's tools/sketch_bake.py) goes into its 5 degree
block's file, sketch/bR_C.json ({"format": 1, "cells": {"ROW_COL": lines}}), and the block's hash into the index's
"sketches" ({"R_C": hash}): the Route planner TV fetches a block's file when it changes."""
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INDEX = os.path.join(ROOT, "index.json")


def main(argv):
    with open(INDEX) as f:
        index = json.load(f)
    added = 0
    for path in sorted(glob.glob(os.path.join(argv[1], "**", "*.json"), recursive=True)):
        with open(path) as f:
            e = json.load(f)
        if not isinstance(e, dict) or "cell" not in e or e.get("release") != index["release"]:
            continue
        cell = e.pop("cell")
        e.pop("release")
        index["cells"][cell] = e
        added += 1
    index["cells"] = dict(sorted(index["cells"].items()))
    sketches = merge_sketches(sorted(glob.glob(os.path.join(argv[1], "**", "*.sketch"), recursive=True)), index)
    with open(INDEX, "w") as f:
        json.dump(index, f, indent=1, sort_keys=False)
        f.write("\n")
    print("index: %d added, %d cells; %d sketches" % (added, len(index["cells"]), sketches))


def block_of(cell):
    """The 5 degree block ("R_C") of cell "ROW_COL": the bake workflow's release for it."""
    row, col = (int(v) for v in cell.split("_"))
    return "%d_%d" % (row // 20, col // 20)


def merge_sketches(paths, index, root=ROOT):
    """Puts the cell sketches at `paths` (main roads as "lines", a coast as "land", bridges and tunnels as "spans", or some of them) into their blocks' files
    under root/sketch, and each block's hash into index["sketches"]. Returns how many were put in."""
    by_block = {}
    for path in paths:
        with open(path) as f:
            s = json.load(f)
        by_block.setdefault(block_of(s["cell"]), []).append(s)
    for block, sketches in sorted(by_block.items()):
        path = os.path.join(root, "sketch", "b%s.json" % block)
        data = {"format": 1, "cells": {}}
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        for s in sketches:
            # (a sketch with only some of lines, land (a coast) and spans changes just those)
            if "lines" in s:
                data["cells"][s["cell"]] = s["lines"]
            for key in ("land", "spans"):
                if key in s:
                    data.setdefault(key, {})[s["cell"]] = s[key]
        data["cells"] = dict(sorted(data["cells"].items()))
        for key in ("land", "spans"):
            if key in data:
                data[key] = dict(sorted(data[key].items()))
        text = json.dumps(data, separators=(",", ":"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text + "\n")
        index.setdefault("sketches", {})[block] = hashlib.sha1(text.encode()).hexdigest()[:12]
    if "sketches" in index:
        index["sketches"] = dict(sorted(index["sketches"].items()))
    return sum(len(v) for v in by_block.values())


if __name__ == "__main__":
    main(sys.argv)
