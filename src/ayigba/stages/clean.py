"""Étape « nettoyage » : des données brutes OpenStreetMap vers des couches propres, dans le repère local (mètres).

Entrée  : cache/osm_overpass.json (étape collecte).
Sorties : work/nettoyage/{roads,buildings,water,surfaces,landuse,pois,barriers}.geojson

Principe : OpenStreetMap n'est pas la vérité absolue. Chaque correction, suppression ou anomalie est écrite
dans le journal des décisions. Le résultat est déterministe : tout est traité dans l'ordre des identifiants.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict

from shapely import STRtree, make_valid
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, polygonize, unary_union

from ..geo import LocalFrame, write_features

STAGE = "nettoyage"

# Largeur de chaussée par défaut (mètres) quand OSM ne la donne pas.
ROAD_WIDTH = {
    "motorway": 10.5, "trunk": 10.0, "primary": 9.0, "secondary": 8.0, "tertiary": 7.0,
    "unclassified": 6.0, "residential": 6.0, "living_street": 5.0, "service": 4.0, "track": 3.5,
    "pedestrian": 4.0, "footway": 2.0, "path": 1.5, "steps": 2.0, "cycleway": 2.0,
}
MIN_ROAD_WIDTH = {"motorway": 7.0, "trunk": 7.0, "primary": 7.0, "secondary": 6.0, "tertiary": 5.0}  # autres : 3,5 m
PEDESTRIAN = {"pedestrian", "footway", "path", "steps", "cycleway"}
PAVED_BY_DEFAULT = {"motorway", "trunk", "primary", "secondary", "tertiary"}
PAVED = {"asphalt", "paved", "concrete", "paving_stones", "sett", "concrete:plates", "concrete:lanes", "cobblestone", "bricks"}
UNPAVED = {"unpaved", "sand", "dirt", "earth", "ground", "gravel", "fine_gravel", "compacted", "mud", "grass"}
WATERWAY_WIDTH = {"river": 8.0, "canal": 5.0}
AERO_WIDTH = {"runway": 45.0, "taxiway": 23.0}
LANDUSE_NATURAL = {"beach", "sand", "scrub", "wood", "wetland", "grassland"}

SNAP = 2.0          # un bout de route à moins de 2 m d'une autre route est recollé
STUB = 3.0          # une impasse de moins de 3 m est un parasite
BRIDGE_GAP = 12.0   # un réseau isolé à moins de 12 m d'un autre est relié
MIN_BUILDING = 4.0  # m2
MAX_HEIGHT = 100.0  # au-delà : aberration pour une ville du Bénin


# ---------------------------------------------------------------- lecture

def _num(text) -> float | None:
    """« 12 », « 12.5 m », « 3,5 » -> nombre ; None si illisible."""
    if text is None:
        return None
    t = str(text).strip().lower().replace(",", ".")
    for suffix in ("meters", "metres", "meter", "metre", "m"):
        if t.endswith(suffix):
            t = t[: -len(suffix)].strip()
            break
    try:
        v = float(t)
    except ValueError:
        return None
    return v if math.isfinite(v) and v > 0 else None


def _coords(frame: LocalFrame, geometry) -> list[tuple[float, float]]:
    pts = [g for g in (geometry or []) if g and "lat" in g]
    if not pts:
        return []
    xs, ys = frame.to_local([p["lon"] for p in pts], [p["lat"] for p in pts])
    out: list[tuple[float, float]] = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        c = (round(x, 3), round(y, 3))
        if not out or out[-1] != c:
            out.append(c)
    return out


def _polygons(geom) -> list[Polygon]:
    """Toutes les parties polygonales valides d'une géométrie quelconque."""
    if geom is None or geom.is_empty:
        return []
    if not geom.is_valid:
        geom = make_valid(geom)
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in _polygons(g)]
    return []


def _lines(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length > 0 else []
    if hasattr(geom, "geoms"):
        return [ln for g in geom.geoms for ln in _lines(g)]
    return []


def _relation_polygons(frame: LocalFrame, rel: dict) -> list[Polygon]:
    outers, inners = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way":
            continue
        c = _coords(frame, m.get("geometry"))
        if len(c) >= 2:
            (inners if m.get("role") == "inner" else outers).append(LineString(c))
    if not outers:
        return []
    shell = unary_union(list(polygonize(unary_union(outers))))
    if inners:
        holes = list(polygonize(unary_union(inners)))
        if holes:
            shell = shell.difference(unary_union(holes))
    return _polygons(shell)


def _key(c) -> tuple[float, float]:
    return (round(c[0], 2), round(c[1], 2))


def _level(tags: dict) -> tuple:
    """Deux routes ne se rencontrent que si elles sont au même niveau (pont, tunnel, couche)."""
    return (tags.get("layer", "0"), tags.get("bridge", "no") != "no", tags.get("tunnel", "no") != "no")


def _insert_vertex(line: LineString, pt: Point, tol: float = 0.02):
    """Ajoute un sommet sur la ligne à l'endroit le plus proche de pt. Renvoie (ligne, coordonnée du sommet)."""
    coords = [c[:2] for c in line.coords]
    target = (pt.x, pt.y)
    d = line.project(pt)
    acc = 0.0
    for k in range(len(coords) - 1):
        seg = math.dist(coords[k], coords[k + 1])
        if acc + seg >= d - 1e-9:
            if math.dist(coords[k], target) < tol:
                return line, coords[k]
            if math.dist(coords[k + 1], target) < tol:
                return line, coords[k + 1]
            q = line.interpolate(d)
            v = (round(q.x, 3), round(q.y, 3))
            coords.insert(k + 1, v)
            return LineString(coords), v
        acc += seg
    return line, coords[-1]


class _Union:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


# ---------------------------------------------------------------- bâtiments

def _building_height(tags: dict, oid: str, journal) -> float | None:
    h = _num(tags.get("height"))
    if h is None:
        levels = _num(tags.get("building:levels"))
        if levels is not None:
            h = levels * 3.0 + 0.5
    if h is not None and h > MAX_HEIGHT:
        journal.record("signale", oid, f"hauteur aberrante ({h:.0f} m), ignorée : elle sera estimée", hauteur=h)
        return None
    return round(h, 2) if h is not None else None


def _clean_buildings(raw: list[dict], zone: Polygon, journal) -> list[dict]:
    items = []
    for b in sorted(raw, key=lambda r: r["id"]):
        parts = [p for p in b["polys"] if p.area >= MIN_BUILDING]
        if not parts:
            journal.record("supprime", b["id"], "bâtiment de moins de 4 m2 ou géométrie vide")
            continue
        poly = max(parts, key=lambda p: p.area)
        if len(b["polys"]) > 1 or not b["valid"]:
            journal.record("corrige", b["id"], "géométrie invalide réparée, plus grande partie gardée")
        if not zone.contains(poly):
            if poly.intersects(zone):
                journal.record("supprime", b["id"], "bâtiment à cheval sur la limite de la zone")
            continue
        items.append({"id": b["id"], "poly": poly, "tags": b["tags"]})

    # doublons et chevauchements : le plus petit cède
    removed: set[int] = set()
    tree = STRtree([it["poly"] for it in items])
    for i, it in enumerate(items):
        if i in removed:
            continue
        for j in sorted(tree.query(it["poly"]).tolist()):
            if j <= i or j in removed or i in removed:
                continue
            a, b = items[i], items[j]
            inter = a["poly"].intersection(b["poly"]).area
            if inter < 0.5:
                continue
            small, big, s_idx = (a, b, i) if a["poly"].area <= b["poly"].area else (b, a, j)
            if inter / small["poly"].area > 0.8:
                removed.add(s_idx)
                journal.record("supprime", small["id"], f"doublon de {big['id']} (plus de 80 % en commun)")
                continue
            rest = [p for p in _polygons(small["poly"].difference(big["poly"].buffer(0.05))) if p.area >= MIN_BUILDING]
            if not rest or max(p.area for p in rest) < 0.5 * small["poly"].area:
                removed.add(s_idx)
                journal.record("supprime", small["id"], f"chevauche {big['id']} sur plus de la moitié")
            else:
                small["poly"] = max(rest, key=lambda p: p.area)
                journal.record("corrige", small["id"], f"chevauchement avec {big['id']} retiré", surface_retiree=round(inter, 1))
    return [it for k, it in enumerate(items) if k not in removed]


# ---------------------------------------------------------------- routes

def _road_props(tags: dict, revetues_par_defaut=None) -> dict:
    cls = tags["highway"]
    base = cls[:-5] if cls.endswith("_link") else cls
    width = _num(tags.get("width"))
    lanes = _num(tags.get("lanes"))
    if width is None and lanes is not None and base not in PEDESTRIAN:
        width = lanes * 3.25
    width_guessed = width is None
    if width is None:
        width = ROAD_WIDTH[base] - (2.0 if cls.endswith("_link") else 0.0)
    width = min(max(width, 1.0), 40.0)
    surface = tags.get("surface")
    if surface in PAVED:
        paved, guessed = True, False
    elif surface in UNPAVED:
        paved, guessed = False, False
    else:
        paved, guessed = base in (PAVED_BY_DEFAULT if revetues_par_defaut is None else revetues_par_defaut), True
    oneway = tags.get("oneway") in ("yes", "1", "true", "-1") or tags.get("junction") == "roundabout"
    return {
        "classe": base, "nom": tags.get("name", ""), "largeur": round(width, 2), "largeur_supposee": width_guessed,
        "voies": int(lanes) if lanes else (1 if base in PEDESTRIAN or width < 5.5 else 2),
        "sens_unique": bool(oneway), "sens_inverse": tags.get("oneway") == "-1",
        "revetement": "pave" if paved else "non_pave", "revetement_suppose": guessed,
        "pieton": base in PEDESTRIAN, "pont": tags.get("bridge", "no") != "no", "tunnel": tags.get("tunnel", "no") != "no",
        "couvert": tags.get("covered", "no") != "no", "rond_point": tags.get("junction") == "roundabout", "source": "osm",
    }


def _clean_roads(raw: list[dict], zone: Polygon, buildings: list[dict], journal, revetues_par_defaut=None) -> list[dict]:
    roads: list[dict] = []
    seen: dict[tuple, str] = {}
    for r in sorted(raw, key=lambda r: r["id"]):
        parts = _lines(LineString(r["coords"]).intersection(zone))
        for k, ln in enumerate(parts):
            sig = tuple(sorted((_key(ln.coords[0]), _key(ln.coords[-1])))) + (round(ln.length, 1), r["tags"]["highway"])
            if sig in seen and LineString(ln.coords).equals_exact(next(x["line"] for x in roads if x["id"] == seen[sig]), 0.05):
                journal.record("supprime", r["id"], f"route en double de {seen[sig]}")
                continue
            rid = r["id"] if len(parts) == 1 else f"{r['id']}#{k}"
            seen.setdefault(sig, rid)
            roads.append({"id": rid, "line": ln, "tags": r["tags"], "props": _road_props(r["tags"], revetues_par_defaut), "level": _level(r["tags"])})

    boundary = zone.exterior

    def vertex_counter():
        c: Counter = Counter()
        for r in roads:
            c.update({_key(v) for v in r["line"].coords})
        return c

    # 1. recoller les bouts de route presque connectés
    count = vertex_counter()
    tree = STRtree([r["line"] for r in roads])
    forced: list[tuple[int, int]] = []
    for i, r in enumerate(roads):
        if r["line"].is_ring:
            continue
        for end in (0, -1):
            coords = list(r["line"].coords)
            pt = Point(coords[end])
            if count[_key(coords[end])] > 1 or boundary.distance(pt) < 0.5:
                continue
            best = None
            for j in sorted(tree.query(pt.buffer(SNAP)).tolist()):
                if j == i or roads[j]["level"] != r["level"]:
                    continue
                d = roads[j]["line"].distance(pt)
                if d <= SNAP and (best is None or d < best[0]):
                    best = (d, j)
            if best is None:
                continue
            d, j = best
            roads[j]["line"], v = _insert_vertex(roads[j]["line"], pt)
            if _key(v) != _key(coords[end]):
                coords = coords + [v] if end == -1 else [v] + coords
                r["line"] = LineString(coords)
            forced.append((i, j))
            journal.record("corrige", r["id"], f"bout de route recollé à {roads[j]['id']}", ecart_m=round(d, 2))

    # 2. croisements au même niveau sans nœud commun
    tree = STRtree([r["line"] for r in roads])
    for i, r in enumerate(roads):
        for j in sorted(tree.query(r["line"]).tolist()):
            if j <= i or roads[j]["level"] != r["level"]:
                continue
            inter = roads[i]["line"].intersection(roads[j]["line"])
            pts = [g for g in (inter.geoms if hasattr(inter, "geoms") else [inter]) if isinstance(g, Point)]
            for p in pts:
                ki = {_key(v) for v in roads[i]["line"].coords}
                kj = {_key(v) for v in roads[j]["line"].coords}
                if _key((p.x, p.y)) in ki and _key((p.x, p.y)) in kj:
                    continue
                roads[i]["line"], _ = _insert_vertex(roads[i]["line"], p)
                roads[j]["line"], _ = _insert_vertex(roads[j]["line"], p)
                forced.append((i, j))
                journal.record("corrige", roads[i]["id"], f"croisement avec {roads[j]['id']} sans nœud commun : carrefour créé")

    # 3. impasses parasites
    count = vertex_counter()
    kept = []
    for r in roads:
        c = list(r["line"].coords)
        free = [e for e in (0, -1) if count[_key(c[e])] == 1 and boundary.distance(Point(c[e])) >= 0.5]
        if r["line"].length < STUB and free and not r["line"].is_ring:
            journal.record("supprime", r["id"], f"impasse parasite de {r['line'].length:.1f} m")
        else:
            kept.append(r)
    index_of = {id(r): k for k, r in enumerate(kept)}
    forced = [(index_of[id(roads[a])], index_of[id(roads[b])]) for a, b in forced if id(roads[a]) in index_of and id(roads[b]) in index_of]
    roads = kept

    # 4. connexité du réseau
    def components() -> tuple[_Union, dict[int, list[int]]]:
        uf = _Union(len(roads))
        owner: dict[tuple, int] = {}
        for k, r in enumerate(roads):
            for v in r["line"].coords:
                kk = _key(v)
                if kk in owner:
                    uf.union(k, owner[kk])
                else:
                    owner[kk] = k
        for a, b in forced:
            uf.union(a, b)
        groups: dict[int, list[int]] = defaultdict(list)
        for k in range(len(roads)):
            groups[uf.find(k)].append(k)
        return uf, groups

    btree = STRtree([b["poly"] for b in buildings]) if buildings else None
    for _ in range(50):
        uf, groups = components()
        if len(groups) <= 1:
            break
        main = max(groups, key=lambda g: (sum(roads[k]["line"].length for k in groups[g]), -g))
        tree = STRtree([r["line"] for r in roads])
        linked = False
        for g in sorted(groups, key=lambda g: (sum(roads[k]["line"].length for k in groups[g]), g)):
            if g == main:
                continue
            best = None
            for k in groups[g]:
                for j in sorted(tree.query(roads[k]["line"].buffer(BRIDGE_GAP)).tolist()):
                    if uf.find(j) == g or roads[j]["level"] != roads[k]["level"]:
                        continue
                    d = roads[k]["line"].distance(roads[j]["line"])
                    if d <= BRIDGE_GAP and (best is None or d < best[0]):
                        best = (d, k, j)
            if best is None:
                continue
            d, k, j = best
            p1, p2 = nearest_points(roads[k]["line"], roads[j]["line"])
            link = LineString([(p1.x, p1.y), (p2.x, p2.y)])
            if d > 0.01 and btree is not None and any(buildings[b]["poly"].intersects(link) for b in btree.query(link).tolist()):
                continue
            roads[k]["line"], v1 = _insert_vertex(roads[k]["line"], p1)
            roads[j]["line"], v2 = _insert_vertex(roads[j]["line"], p2)
            if math.dist(v1, v2) > 0.02:
                ped = roads[k]["props"]["pieton"] or roads[j]["props"]["pieton"]
                tags = {"highway": "path" if ped else "service"}
                props = _road_props(tags, revetues_par_defaut)
                props["source"] = "genere"
                rid = f"genere/lien-{roads[k]['id'].replace('/', '-')}-{roads[j]['id'].replace('/', '-')}"
                roads.append({"id": rid, "line": LineString([v1, v2]), "tags": tags, "props": props, "level": roads[k]["level"]})
                journal.record("genere", rid, f"lien de {d:.1f} m créé pour relier un réseau isolé", entre=[roads[k]["id"], roads[j]["id"]])
            else:
                forced.append((k, j))
            linked = True
            break
        if not linked:
            break

    uf, groups = components()
    main = max(groups, key=lambda g: (sum(roads[k]["line"].length for k in groups[g]), -g)) if groups else None
    for g, members in sorted(groups.items()):
        touches = any(boundary.distance(Point(roads[k]["line"].coords[e])) < 0.5 for k in members for e in (0, -1))
        for k in members:
            roads[k]["props"]["reseau"] = "principal" if g == main else ("relie_hors_zone" if touches else "isole")
        if g != main and not touches:
            total = sum(roads[k]["line"].length for k in members)
            journal.record("signale", roads[members[0]]["id"], f"réseau isolé de {len(members)} route(s), {total:.0f} m, sans lien possible à moins de {BRIDGE_GAP:.0f} m")
    return roads


def _corridor(road: dict, extra: float = 0.0) -> Polygon:
    return road["line"].buffer(road["props"]["largeur"] / 2.0 + extra, cap_style="flat", join_style="round")


def _resolve_road_building(roads: list[dict], buildings: list[dict], journal) -> tuple[list[dict], list[dict]]:
    """Une route carrossable qui traverse un bâtiment rogne le bâtiment ; un sentier qui traverse un bâtiment est coupé."""
    if not buildings or not roads:
        return roads, buildings
    btree = STRtree([b["poly"] for b in buildings])
    dead: set[int] = set()
    out_roads: list[dict] = []
    for r in roads:
        p = r["props"]
        if r["level"][0] != "0" and not (p["tunnel"] or p["couvert"]):
            out_roads.append(r)
            continue
        corridor = _corridor(r)
        if p["tunnel"] or p["couvert"]:
            # passage couvert : cette version ne sait pas faire de plafond. S'il traverse le bâtiment de part en part,
            # on l'ouvre à ciel ouvert ; s'il finit dedans (parking, cour intérieure), on raccourcit la voie.
            hits = [k for k in sorted(btree.query(r["line"]).tolist()) if k not in dead and buildings[k]["tags"].get("building") != "roof"
                    and buildings[k]["poly"].intersects(r["line"])]
            if not hits:
                out_roads.append(r)
                continue
            line = r["line"]
            for k in hits:
                b = buildings[k]
                ends_inside = b["poly"].contains(Point(line.coords[0])) or b["poly"].contains(Point(line.coords[-1]))
                rest = [q for q in _polygons(b["poly"].difference(_corridor(r, 0.2))) if q.area >= MIN_BUILDING]
                if not ends_inside and rest and sum(q.area for q in rest) >= 0.5 * b["poly"].area:
                    b["poly"] = max(rest, key=lambda q: q.area)
                    for n, extra in enumerate(sorted((q for q in rest if q is not b["poly"]), key=lambda q: -q.area)):
                        buildings.append({"id": f"{b['id']}~{n + 1}", "poly": extra, "tags": b["tags"]})
                    journal.record("corrige", b["id"], f"passage couvert {r['id']} ouvert à ciel ouvert à travers le bâtiment")
                else:
                    parts = [ln for ln in _lines(line.difference(b["poly"].buffer(0.3))) if ln.length >= STUB]
                    line = max(parts, key=lambda ln: ln.length) if parts else None
                    journal.record("corrige", r["id"], f"voie couverte raccourcie : elle finissait dans le bâtiment {b['id']}")
                    if line is None:
                        break
            if line is not None:
                p["tunnel"] = p["couvert"] = False
                out_roads.append({**r, "line": line})
            else:
                journal.record("supprime", r["id"], "voie couverte entièrement à l'intérieur d'un bâtiment")
            continue
        hits = [k for k in sorted(btree.query(corridor).tolist()) if k not in dead and buildings[k]["tags"].get("building") != "roof"
                and buildings[k]["poly"].intersection(corridor).area > 1.0]
        if not hits:
            out_roads.append(r)
            continue
        if p["pieton"]:
            rest = _lines(r["line"].difference(unary_union([buildings[k]["poly"] for k in hits]).buffer(0.2)))
            rest = [ln for ln in rest if ln.length >= STUB]
            journal.record("corrige", r["id"], f"sentier coupé : il traversait {len(hits)} bâtiment(s)", batiments=[buildings[k]["id"] for k in hits])
            for n, ln in enumerate(rest):
                out_roads.append({**r, "id": r["id"] if len(rest) == 1 else f"{r['id']}~{n}", "line": ln, "props": dict(p)})
            continue
        if p["largeur_supposee"]:
            # largeur non mesurée : les bâtiments bornent la rue, donc on rétrécit la chaussée avant de toucher aux murs
            gap = min(r["line"].distance(buildings[k]["poly"]) for k in hits)
            narrowed = max(MIN_ROAD_WIDTH.get(p["classe"], 3.5), 2.0 * (gap - 0.3))
            if narrowed < p["largeur"]:
                journal.record("corrige", r["id"], f"chaussée rétrécie de {p['largeur']:.1f} à {narrowed:.1f} m : des bâtiments bornent la rue")
                p["largeur"] = round(narrowed, 2)
                corridor = _corridor(r)
                hits = [k for k in hits if buildings[k]["poly"].intersection(corridor).area > 1.0]
        out_roads.append(r)
        for k in hits:
            b = buildings[k]
            rest = [q for q in _polygons(b["poly"].difference(_corridor(r, 0.3))) if q.area >= MIN_BUILDING]
            if rest and max(q.area for q in rest) >= 0.6 * b["poly"].area:
                b["poly"] = max(rest, key=lambda q: q.area)
                journal.record("corrige", b["id"], f"bâtiment rogné : il débordait sur la route {r['id']}")
            else:
                dead.add(k)
                journal.record("supprime", b["id"], f"bâtiment posé sur la route {r['id']} (plus de 40 % sur la chaussée)")
    return out_roads, [b for k, b in enumerate(buildings) if k not in dead]


# ---------------------------------------------------------------- eau

def _sea_from_coastline(coast: list[LineString], zone: Polygon, journal) -> list[Polygon]:
    """OSM : la terre est à gauche du trait de côte, la mer à droite."""
    clipped = [ln for c in coast for ln in _lines(c.intersection(zone))]
    if not clipped:
        return []
    pieces = list(polygonize(unary_union([zone.exterior, *clipped])))
    segments = [(a, b) for ln in clipped for a, b in zip(ln.coords[:-1], ln.coords[1:])]
    sea = []
    for piece in pieces:
        p = piece.representative_point()
        a, b = min(segments, key=lambda s: LineString(s).distance(p))
        if (b[0] - a[0]) * (p.y - a[1]) - (b[1] - a[1]) * (p.x - a[0]) < 0:
            sea.append(piece)
    if sea:
        journal.record("info", "mer", f"mer déduite du trait de côte : {sum(s.area for s in sea) / 1e4:.1f} ha dans la zone")
    return sea


# ---------------------------------------------------------------- étape

def run(ctx) -> dict:
    journal = ctx.journal
    src = ctx.project.cache / "osm_overpass.json"
    if not src.is_file():
        raise RuntimeError("Données OpenStreetMap absentes : lance d'abord l'étape « collecte ».")
    elements = json.loads(src.read_text(encoding="utf-8")).get("elements", [])
    frame = LocalFrame(ctx.config.bbox)
    zone = frame.zone_polygon()

    raw_roads, raw_buildings, water, coast, surfaces, landuse, pois, barriers = [], [], [], [], [], [], [], []
    skipped: Counter = Counter()

    for el in sorted(elements, key=lambda e: (e.get("type", ""), e.get("id", 0))):
        tags = el.get("tags") or {}
        oid = f"{el.get('type')}/{el.get('id')}"
        if el.get("type") == "node":
            x, y = frame.to_local(el["lon"], el["lat"])
            pt = Point(round(float(x), 3), round(float(y), 3))
            if not zone.contains(pt):
                continue
            if tags.get("natural") == "tree":
                pois.append((pt, {"id": oid, "genre": "arbre", "type": "tree", "nom": "", "source": "osm"}))
            else:
                for k in ("amenity", "shop", "tourism", "man_made", "power", "highway"):
                    if k in tags:
                        pois.append((pt, {"id": oid, "genre": k, "type": tags[k], "nom": tags.get("name", ""), "source": "osm"}))
                        break
            continue
        if el.get("type") == "relation":
            polys = _relation_polygons(frame, el)
            if not polys:
                continue
            if tags.get("building", "no") != "no":
                raw_buildings.append({"id": oid, "polys": polys, "valid": True, "tags": tags})
            elif tags.get("natural") == "water":
                water.extend((p, oid, "eau") for p in polys)
            elif "landuse" in tags:
                landuse.extend((p, oid, tags["landuse"]) for p in polys)
            continue
        c = _coords(frame, el.get("geometry"))
        if len(c) < 2:
            continue
        closed = len(c) >= 4 and c[0] == c[-1]
        hw = tags.get("highway")
        if hw and tags.get("area") != "yes":
            base = hw[:-5] if hw.endswith("_link") else hw
            if base in ROAD_WIDTH:
                raw_roads.append({"id": oid, "coords": c, "tags": tags})
            else:
                skipped[f"highway={hw}"] += 1
            continue
        if tags.get("building", "no") != "no" and closed:
            poly = Polygon(c)
            raw_buildings.append({"id": oid, "polys": _polygons(poly), "valid": poly.is_valid, "tags": tags})
            if tags.get("amenity") or tags.get("shop"):
                k = "amenity" if tags.get("amenity") else "shop"
                rp = poly.representative_point() if poly.is_valid else Point(c[0])
                if zone.contains(rp):
                    pois.append((Point(round(rp.x, 3), round(rp.y, 3)), {"id": oid, "genre": k, "type": tags[k], "nom": tags.get("name", ""), "source": "osm"}))
            continue
        if tags.get("natural") == "coastline":
            coast.append(LineString(c))
        elif closed and (tags.get("natural") == "water" or tags.get("waterway") in ("riverbank", "dock") or tags.get("landuse") in ("reservoir", "basin")):
            water.extend((p, oid, "eau") for p in _polygons(Polygon(c)))
        elif tags.get("waterway") in WATERWAY_WIDTH:
            w = _num(tags.get("width")) or WATERWAY_WIDTH[tags["waterway"]]
            water.extend((p, oid, tags["waterway"]) for p in _polygons(LineString(c).buffer(w / 2.0)))
        elif tags.get("waterway"):
            skipped[f"waterway={tags['waterway']}"] += 1
        elif tags.get("aeroway") in AERO_WIDTH:
            w = _num(tags.get("width")) or AERO_WIDTH[tags["aeroway"]]
            surfaces.extend((p, oid, tags["aeroway"]) for p in _polygons(LineString(c).buffer(w / 2.0, cap_style="flat")))
        elif tags.get("aeroway") == "apron" and closed:
            surfaces.extend((p, oid, "apron") for p in _polygons(Polygon(c)))
        elif closed and tags.get("aeroway") in ("aerodrome", "heliport"):
            landuse.extend((p, oid, "aerodrome") for p in _polygons(Polygon(c)))
        elif closed and ("landuse" in tags or "leisure" in tags or tags.get("natural") in LANDUSE_NATURAL):
            kind = tags.get("landuse") or tags.get("leisure") or tags.get("natural")
            landuse.extend((p, oid, kind) for p in _polygons(Polygon(c)))
        elif tags.get("barrier") in ("wall", "fence", "hedge", "retaining_wall"):
            barriers.append((LineString(c), oid, tags["barrier"]))
        elif closed and tags.get("amenity"):
            poly = Polygon(c)
            rp = poly.representative_point() if poly.is_valid else Point(c[0])
            if zone.contains(rp):
                pois.append((Point(round(rp.x, 3), round(rp.y, 3)), {"id": oid, "genre": "amenity", "type": tags["amenity"], "nom": tags.get("name", ""), "source": "osm"}))

    for what, n in sorted(skipped.items()):
        journal.record("info", what, f"{n} élément(s) de ce type ignoré(s) dans cette version")

    buildings = _clean_buildings(raw_buildings, zone, journal)
    from ..style import charger as _charger_style
    roads = _clean_roads(raw_roads, zone, buildings, journal, _charger_style(ctx.config).revetues_par_defaut)
    roads, buildings = _resolve_road_building(roads, buildings, journal)

    # eau : polygones découpés à la zone, mer déduite de la côte, routes traitées comme des remblais
    water_polys = [(q, oid, kind) for p, oid, kind in water for q in _polygons(p.intersection(zone))]
    water_polys += [(s, "mer", "mer") for s in _sea_from_coastline(coast, zone, journal)]
    if water_polys:
        wtree = STRtree([w[0] for w in water_polys])
        cut = defaultdict(list)
        for r in roads:
            if r["props"]["tunnel"]:
                continue
            for k in wtree.query(r["line"]).tolist():
                inside = r["line"].intersection(water_polys[k][0]).length
                if inside > 5.0:
                    cut[k].append(_corridor(r, 1.0))
                    why = "pont rendu comme un remblai dans cette version" if r["props"]["pont"] else "route dans l'eau sans pont : remblai supposé"
                    journal.record("signale" if r["props"]["pont"] else "corrige", r["id"], f"{why} ({inside:.0f} m dans {water_polys[k][1]})")
        fixed = []
        for k, (p, oid, kind) in enumerate(water_polys):
            if cut.get(k):
                fixed.extend((q, oid, kind) for q in _polygons(p.difference(unary_union(cut[k]))) if q.area >= 1.0)
            else:
                fixed.append((p, oid, kind))
        water_polys = fixed
        wtree = STRtree([w[0] for w in water_polys])
        for b in buildings:
            wet = sum(b["poly"].intersection(water_polys[k][0]).area for k in wtree.query(b["poly"]).tolist())
            if wet > 0.5 * b["poly"].area:
                journal.record("signale", b["id"], "bâtiment à plus de 50 % dans l'eau (pilotis ou erreur de données)")
    water_union = _polygons(unary_union([w[0] for w in water_polys])) if water_polys else []

    out = ctx.project.stage_dir(STAGE)
    extra = {"repere": {"epsg": frame.epsg, "lon0": frame.lon0, "lat0": frame.lat0, "unite": "metre", "axes": "x est, y nord"}}
    roads.sort(key=lambda r: r["id"])
    buildings.sort(key=lambda b: b["id"])
    write_features(out / "roads.geojson", [(r["line"], {"id": r["id"], **r["props"]}) for r in roads], extra=extra)
    write_features(out / "buildings.geojson", [(b["poly"], {
        "id": b["id"], "hauteur": _building_height(b["tags"], b["id"], journal), "type": b["tags"].get("building", "yes"),
        "nom": b["tags"].get("name", ""), "toit": b["tags"].get("roof:shape", ""), "source": "osm"}) for b in buildings], extra=extra)
    write_features(out / "water.geojson", [(p, {"id": f"eau/{k}", "source": "osm"}) for k, p in enumerate(water_union)], extra=extra)
    surf = [(q, oid, kind) for p, oid, kind in surfaces for q in _polygons(p.intersection(zone))]
    write_features(out / "surfaces.geojson", [(p, {"id": oid, "genre": kind, "source": "osm"}) for p, oid, kind in surf], extra=extra)
    land = [(q, oid, kind) for p, oid, kind in landuse for q in _polygons(p.intersection(zone))]
    write_features(out / "landuse.geojson", [(p, {"id": oid, "genre": kind, "source": "osm"}) for p, oid, kind in land], extra=extra)
    pois.sort(key=lambda t: t[1]["id"])
    write_features(out / "pois.geojson", pois, extra=extra)
    bars = [(ln, oid, kind) for g, oid, kind in barriers for ln in _lines(g.intersection(zone))]
    write_features(out / "barriers.geojson", [(g, {"id": oid, "genre": kind, "source": "osm"}) for g, oid, kind in bars], extra=extra)

    networks = Counter(r["props"].get("reseau", "") for r in roads)
    return {
        "routes": len(roads), "routes_km": round(sum(r["line"].length for r in roads) / 1000.0, 2),
        "routes_isolees": networks.get("isole", 0), "batiments": len(buildings), "eau_ha": round(sum(p.area for p in water_union) / 1e4, 2),
        "surfaces": len(surf), "occupation_sol": len(land), "points_interet": len(pois), "barrieres": len(bars),
    }
