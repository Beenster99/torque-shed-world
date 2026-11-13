#!/usr/bin/env python3
"""Makes the buildings (the game's tools/building_bake.py: every building with its outline and height, towns stage 3)
of the baked cells of one 5 degree block, each zipped as OUT/cROW_COL-HASH.bld.zip (zipped() says how) with
its entry OUT/cROW_COL.bld for index.py to merge (the index's "buildings": {"ROW_COL": {hash, bytes, url, classes}}).
The zips go up as the release assets of bld-RELEASE-bR_C (the workflow uploads them: they are far too big for git).
Only the cells with none, or made from another Overture release or other rules (building_bake.py's classes hash), are
made again.

    python3 scripts/building_backfill.py GAME_TOOLS_DIR --only R_C --out DIR --repo OWNER/NAME [--release RELEASE]
        [--threads N] [--all] [--shard K/N]"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import index as idx  # noqa: E402


def tag_of(release, block):
    return "bld-%s-b%s" % (release, block)


CELLS_A_JOB = 40   # (about 3 minutes a cell, four at a time: half an hour a job)


def jobs(index, classes, only=(), every=False):
    """The workflow's jobs: "R_C:K/N" for each block's share of the cells it must make, CELLS_A_JOB a job."""
    release = index["release"]
    count = {}
    for c, e in index["cells"].items():
        if not e.get("empty") and (every or wanted(index, c, release, classes)):
            b = idx.block_of(c)
            if not only or b in only:
                count[b] = count.get(b, 0) + 1
    out = []
    for b in sorted(count):
        n = max(1, -(-count[b] // CELLS_A_JOB))
        out += ["%s:%d/%d" % (b, k, n) for k in range(n)]
    return out


def wanted(index, cell, release, classes):
    have = index.get("buildings", {}).get(cell)
    return have is None or have.get("release") != release or have.get("classes") != classes


def zipped(got):
    """The cell's file as a zip the game can read a tile at a time: buildings.json (the file without its rows, and
    "have": the tiles it has) and each tile's rows as tTX_TZ.json ([building, ...]); the same bytes for the same file."""
    buf = io.BytesIO()

    def put(z, name, value):
        info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, json.dumps(value, separators=(",", ":")))

    head = {k: v for k, v in got.items() if k != "rows"}
    head["have"] = sorted(got["rows"])
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        put(z, "buildings.json", head)
        for key, rows in sorted(got["rows"].items()):
            put(z, "t%s.json" % key, rows)
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tools")
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", required=True, help="where the release assets go (OWNER/NAME)")
    ap.add_argument("--release", help="the Overture release (default: the index's)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--all", action="store_true", help="make every cell's again, whatever it was made from")
    ap.add_argument("--shard", default="0/1", help="K/N: only every Nth of the block's cells, from the Kth")
    args = ap.parse_args(argv)
    sys.path.insert(0, args.tools)
    import building_bake as bb
    import coast_bake as cb
    with open(idx.INDEX) as f:
        index = json.load(f)
    release = args.release or index["release"]
    classes = bb.classes_hash()
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only
                   and (args.all or wanted(index, c, release, classes)))
    k, n = (int(v) for v in args.shard.split("/"))
    cells = cells[k::n]
    os.makedirs(args.out, exist_ok=True)
    tag = tag_of(release, args.only)

    def one(cell):
        row, col = (int(v) for v in cell.split("_"))
        for attempt in range(4):
            try:
                got = bb.cell_buildings(bb.fetch(cb.cell_box(row, col), release, log=lambda m: None), row, col, release)
                break
            except OSError:
                if attempt == 3:
                    raise
        data = zipped(got)
        h = hashlib.sha256(data).hexdigest()[:16]
        asset = "c%s-%s.bld.zip" % (cell, h)
        with open(os.path.join(args.out, asset), "wb") as f:
            f.write(data)
        n = sum(len(v) for v in got["rows"].values())
        entry = {"cell": cell, "release": release, "classes": classes, "hash": h, "bytes": len(data), "buildings": n,
                 "url": "https://github.com/%s/releases/download/%s/%s" % (args.repo, tag, asset)}
        with open(os.path.join(args.out, "c%s.bld" % cell), "w") as f:
            json.dump(entry, f)
        print("%s: %d buildings, %d KB" % (cell, n, len(data) // 1024), flush=True)
        return n

    with ThreadPoolExecutor(args.threads) as pool:
        n = sum(pool.map(one, cells))
    print("buildings: %d in %d cells of block %s (Overture %s), release %s" % (n, len(cells), args.only, release, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
