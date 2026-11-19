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

MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
AGENT = "torque-shed-world circuit bake (GitHub Actions; scripts/overpass_fetch.py)"

CORE = """[out:json][timeout:600];
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
MORE = """[out:json][timeout:600];
way["highway"="raceway"]({b})->.r;
(
  way["surface"~"^(gravel|sand|asphalt|paved|concrete)$"]["highway"!~"."](around.r:400);
  way["natural"~"^(sand|shingle)$"](around.r:400);
  way["landuse"~"^(grass|gravel_trap)$"](around.r:400);
  relation["natural"~"^(sand|shingle)$"](around.r:400);
);
out body geom;
"""


def ask(query):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(3):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=data, headers={"User-Agent": AGENT, "Accept": "application/json, */*"})
                with urllib.request.urlopen(req, timeout=700) as r:
                    body = json.loads(r.read().decode("utf-8"))
                if "elements" in body and not body.get("remark", "").lower().startswith("runtime error"):
                    return body["elements"]
                last = "%s: %s" % (url, body.get("remark", "no elements"))
            except Exception as e:  # noqa: BLE001 (any failure: the next mirror)
                last = "%s: %s" % (url, e)
            print("  (%s)" % last, flush=True)
            time.sleep(10)
        time.sleep(30 * (attempt + 1))
    raise SystemExit("Overpass: no answer (%s)" % last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", default="49.8,-8.8,61.0,2.0")
    ap.add_argument("--tile", type=float, default=2.0)
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
    for name, q in (("core", CORE), ("more", MORE)):
        seen, out = set(), []
        for t in tiles:
            b = "%.4f,%.4f,%.4f,%.4f" % t
            got = ask(q.format(b=b))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
