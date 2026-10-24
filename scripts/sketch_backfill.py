#!/usr/bin/env python3
"""Makes the main-roads sketch of every baked cell the index has (each cell's zip fetched from its release, its sketch
made by the game's tools/sketch_bake.py), and merges them into sketch/ and the index's "sketches" (see index.py). For
cells baked before sketches were made; cells baked since get theirs as they are baked.

    python3 scripts/sketch_backfill.py GAME_TOOLS_DIR [--only R_C]"""
import argparse
import io
import json
import os
import sys
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def sketch_of(cell, entry, tools, out_dir):
    req = urllib.request.Request(entry["url"], headers={"User-Agent": "torque-shed-world sketch_backfill"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            break
        except OSError:
            if attempt == 3:
                raise
    with tempfile.TemporaryDirectory() as d:
        zipfile.ZipFile(io.BytesIO(data)).extractall(d)
        s = tools.cell_sketch(d)
    s["cell"] = cell
    path = os.path.join(out_dir, "c%s.sketch" % cell)
    with open(path, "w") as f:
        json.dump(s, f, separators=(",", ":"))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--only", help="just this block (R_C)")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import sketch_bake as tools
    with open(idx.INDEX) as f:
        index = json.load(f)
    cells = {c: e for c, e in index["cells"].items() if not e.get("empty") and (not args.only or idx.block_of(c) == args.only)}
    with tempfile.TemporaryDirectory() as out:
        with ThreadPoolExecutor(8) as pool:
            paths = list(pool.map(lambda kv: sketch_of(kv[0], kv[1], tools, out), sorted(cells.items())))
        n = idx.merge_sketches(paths, index)
    with open(idx.INDEX, "w") as f:
        json.dump(index, f, indent=1, sort_keys=False)
        f.write("\n")
    print("sketches: %d cells in %d blocks" % (n, len(index.get("sketches", {}))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
