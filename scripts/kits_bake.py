#!/usr/bin/env python3
"""[everyday kits stage 2] The map data pass for the everyday asset kits (the UE game's "Everyday Britain asset kits"
plan): the things the kits need that the cells' features/, ground/ and places/ files don't carry, from an
OpenStreetMap extract, into OUT/cROW_COL.kits for index.py (kits/ and the index's "kits").

    python3 scripts/kits_bake.py --pbf GB.osm.pbf --only R_C --out DIR [--squares LAT,LON ...] [--no-cut]

Each 1 degree square of the block is cut from the extract once with osmium-tool (as roadx_backfill.py does), then read
with pyosmium. --no-cut reads --pbf as it is (a small test file).

A cell's file: {"format": 1, "cell", "release", "kinds": [...], "words": [...],
  "points": [[kind, word, word2, lat, lon], ...],
  "areas":  [[kind, word, word2, lat, lon, dlat, dlon, ...], ...]   (outer ring, first point absolute, then steps),
  "lines":  [[kind, word, word2, layer, under, lat, lon, dlat, dlon, ...], ...],
  "km": {"motorway": km, ...}}
lat and lon in 1e-5 degrees (as places/). word and word2 index "words" (0 = none). For lines, layer is the way's
layer tag (0 when none) and under a bit mask of what a bridge crosses: 1 water, 2 railway, 4 road, 8 path.
A point is in the cell its position is in; an area or line in the cell its middle is in."""
import argparse
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

import osmium

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

E5 = 100000.0
ROAD_KM = ("motorway", "motorway_link", "trunk", "trunk_link", "primary", "secondary", "tertiary", "unclassified",
           "residential", "service", "track")
BIG_ROADS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
             "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road", "track"}
PATHS = {"footway", "path", "cycleway", "bridleway", "steps", "pedestrian"}
WATER = {"river", "stream", "canal", "drain", "ditch", "tidal_channel"}
RAILS = {"rail", "light_rail", "narrow_gauge", "subway", "tram", "disused", "abandoned", "preserved", "miniature"}


def cell_of(lat, lon):
    return "%d_%d" % (int(math.floor((lat + 90.0) * 4.0)), int(math.floor((lon + 180.0) * 4.0)))


def has(tags, key, *values):
    v = tags.get(key)
    return v is not None and (not values or v in values)


def what_point(t):
    """(kind, word, word2) of a node or area's tags, or None: the kits' things."""
    a = t.get("amenity")
    mm = t.get("man_made")
    hw = t.get("highway")
    em = t.get("emergency")
    le = t.get("leisure")
    b = t.get("building")
    # farmyards
    if mm == "bunker_silo":
        return ("silage_clamp", t.get("content", ""), "")
    if mm == "storage_tank" and t.get("content", t.get("substance", "")) in ("slurry", "manure", "sewage", "biogas", "water", "oil", "fuel", "gas", "milk", "grain", "fodder"):
        return ("storage_tank", t.get("content", t.get("substance", "")), "")
    if mm == "silo" and (t.get("content") or t.get("crop")):
        return ("farm_silo", t.get("content", t.get("crop", "")), "")
    if b in ("cowshed", "stable", "sty", "barn", "farm_auxiliary", "greenhouse", "glasshouse", "slurry_tank", "silo") and not a:
        return None   # (outlines: the cells' bld/ has them)
    if le == "horse_riding" or t.get("landuse") == "animal_keeping":
        return ("animal_keeping", "", "")
    # the village set
    if a == "school" or (b == "school" and t.get("name")):
        n = t.get("name", "").lower()
        level = "primary" if any(w in n for w in ("primary", "infant", "junior", "first school", "c of e", "ce school", "church school", "c.e.")) \
            else "secondary" if any(w in n for w in ("academy", "high school", "college", "grammar", "secondary", "comprehensive")) else ""
        return ("school", level or t.get("isced:level", "")[:8], "")
    if a in ("community_centre", "village_hall") or (a == "townhall" and t.get("townhall:type") == "village"):
        n = t.get("name", "").lower()
        return ("village_hall", "village_hall" if a == "village_hall" or t.get("community_centre") == "village_hall" or "village hall" in n else
                "church_hall" if "church hall" in n or "parish hall" in n else "scout_hut" if "scout" in n or "guide" in n else "", "")
    if t.get("historic") == "memorial" or a == "memorial":
        m = t.get("memorial", t.get("memorial:type", ""))
        war = m == "war_memorial" or "war" in t.get("memorial:type", "") or "war memorial" in t.get("name", "").lower() or has(t, "subject:wikidata")
        shape = t.get("memorial:type", "") if m == "war_memorial" else m
        if war:
            return ("war_memorial", shape if shape not in ("war_memorial", "yes") else "", t.get("material", ""))
        if m in ("plaque", "blue_plaque", "bench", "tree", "ghost_bike", "stolperstein", "yes", ""):
            return None
        return ("memorial", m, t.get("material", ""))
    sport = t.get("sport", "")
    if "cricket" in sport.split(";") and le in ("pitch", "sports_centre", "recreation_ground", "track", None):
        return ("cricket", le or "", "")
    if "bowls" in sport.split(";") and le in ("pitch", "sports_centre", None):
        return ("bowling_green", "", "")
    if b == "pavilion" or a == "pavilion" or (b == "sports_hall" and "cricket" in t.get("name", "").lower()):
        return ("pavilion", "", "")
    if (a == "shelter" and t.get("shelter_type") == "public_transport") or (hw == "bus_stop" and t.get("shelter") == "yes"):
        return ("bus_shelter", t.get("material", t.get("building:material", "")), "")
    if a == "shelter" and t.get("shelter_type") in ("weather_shelter", "gazebo", "pavilion"):
        return ("shelter", t.get("shelter_type", ""), t.get("material", ""))
    if a == "waste_basket":
        return ("waste_basket", "", "")
    if a == "grit_bin":
        return ("grit_bin", "", "")
    if a == "notice_board" or (t.get("tourism") == "information" and t.get("information") == "board" and t.get("board_type") in ("notice", "community", "parish")):
        return ("notice_board", "", "")
    if a == "telephone" and em != "phone":
        return None   # (the cells have phone boxes)
    if em == "defibrillator":
        return ("defibrillator", "", "")
    if hw == "bus_stop":
        return ("bus_stop", t.get("shelter", ""), "")
    if t.get("traffic_sign") in ("city_limit", "GB:city_limit") or t.get("traffic_sign:forward") == "city_limit":
        return ("place_sign", "", "")
    # petrol stations and roadside stops
    if a == "fuel":
        flags = []
        if t.get("shop") in ("convenience", "kiosk", "yes") or t.get("fuel:shop") == "yes":
            flags.append("shop")
        if t.get("car_wash") == "yes":
            flags.append("wash")
        if t.get("compressed_air") == "yes":
            flags.append("air")
        if t.get("fuel:lpg") == "yes":
            flags.append("lpg")
        if t.get("hgv") == "yes" or t.get("fuel:HGV_diesel") == "yes":
            flags.append("hgv")
        return ("fuel", "_".join(flags), "")
    if a == "car_wash":
        return ("car_wash", "", "")
    if a == "compressed_air":
        return ("compressed_air", "", "")
    if a == "vacuum_cleaner":
        return ("vacuum", "", "")
    if a == "charging_station":
        return None   # (the cells have them)
    if t.get("shop") in ("convenience", "kiosk") and not a:
        return ("convenience_shop", "", "")
    if a == "parking" and t.get("parking") in ("layby", "lay_by", "street_side"):
        return ("layby", t.get("parking"), t.get("surface", ""))
    if hw == "rest_area":
        return ("rest_area", "", "")
    if hw == "services":
        return ("services", "", "")
    if a in ("cafe", "fast_food"):
        return (a, "truck_stop" if t.get("hgv") == "yes" or "truck" in t.get("name", "").lower() or "transport" in t.get("name", "").lower() else
                "van" if t.get("mobile") == "yes" or "van" in t.get("name", "").lower() or "snack" in t.get("name", "").lower() or t.get("building") == "no" else "", "")
    if a == "toilets":
        return ("toilets", "", "")
    # fast roads
    if hw == "speed_camera" or t.get("enforcement") in ("maxspeed", "average_speed") or t.get("traffic_sign") == "GB:880":
        return ("speed_camera", t.get("enforcement", "maxspeed"), t.get("maxspeed", ""))
    if em == "phone" or a == "emergency_phone":
        return ("emergency_phone", "", "")
    if mm == "gantry" or t.get("highway") == "gantry":
        return ("gantry", t.get("gantry:type", t.get("gantry", "")), "")
    if hw == "milestone" and t.get("distance") and t.get("railway") is None:
        return ("marker_post", "", "")
    if t.get("traffic_calming") is None and t.get("highway") == "emergency_bay":
        return ("emergency_bay", "", "")
    # the coast
    if b == "beach_hut" or a == "beach_hut" or t.get("tourism") == "beach_hut":
        return ("beach_hut", "", "")
    if le == "slipway":
        return ("slipway", t.get("surface", ""), "")
    if em == "lifeboat_station" or a == "lifeboat_station" or (b and "lifeboat" in t.get("name", "").lower()):
        return ("lifeboat_station", "", "")
    if t.get("harbour") == "yes" or t.get("landuse") == "harbour" or t.get("seamark:type") in ("harbour",):
        return ("harbour", t.get("harbour:category", t.get("seamark:harbour:category", "")), "")
    if t.get("mooring") in ("yes", "public", "private", "visitor") or t.get("seamark:type") == "mooring" or (le == "marina" and False):
        return ("mooring", "", "")
    if t.get("waterway") == "boatyard" or t.get("craft") == "boatbuilder" or t.get("shop") == "boat":
        return ("boatyard", "", "")
    if mm == "lighthouse":
        return None   # (places/ has them)
    if le == "beach_resort" or t.get("natural") == "beach" and False:
        return ("beach_resort", "", "")
    # yards and estates (the industrial thread's stage 3, counted only)
    if a == "recycling" and t.get("recycling_type") == "container":
        return ("recycling_bank", "", "")
    if t.get("landuse") == "depot" or t.get("industrial") == "depot":
        return ("depot", "", "")
    if a == "bicycle_parking":
        return None
    if le == "playground" or t.get("playground"):
        return ("play_equipment", t.get("playground", ""), "") if t.get("playground") else None
    if le == "golf_course" or a in ("allotments",):
        return None
    return None


def what_line(t):
    """(kind, word, word2) of a way that is a line the kits need, or None."""
    hw, rw, ww = t.get("highway"), t.get("railway"), t.get("waterway")
    br = t.get("bridge")
    if br and br != "no":
        what = "road" if hw in BIG_ROADS else "path" if hw in PATHS else "rail" if rw in RAILS else "water" if ww in ("canal", "river") else ""
        if not what:
            return None
        style = t.get("bridge:structure", "") or ("viaduct" if br == "viaduct" else "aqueduct" if br == "aqueduct" else "")
        if br in ("movable", "boardwalk", "covered", "cantilever", "trestle", "low_water_crossing"):
            style = style or br
        return ("bridge_" + what, style, t.get("bridge:material", t.get("material", "")))
    if t.get("man_made") == "embankment" or t.get("embankment") == "yes":
        return None
    if (hw in PATHS or hw == "pedestrian") and (t.get("footway") == "promenade" or "promenade" in t.get("name", "").lower() or t.get("name", "").lower().endswith(" parade")):
        return ("promenade", "", "")
    if (t.get("barrier") == "wall" and t.get("wall") in ("sea_wall", "flood_wall")) or t.get("man_made") in ("sea_wall", "flood_wall"):
        return ("sea_wall", "", "")
    if t.get("barrier") in ("guard_rail",) and hw is None:
        return None   # (roadx/ has crash barriers)
    if t.get("man_made") == "gantry":
        return ("gantry", t.get("gantry:type", ""), "")
    if t.get("barrier") == "fence" and t.get("fence_type") in ("palisade", "metal_bars", "security"):
        return ("palisade", t.get("fence_type", ""), "")
    return None


class Handler(osmium.SimpleHandler):
    def __init__(self, box):
        super().__init__()
        self.box = box   # (s, w, n, e) the square
        self.points, self.areas, self.lines = [], [], []
        self.km = defaultdict(float)
        self.under = defaultdict(list)   # what can be under a bridge: (mask, ring of (lat, lon))
        self.devices = {}               # enforcement relations' device node ids -> (kind, word)

    def inside(self, lat, lon):
        s, w, n, e = self.box
        return s <= lat < n and w <= lon < e

    def node(self, n):
        if not n.tags or not n.location.valid():
            return
        lat, lon = n.location.lat, n.location.lon
        if not self.inside(lat, lon):
            return
        got = what_point(n.tags)
        if got:
            self.points.append((got, lat, lon, n.id))

    def way(self, w):
        t = w.tags
        hw, rw, ww = t.get("highway"), t.get("railway"), t.get("waterway")
        try:
            pts = [(nd.location.lat, nd.location.lon) for nd in w.nodes if nd.location.valid()]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2:
            return
        # (road km by class: each step in the cell of its middle; only the square's)
        if hw in ROAD_KM:
            for (a0, o0), (a1, o1) in zip(pts, pts[1:]):
                ma, mo = (a0 + a1) * 0.5, (o0 + o1) * 0.5
                if self.inside(ma, mo):
                    dy = (a1 - a0) * 111320.0
                    dx = (o1 - o0) * 111320.0 * math.cos(math.radians(ma))
                    self.km[(cell_of(ma, mo), hw)] += math.hypot(dx, dy) / 1000.0
        br = t.get("bridge")
        if not (br and br != "no") and t.get("tunnel") in (None, "no"):
            mask = 1 if ww in WATER else 2 if rw in ("rail", "light_rail", "narrow_gauge", "preserved", "disused", "subway") else 4 if hw in BIG_ROADS else 8 if hw in PATHS else 0
            if mask:
                self.under_add(mask, pts)
        got = what_line(t)
        if got:
            layer = t.get("layer", "0")
            try:
                layer = int(float(layer))
            except ValueError:
                layer = 0
            self.lines.append((got, pts, layer, w.id))

    def under_add(self, mask, pts):
        for (a0, o0), (a1, o1) in zip(pts, pts[1:]):
            key = (int(a0 * 200), int(o0 * 200))
            self.under[key].append((mask, a0, o0, a1, o1))

    def area(self, a):
        got = what_point(a.tags)
        if not got:
            return
        try:
            for outer in a.outer_rings():
                ring = [(nd.lat, nd.lon) for nd in outer if nd.location.valid()]
                if len(ring) > 1 and ring[0] == ring[-1]:
                    ring = ring[:-1]
                break
            else:
                return
        except osmium.InvalidLocationError:
            return
        if len(ring) < 3:
            return
        lat = sum(p[0] for p in ring) / len(ring)
        lon = sum(p[1] for p in ring) / len(ring)
        if self.inside(lat, lon):
            self.areas.append((got, ring, lat, lon))

    def relation(self, r):
        if r.tags.get("type") == "enforcement" and r.tags.get("enforcement") in ("maxspeed", "average_speed", "traffic_signals"):
            for m in r.members:
                if m.type == "n" and m.role == "device":
                    self.devices[m.ref] = ("speed_camera", r.tags.get("enforcement"), r.tags.get("maxspeed", ""))


def crosses(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) > 0) != (o(a, b, d) > 0) and (o(c, d, a) > 0) != (o(c, d, b) > 0)


def under_of(h, pts):
    mask = 0
    for (a0, o0), (a1, o1) in zip(pts, pts[1:]):
        k0 = (int(a0 * 200), int(o0 * 200))
        seen = set()
        for da in (-1, 0, 1):
            for do in (-1, 0, 1):
                for seg in h.under.get((k0[0] + da, k0[1] + do), ()):
                    if id(seg) in seen:
                        continue
                    seen.add(id(seg))
                    if crosses((a0, o0), (a1, o1), (seg[1], seg[2]), (seg[3], seg[4])):
                        mask |= seg[0]
    return mask


def simplify(ring, tol=0.00002):
    """Douglas-Peucker in degrees (about 2 m): outlines kept small."""
    if len(ring) < 4:
        return ring
    def rec(pts):
        a, b = pts[0], pts[-1]
        dmax, imax = 0.0, 0
        for i in range(1, len(pts) - 1):
            p = pts[i]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1e-12
            d = abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / L
            if d > dmax:
                dmax, imax = d, i
        if dmax <= tol:
            return [a, b]
        left = rec(pts[:imax + 1])
        return left[:-1] + rec(pts[imax:])
    ring = list(ring)
    if ring[0] == ring[-1]:
        # (a closed ring: cut at the point furthest from the first, each half simplified)
        ring = ring[:-1]
        far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
        if far == 0:
            return ring
        return rec(ring[:far + 1])[:-1] + rec(ring[far:] + [ring[0]])[:-1]
    return rec(ring)


def packed(pts):
    out, la, lo = [], None, None
    for lat, lon in pts:
        a, o = int(round(lat * E5)), int(round(lon * E5))
        if la is None:
            out += [a, o]
        else:
            out += [a - la, o - lo]
        la, lo = a, o
    return out


def bake_square(pbf, box, cells, release):
    """The kits' things of the cells (a set of "ROW_COL") in box, from pbf: {cell: baked}."""
    h = Handler(box)
    h.apply_file(pbf, locations=True, idx="flex_mem")
    words, kinds = [""], []
    wi, ki = {"": 0}, {}

    def W(w):
        w = (w or "")[:32]
        if w not in wi:
            wi[w] = len(words)
            words.append(w)
        return wi[w]

    def K(k):
        if k not in ki:
            ki[k] = len(kinds)
            kinds.append(k)
        return ki[k]

    out = {c: {"points": [], "areas": [], "lines": [], "km": {}} for c in cells}
    seen_nodes = set()
    for (k, w1, w2), lat, lon, nid in h.points:
        if nid in h.devices and k != "speed_camera":
            k, w1, w2 = h.devices[nid]
        c = cell_of(lat, lon)
        if c in out:
            out[c]["points"].append([K(k), W(w1), W(w2), int(round(lat * E5)), int(round(lon * E5))])
            seen_nodes.add(nid)
    for (k, w1, w2), ring, lat, lon in h.areas:
        c = cell_of(lat, lon)
        if c in out:
            out[c]["areas"].append([K(k), W(w1), W(w2)] + packed(simplify(ring)))
    for (k, w1, w2), pts, layer, wid in h.lines:
        mid = pts[len(pts) // 2]
        c = cell_of(*mid)
        if c not in out:
            continue
        under = under_of(h, pts) if k.startswith("bridge_") else 0
        out[c]["lines"].append([K(k), W(w1), W(w2), layer, under] + packed(simplify(pts, 0.00001)))
    for (c, cls), km in h.km.items():
        if c in out:
            out[c]["km"][cls] = round(out[c]["km"].get(cls, 0.0) + km, 2)
    baked = {}
    for c, d in out.items():
        baked[c] = {"format": 1, "cell": c, "release": release, "kinds": kinds, "words": words,
                    "points": d["points"], "areas": d["areas"], "lines": d["lines"], "km": d["km"]}
    return baked


def report(b):
    from collections import Counter
    n = Counter(b["kinds"][r[0]] for r in b["points"] + b["areas"] + b["lines"])
    return "%s: %s" % (b["cell"], ", ".join("%s %d" % kv for kv in sorted(n.items())))


def main(argv=None):
    import index as idx
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pbf", required=True)
    ap.add_argument("--only", required=True, help="the 5 degree block (R_C)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--squares", nargs="*", default=[], help="just these 1 degree squares (LAT,LON of their corner)")
    ap.add_argument("--no-cut", action="store_true", help="read --pbf whole (a small test file)")
    args = ap.parse_args(argv)
    with open(idx.INDEX) as f:
        index = json.load(f)
    release = index["release"]
    uk = set(index.get("roadx", {}))   # (the cells the extract covers: those with the road itself baked)
    cells = sorted(c for c, e in index["cells"].items() if not e.get("empty") and idx.block_of(c) == args.only and (not uk or c in uk))
    squares = defaultdict(set)
    for c in cells:
        row, col = (int(v) for v in c.split("_"))
        squares[(row // 4, col // 4)].add(c)
    only = {tuple(int(float(v)) for v in s.split(",")) for s in args.squares}
    os.makedirs(args.out, exist_ok=True)
    os.makedirs("cuts", exist_ok=True)
    n = 0
    for (sr, sc), members in sorted(squares.items()):
        s, w = sr - 90.0, sc - 180.0
        if only and (int(round(s)), int(round(w))) not in only:
            continue
        box = (s, w, s + 1.0, w + 1.0)
        if args.no_cut:
            cut = args.pbf
        else:
            cut = os.path.join("cuts", "k%d_%d.osm.pbf" % (sr, sc))
            subprocess.run(["osmium", "extract", "-b", "%.3f,%.3f,%.3f,%.3f" % (w - 0.02, s - 0.02, w + 1.02, s + 1.02),
                            "-s", "smart", "--overwrite", "-o", cut, args.pbf], check=True)
        for c, baked in sorted(bake_square(cut, box, members, release).items()):
            if not (baked["points"] or baked["areas"] or baked["lines"] or baked["km"]):
                continue
            with open(os.path.join(args.out, "c%s.kits" % c), "w") as f:
                json.dump(baked, f, separators=(",", ":"), ensure_ascii=False)
            print(report(baked), flush=True)
            n += 1
        if not args.no_cut:
            os.remove(cut)
    print("kits: %d cells of block %s" % (n, args.only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
