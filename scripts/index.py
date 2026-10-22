#!/usr/bin/env python3
"""Adds the entries a bake run made (entries/*.json, one a cell) to index.json.

    python3 scripts/index.py entries/

An entry is {cell: "ROW_COLUMN", release, hash, bytes, url, tools} for a baked cell, or {cell, release, empty: true} for
one with no roads (the sea, mostly: not baked again). Entries from another release than the index's are left out."""
import glob
import json
import os
import sys

INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.json")


def main(argv):
    with open(INDEX) as f:
        index = json.load(f)
    added = 0
    for path in sorted(glob.glob(os.path.join(argv[1], "**", "*.json"), recursive=True)):
        with open(path) as f:
            e = json.load(f)
        if e.get("release") != index["release"]:
            continue
        cell = e.pop("cell")
        e.pop("release")
        index["cells"][cell] = e
        added += 1
    index["cells"] = dict(sorted(index["cells"].items()))
    with open(INDEX, "w") as f:
        json.dump(index, f, indent=1, sort_keys=False)
        f.write("\n")
    print("index: %d added, %d cells" % (added, len(index["cells"])))


if __name__ == "__main__":
    main(sys.argv)
