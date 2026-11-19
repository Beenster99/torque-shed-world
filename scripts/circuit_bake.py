#!/usr/bin/env python3
"""[race tracks stage 1] The UK's race circuits from OpenStreetMap, for the game's Ride UK: every highway=raceway way
(the track, its pit lane, the short and long layouts), the run-off round it (gravel traps, sand, grass, tarmac), the
circuit's own outline and its grandstands, cut into the world's 0.25 degree cells.

    python3 scripts/circuit_bake.py EXTRACT.osm.pbf [MORE.osm.pbf ...] --out DIR [--release RELEASE] [--list LIST.json]

Each cell with any of it gets DIR/cROW_COL.circuit (index.py puts it in circuit/cROW_COL.json and its hash in the
index's "circuits"):

    {"format": 1, "cell": "ROW_COL", "release", "osm": "the extract's date",
     "kinds": [...], "names": [...],
     "circuits": [[id, name, kind, lat, lon, length_m], ...],       the circuits with a way in the cell
     "ways": [[osm id, kind, width_dm, oneway, name, circuit id, lat, lon, dlat, dlon, ...], ...],
     "areas": [[osm id, kind, name, circuit id, lat, lon, dlat, dlon, ...], ...]}

Points are 1e-5 degrees, the first whole and the rest steps from the one before (as the other bakes' lines). A way that
runs over two cells is in both, whole: the game keeps it once by its id. A circuit's id is the same in every cell
(its first way's OSM id), so the game joins its pieces.

kind of a way: "track" (the circuit), "pit" (its pit lane), "kart" (a kart track), "dirt" (motocross, autograss,
rallycross on loose ground); oneway 1 as drawn, -1 against, 0 not said. kind of an area: "outline" (the circuit's
own: leisure=track or a motor sport ground), "gravel", "sand", "grass", "tarmac" (paved run-off or paddock),
"grandstand".

The list (--list) is the stage 1 table: every circuit found, its length, how much of it is mapped, and what else."""
import argparse
import json
import math
import os
import sys

FORMAT = 1
CELL_DEG = 0.25
NEAR_M = 400.0            # run-off, gravel and stands this close to a circuit's track belong to it
JOIN_M = 30.0             # raceway ways whose ends are this close are one circuit
UNPAVED = {"dirt", "gravel", "grass", "ground", "sand", "unpaved", "compacted", "mud", "earth", "fine_gravel", "grass_paver"}
DIRT_SPORTS = {"motocross", "autocross", "rallycross", "autograss", "dirt_bike", "speedway", "enduro", "trial"}
MOTOR_SPORTS = {"motor", "motorsport", "motorcycle", "motorcycle_racing", "motor_racing", "karting", "superbike"} | DIRT_SPORTS
WAY_KINDS = ["track", "pit", "kart", "dirt"]
AREA_KINDS = ["outline", "gravel", "sand", "grass", "tarmac", "grandstand"]

# The circuits the plan names (general knowledge, so a nameless circuit outline still gets its name), each a rough
# middle; matched within 3 km.
KNOWN = [
    ("Cadwell Park", 53.3107, -0.0626), ("Brands Hatch", 51.3569, 0.2626), ("Donington Park", 52.8306, -1.3750),
    ("Oulton Park", 53.1792, -2.6150), ("Silverstone", 52.0733, -1.0147), ("Snetterton", 52.4636, 0.9456),
    ("Thruxton", 51.2076, -1.6095), ("Mallory Park", 52.5994, -1.3378), ("Croft", 54.4553, -1.5558),
    ("Castle Combe", 51.4917, -2.2153), ("Goodwood", 50.8580, -0.7590), ("Lydden Hill", 51.1772, 1.1986),
    ("Rockingham", 52.5153, -0.6575), ("Knockhill", 56.1300, -3.5100), ("Anglesey (Trac Môn)", 53.1886, -4.4967),
    ("Pembrey", 51.7056, -4.3239), ("Kirkistown", 54.4561, -5.4672), ("Bishopscourt", 54.3022, -5.5717),
    ("Three Sisters", 53.5244, -2.6156), ("Bedford Autodrome", 52.2350, -0.4740), ("Blyton Park", 53.4590, -0.6880),
    ("Curborough", 52.7110, -1.8100), ("Llandow", 51.4310, -3.4960), ("Ty Croes", 53.1886, -4.4967),
]


def cell_of(lat, lon):
    return int(math.floor((lat + 90.0) / CELL_DEG)), int(math.floor((lon + 180.0) / CELL_DEG))


def metres(a, b):
    """Rough distance in metres between (lat, lon) a and b (good enough within a few km)."""
    k = math.cos(math.radians((a[0] + b[0]) * 0.5))
    return math.hypot((a[0] - b[0]) * 111320.0, (a[1] - b[1]) * 111320.0 * k)


def length_of(pts):
    return sum(metres(pts[i - 1], pts[i]) for i in range(1, len(pts)))


def width_of(tags):
    """A way's width (m) from width=*, est_width=*: "12", "12 m", "40'"; 0 where the map says nothing."""
    for key in ("width", "est_width"):
        v = (tags.get(key) or "").strip().lower().replace(",", ".")
        if not v:
            continue
        try:
            if v.endswith("'") or v.endswith("ft"):
                return float(v.rstrip("'ft ").strip()) * 0.3048
            return float(v.split()[0].rstrip("m"))
        except ValueError:
            continue
    return 0.0


def way_kind(tags):
    """The kind of a raceway way (WAY_KINDS), or None for one to leave out (planned, disused, a slot-car track)."""
    if tags.get("highway") != "raceway":
        return None
    for key in ("disused", "abandoned", "proposed", "construction"):
        if tags.get(key) in ("yes",) or tags.get(key + ":highway"):
            return None
    if tags.get("access") == "no" and tags.get("raceway") in ("slot_car",):
        return None
    sport = set((tags.get("sport") or "").replace(",", ";").split(";"))
    words = " ".join(tags.get(k, "") for k in ("raceway", "service", "name", "description")).lower()
    if "pit" in words.split() or "pit_lane" in words or "pitlane" in words or "pit lane" in words:
        return "pit"
    if sport & DIRT_SPORTS or (tags.get("surface") or "").lower() in UNPAVED:
        return "dirt"
    if "karting" in sport or "kart" in words:
        return "kart"
    return "track"


def area_kind(tags):
    """The kind of an area (AREA_KINDS), or None."""
    sport = set((tags.get("sport") or "").replace(",", ";").split(";"))
    if tags.get("area:highway") == "raceway" or (tags.get("highway") == "raceway" and tags.get("area") == "yes"):
        return "tarmac"
    if tags.get("building") == "grandstand" or tags.get("leisure") == "grandstand" or tags.get("building:use") == "grandstand":
        return "grandstand"
    if (tags.get("leisure") in ("track", "sports_centre", "stadium") or tags.get("landuse") in ("motor_racing", "raceway")) and sport & MOTOR_SPORTS:
        return "outline"
    if tags.get("landuse") == "raceway" or tags.get("leisure") == "motor_racing":
        return "outline"
    if (tags.get("surface") or "") == "gravel" or tags.get("landuse") == "gravel_trap" or tags.get("natural") == "shingle":
        return "gravel"
    if tags.get("natural") == "sand" or (tags.get("surface") or "") == "sand":
        return "sand"
    if tags.get("landuse") == "grass" or tags.get("surface") == "grass":
        return "grass"
    # (car parks are the car parks thread's: Ride UK draws those from the ground bake)
    if tags.get("amenity") != "parking" and tags.get("surface") in ("asphalt", "paved", "concrete") and not tags.get("building"):
        return "tarmac"
    return None


def collect(paths, boxes=None):
    """Every raceway way and candidate area in the extracts: (ways, areas), each a list of dicts. With boxes (a set of
    (lat * 100, lon * 60) squares, about 1 km), only areas starting in one of them are kept, and no ways."""
    import osmium

    ways, areas = [], []

    class H(osmium.SimpleHandler):
        def way(self, w):
            if boxes is not None:
                return
            tags = {t.k: t.v for t in w.tags}
            kind = way_kind(tags)
            if kind is None:
                return
            try:
                pts = [(n.location.lat, n.location.lon) for n in w.nodes if n.location.valid()]
            except osmium.InvalidLocationError:
                return
            if len(pts) < 2:
                return
            oneway = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}.get(tags.get("oneway", ""), 0)
            ways.append({"id": w.id, "kind": kind, "tags": tags, "pts": pts, "width": width_of(tags), "oneway": oneway,
                         "name": tags.get("name", ""), "ends": (w.nodes[0].ref, w.nodes[len(w.nodes) - 1].ref)})

        def area(self, a):
            tags = {t.k: t.v for t in a.tags}
            kind = area_kind(tags)
            if kind is None:
                return
            for ring in a.outer_rings():
                if boxes is not None:
                    first = next(iter(ring))
                    if not first.location.valid() or (int(math.floor(first.lat * 100)), int(math.floor(first.lon * 60))) not in boxes:
                        break
                pts = [(n.lat, n.lon) for n in ring if n.location.valid()]
                if len(pts) >= 4:
                    areas.append({"id": a.orig_id(), "kind": kind, "name": tags.get("name", ""), "pts": pts, "tags": tags})
                break

    for p in paths:
        H().apply_file(p, locations=True, idx="flex_mem")
    return ways, areas


def collect_overpass(paths, boxes=None):
    """As collect, from Overpass API answers (JSON, "out body geom": ways with their nodes and geometry,
    multipolygon relations with their members' geometry)."""
    ways, areas = [], []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for el in data.get("elements", []):
            tags = el.get("tags") or {}
            if el.get("type") == "way":
                geom = [(g["lat"], g["lon"]) for g in el.get("geometry") or [] if g]
                if len(geom) < 2:
                    continue
                kind = way_kind(tags) if boxes is None else None
                if kind is not None:
                    nodes = el.get("nodes") or [None, None]
                    oneway = {"yes": 1, "true": 1, "1": 1, "-1": -1, "reverse": -1}.get(tags.get("oneway", ""), 0)
                    ways.append({"id": el["id"], "kind": kind, "tags": tags, "pts": geom, "width": width_of(tags), "oneway": oneway,
                                 "name": tags.get("name", ""), "ends": (nodes[0], nodes[-1])})
                akind = area_kind(tags)
                if akind is not None and geom[0] == geom[-1] and len(geom) >= 4:
                    if boxes is not None and (int(math.floor(geom[0][0] * 100)), int(math.floor(geom[0][1] * 60))) not in boxes:
                        continue
                    areas.append({"id": el["id"] * 2, "kind": akind, "name": tags.get("name", ""), "pts": geom, "tags": tags})
            elif el.get("type") == "relation" and tags.get("type") == "multipolygon":
                akind = area_kind(tags)
                if akind is None:
                    continue
                for m in el.get("members") or []:
                    if m.get("role") != "outer" or not m.get("geometry"):
                        continue
                    geom = [(g["lat"], g["lon"]) for g in m["geometry"] if g]
                    if len(geom) >= 4:
                        if boxes is not None and (int(math.floor(geom[0][0] * 100)), int(math.floor(geom[0][1] * 60))) not in boxes:
                            continue
                        areas.append({"id": el["id"] * 2 + 1, "kind": akind, "name": tags.get("name", ""), "pts": geom, "tags": tags})
                        break
    return ways, areas


def group(ways, areas):
    """The circuits: raceway ways joined where they share an end or their ends are within JOIN_M, or lie in the same
    circuit outline. Returns a list of circuits, each {id, ways, areas, name, kind, lat, lon, length}."""
    n = len(ways)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    by_node = {}
    for i, w in enumerate(ways):
        for ref in w["ends"]:
            by_node.setdefault(ref, []).append(i)
    for members in by_node.values():
        for j in members[1:]:
            join(members[0], j)
    # (ends close together, and every point near another way's: a pit lane drawn a few metres off the track)
    grid = {}
    for i, w in enumerate(ways):
        for p in w["pts"][:: max(1, len(w["pts"]) // 40)] + [w["pts"][-1]]:
            grid.setdefault((round(p[0] * 2000), round(p[1] * 1200)), set()).add(i)
    for i, w in enumerate(ways):
        for p in (w["pts"][0], w["pts"][-1]):
            key = (round(p[0] * 2000), round(p[1] * 1200))
            for dk in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                for j in grid.get((key[0] + dk[0], key[1] + dk[1]), ()):
                    if j != i and min(metres(p, q) for q in ways[j]["pts"]) < JOIN_M:
                        join(i, j)
    outlines = [a for a in areas if a["kind"] == "outline"]
    for a in outlines:
        inside = [i for i, w in enumerate(ways) if inside_ring(mid_point(w["pts"]), a["pts"])]
        for j in inside[1:]:
            join(inside[0], j)
    circuits = {}
    for i in range(n):
        circuits.setdefault(find(i), []).append(i)
    out = []
    for root, members in circuits.items():
        ws = [ways[i] for i in members]
        # (the circuit's kind: its track's; a group of only pit lane is an oddity, kept as a track)
        kinds = [w["kind"] for w in ws]
        kind = "track" if "track" in kinds else "kart" if "kart" in kinds else "dirt" if "dirt" in kinds else "track"
        track_len = sum(length_of(w["pts"]) for w in ws if w["kind"] in ("track", "kart", "dirt"))
        lat = sum(w["pts"][k][0] for w in ws for k in range(len(w["pts"]))) / sum(len(w["pts"]) for w in ws)
        lon = sum(w["pts"][k][1] for w in ws for k in range(len(w["pts"]))) / sum(len(w["pts"]) for w in ws)
        # (a circuit of only a few hundred metres of "track" is a kart or a test pad unless the map says more)
        if kind == "track" and track_len < 800.0:
            kind = "kart"
        out.append({"id": min(w["id"] for w in ws), "ways": ws, "kind": kind, "lat": lat, "lon": lon, "length": track_len,
                    "areas": [], "name": ""})
    assign(out, areas)
    out.sort(key=lambda c: (-c["length"], c["id"]))
    return out


def boxes_of(circuits):
    """The ~1 km squares within about NEAR_M of the circuits' tracks (collect's boxes)."""
    out = set()
    for c in circuits:
        for w in c["ways"]:
            for p in w["pts"]:
                i, j = int(math.floor(p[0] * 100)), int(math.floor(p[1] * 60))
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        out.add((i + di, j + dj))
    return out


def assign(out, areas):
    """Areas near a circuit's track belong to it (the nearest within NEAR_M); then each circuit's name."""
    for a in areas:
        m = mid_point(a["pts"])
        best, bd = None, NEAR_M
        for c in out:
            if metres(m, (c["lat"], c["lon"])) > 6000.0:
                continue
            if a["kind"] == "outline" and any(inside_ring(mid_point(w["pts"]), a["pts"]) for w in c["ways"]):
                best, bd = c, 0.0
                break
            for w in c["ways"]:
                d = min(metres(m, p) for p in w["pts"][:: max(1, len(w["pts"]) // 60)])
                if d < bd:
                    best, bd = c, d
        if best is not None:
            best["areas"].append(a)
    for c in out:
        c["name"] = name_of(c)


def name_of(c):
    """A circuit's name: its outline's, else a known circuit's within 3 km, else its longest named way's."""
    for a in c["areas"]:
        if a["kind"] == "outline" and a["name"]:
            return a["name"]
    near = [(metres((c["lat"], c["lon"]), (k[1], k[2])), k[0]) for k in KNOWN]
    near = [k for k in near if k[0] < 3000.0]
    if near:
        return min(near)[1]
    named = sorted(((length_of(w["pts"]), w["name"]) for w in c["ways"] if w["name"]), reverse=True)
    return named[0][1] if named else ""


def mid_point(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def inside_ring(p, ring):
    """Whether (lat, lon) p is inside the ring (even-odd)."""
    y, x = p
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def steps(pts):
    """Points as 1e-5 degrees: the first whole, the rest steps from the one before."""
    out = []
    la0 = lo0 = 0
    for k, (la, lo) in enumerate(pts):
        a, b = int(round(la * 1e5)), int(round(lo * 1e5))
        if k == 0:
            out += [a, b]
        else:
            if a == la0 and b == lo0:
                continue
            out += [a - la0, b - lo0]
        la0, lo0 = a, b
    return out


def bake(circuits, release, osm_date=""):
    """The cells' files: {"ROW_COL": file}."""
    cells = {}

    def cell_file(rc):
        key = "%d_%d" % rc
        if key not in cells:
            cells[key] = {"format": FORMAT, "cell": key, "release": release, "osm": osm_date, "kinds": WAY_KINDS + AREA_KINDS,
                          "names": [""], "circuits": [], "ways": [], "areas": [], "_c": set()}
        return cells[key]

    def name_ix(f, name):
        if name not in f["names"]:
            f["names"].append(name)
        return f["names"].index(name)

    kinds = WAY_KINDS + AREA_KINDS
    for c in circuits:
        touched = set()
        for w in c["ways"]:
            here = {cell_of(p[0], p[1]) for p in w["pts"]}
            touched |= here
            for rc in here:
                f = cell_file(rc)
                f["ways"].append([str(w["id"]), kinds.index(w["kind"]), int(round(w["width"] * 10)), w["oneway"],
                                  name_ix(f, w["name"]), str(c["id"])] + steps(w["pts"]))
        for a in c["areas"]:
            here = {cell_of(p[0], p[1]) for p in a["pts"]}
            for rc in here & touched or here:
                f = cell_file(rc)
                f["areas"].append([str(a["id"]), kinds.index(a["kind"]), name_ix(f, a["name"]), str(c["id"])] + steps(a["pts"]))
        for rc in touched:
            f = cell_file(rc)
            if c["id"] not in f["_c"]:
                f["_c"].add(c["id"])
                f["circuits"].append([str(c["id"]), c["name"], c["kind"], round(c["lat"], 5), round(c["lon"], 5), int(round(c["length"]))])
    for f in cells.values():
        del f["_c"]
        f["ways"].sort(key=lambda r: r[0])
        f["areas"].sort(key=lambda r: r[0])
        f["circuits"].sort(key=lambda r: r[0])
    return cells


def table(circuits):
    """The stage 1 table: one row a circuit."""
    rows = []
    for c in circuits:
        ws = c["ways"]
        widths = [w["width"] for w in ws if w["width"] > 0 and w["kind"] != "pit"]
        rows.append({
            "id": str(c["id"]), "name": c["name"], "kind": c["kind"], "lat": round(c["lat"], 5), "lon": round(c["lon"], 5),
            "cell": "%d_%d" % cell_of(c["lat"], c["lon"]), "track_m": int(round(c["length"])),
            "ways": len(ws), "pit_lane_m": int(round(sum(length_of(w["pts"]) for w in ws if w["kind"] == "pit"))),
            "closed": any(w["ends"][0] == w["ends"][1] for w in ws) or closes(ws),
            "width_tagged": round(sum(widths) / len(widths), 1) if widths else 0,
            "oneway_tagged": sum(1 for w in ws if w["oneway"]),
            "named_ways": sorted({w["name"] for w in ws if w["name"]})[:20],
            "outline": sum(1 for a in c["areas"] if a["kind"] == "outline"),
            "gravel": sum(1 for a in c["areas"] if a["kind"] in ("gravel", "sand")),
            "grass": sum(1 for a in c["areas"] if a["kind"] == "grass"),
            "tarmac": sum(1 for a in c["areas"] if a["kind"] == "tarmac"),
            "grandstands": sum(1 for a in c["areas"] if a["kind"] == "grandstand"),
        })
    return rows


def closes(ws):
    """Whether the track ways make a loop: every end node meets another way's end."""
    track = [w for w in ws if w["kind"] != "pit"]
    if not track:
        return False
    count = {}
    for w in track:
        for ref in w["ends"]:
            count[ref] = count.get(ref, 0) + 1
    return all(v >= 2 for v in count.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pbf", nargs="+", help="extracts (.osm.pbf, .osm) or Overpass API answers (.json)")
    ap.add_argument("--more", nargs="*", default=[], help="extracts of the run-off kinds (gravel, sand, grass, parking): only near circuits")
    ap.add_argument("--out", required=True)
    ap.add_argument("--release", default="")
    ap.add_argument("--osm-date", default="")
    ap.add_argument("--list", default="")
    ap.add_argument("--box", default="49.5,-8.9,61.0,2.1", help="S,W,N,E: circuits whose middle is outside are left out")
    args = ap.parse_args(argv)
    if not args.release:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.json")) as f:
            args.release = json.load(f)["release"]
    s, w, n, e = (float(v) for v in args.box.split(","))
    over = all(p.endswith(".json") for p in args.pbf)
    ways, areas = (collect_overpass if over else collect)(args.pbf)
    circuits = [c for c in group(ways, areas) if s <= c["lat"] <= n and w <= c["lon"] <= e]
    if args.more:
        _, more = (collect_overpass if all(p.endswith(".json") for p in args.more) else collect)(args.more, boxes_of(circuits))
        more = [a for a in more if a["kind"] not in ("outline",)]
        assign(circuits, more)
    cells = bake(circuits, args.release, args.osm_date)
    os.makedirs(args.out, exist_ok=True)
    for key, f in sorted(cells.items()):
        with open(os.path.join(args.out, "c%s.circuit" % key), "w", encoding="utf-8") as fh:
            json.dump(f, fh, separators=(",", ":"), ensure_ascii=False)
    rows = table(circuits)
    if args.list:
        os.makedirs(os.path.dirname(os.path.abspath(args.list)), exist_ok=True)
        with open(args.list, "w", encoding="utf-8") as fh:
            json.dump({"format": 1, "release": args.release, "osm": args.osm_date, "circuits": rows}, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    for r in rows:
        print("%-34s %-5s %6d m  ways %3d  pit %4d m  closed %-5s  gravel %2d  stands %2d  cell %s" % (
            r["name"][:34] or "(no name)", r["kind"], r["track_m"], r["ways"], r["pit_lane_m"], r["closed"], r["gravel"],
            r["grandstands"], r["cell"]))
    print("circuits: %d (%d track, %d kart, %d dirt) in %d cells" % (len(rows), sum(r["kind"] == "track" for r in rows),
          sum(r["kind"] == "kart" for r in rows), sum(r["kind"] == "dirt" for r in rows), len(cells)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
