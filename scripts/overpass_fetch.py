"""[race tracks] The race circuits' OpenStreetMap data from the Overpass API, for scripts/circuit_bake.py: the box
cut into tiles (one big ask times out), each asked of the mirrors in turn, the answers merged into one Overpass
JSON per query (over/core.json, over/more.json).

    python3 scripts/overpass_fetch.py --box 49.8,-8.8,61.0,2.0 --tile 2.0 --out over
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# (the mirrors that answered on the night of Nov 19 first: overpass-api.de gave 502 and kumi 504 to almost every ask)
MIRRORS = ["https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
AGENT = "torque-shed-world circuit bake (GitHub Actions; scripts/overpass_fetch.py)"

CORE = """[out:json][timeout:280];
(
  way["highway"="raceway"]({b});
  way["area:highway"="raceway"]({b});
  way["leisure"~"^(track|motor_racing)$"]["sport"]({b});
  relation["leisure"~"^(track|motor_racing)$"]["sport"]({b});
  way["landuse"~"^(raceway|motor_racing)$"]({b});
  relation["landuse"~"^(raceway|motor_racing)$"]({b});
  way["building"="grandstand"]({b});
  way["leisure"="grandstand"]({b});
);
out body geom;
"""
MORE = """[out:json][timeout:90];
way["highway"="raceway"]({b})->.r;
(
  way["surface"~"^(gravel|sand|fine_gravel|pebblestone)$"]["highway"!~"."](around.r:200);
  way["natural"~"^(sand|shingle)$"](around.r:200);
  way["landuse"="gravel_trap"](around.r:200);
);
out body geom;
"""


def ask(query, must=True, wait=700):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(3 if must else 1):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": AGENT, "Accept": "application/json, */*"})
                with urllib.request.urlopen(req, timeout=wait) as r:
                    body = json.loads(r.read().decode("utf-8"))
                if "elements" in body and not body.get("remark", "").lower().startswith("runtime error"):
                    return body["elements"]
                last = "%s: %s" % (url, body.get("remark", "no elements"))
            except Exception as e:  # noqa: BLE001 (any failure: the next mirror)
                last = "%s: %s" % (url, e)
            print("  (%s)" % last, flush=True)
            time.sleep(10)
        time.sleep(30 * (attempt + 1))
    if must:
        raise SystemExit("Overpass: no answer (%s)" % last)
    print("  (left out: %s)" % last, flush=True)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", default="49.8,-8.8,61.0,2.0")
    ap.add_argument("--tile", type=float, default=2.0)
    ap.add_argument("--more-tile", type=float, default=0.25)
    ap.add_argument("--core-minutes", type=float, default=60)
    ap.add_argument("--more-minutes", type=float, default=20)
    ap.add_argument("--out", default="over")
    a = ap.parse_args()
    s, w, n, e = (float(v) for v in a.box.split(","))
    os.makedirs(a.out, exist_ok=True)
    tiles = []
    lat = s
    while lat < n - 1e-9:
        lon = w
        while lon < e - 1e-9:
            tiles.append((lat, lon, min(lat + a.tile, n), min(lon + a.tile, e)))
            lon += a.tile
        lat += a.tile
    def run(name, q, boxes, must, budget=None, wait=120):
        seen, out, missed = set(), [], []
        began = time.time()
        for t in boxes:
            b = "%.4f,%.4f,%.4f,%.4f" % t
            if budget and time.time() - began > budget:
                print("%s %s: left out (out of time)" % (name, b), flush=True)
                missed.append(b)
                continue
            got = ask(q.format(b=b), must=must) if must else ask(q.format(b=b), must=False, wait=wait)
            if got is None:
                missed.append(b)
                continue
            new = 0
            for el in got:
                k = (el.get("type"), el.get("id"))
                if k in seen:
                    continue
                seen.add(k)
                out.append(el)
                new += 1
            print("%s %s: %d elements (%d new)" % (name, b, len(got), new), flush=True)
        with open(os.path.join(a.out, name + ".json"), "w") as f:
            json.dump({"elements": out}, f)
        print("%s: %d elements in all" % (name, len(out)), flush=True)
        if missed:
            # (ask again later with --box for each: a run adds to what is baked, cell by cell)
            print("%s: %d boxes left out: %s" % (name, len(missed), " ".join(missed)), flush=True)
        return out
    # (each tile asked of every mirror once, five minutes a mirror; a tile no mirror answers is left out and named,
    # so one slow night still bakes the rest)
    core = run("core", CORE, tiles, False, budget=a.core_minutes * 60, wait=300)
    if not core:
        raise SystemExit("Overpass: no circuits at all")
    # (the run-off only round the raceways found: a small box, a.more_tile degrees, for each square that has one)
    squares = set()
    for el in core:
        if el.get("type") != "way" or el.get("tags", {}).get("highway") != "raceway":
            continue
        for g in el.get("geometry", []):
            squares.add((int(g["lat"] // a.more_tile), int(g["lon"] // a.more_tile)))
    boxes = [(r * a.more_tile, c * a.more_tile, (r + 1) * a.more_tile, (c + 1) * a.more_tile) for r, c in sorted(squares)]
    print("run-off: %d squares with raceways" % len(boxes), flush=True)
    # (at most --more-minutes for it all, each square asked for two minutes a mirror: run-off is a nicety)
    run("more", MORE, boxes, False, budget=a.more_minutes * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
