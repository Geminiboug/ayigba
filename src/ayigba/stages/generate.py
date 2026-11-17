"""Étape « generation » : des couches propres vers les maillages 3D.

Entrée  : work/nettoyage/*.geojson
Sorties : work/generation/<couche>.npz (triangles + couleurs), sol.geojson (partition du sol),
          buildings.geojson (bâtiments avec leur hauteur finale), scene.json (liste des couches).

Le sol est une partition exacte de la zone : terre, chaussées revêtues, chaussées non revêtues, eau.
Aucune de ces parties ne se chevauche, et leur réunion couvre toute la zone : pas de trou, pas de scintillement.
Limites de cette version : terrain plat, toits plats, pas de trottoirs, ponts rendus comme des remblais.
"""
from __future__ import annotations

import json

from shapely.geometry import Point
from shapely.ops import unary_union

from ..decor import place_decor
from ..geo import LocalFrame, read_features, write_features
from ..mesh import MeshBuilder, rng_for
from ..props import CATALOGUE, place
from .clean import _polygons

STAGE = "generation"
WATER_LEVEL = -0.3
BED_LEVEL = -1.2

SAND = (0.78, 0.69, 0.52)
LATERITE = (0.72, 0.52, 0.36)
ASPHALT = (0.23, 0.23, 0.25)
TARMAC = (0.33, 0.33, 0.35)
WATER = (0.16, 0.38, 0.47)
BED = (0.45, 0.41, 0.33)
WALLS = [(0.86, 0.80, 0.68), (0.90, 0.86, 0.78), (0.80, 0.70, 0.55), (0.93, 0.91, 0.87), (0.76, 0.74, 0.70), (0.85, 0.73, 0.66), (0.70, 0.76, 0.72)]
ROOFS = [(0.55, 0.56, 0.58), (0.47, 0.36, 0.30), (0.62, 0.62, 0.60), (0.40, 0.42, 0.45), (0.52, 0.30, 0.24)]


def _estimate_height(rng, area: float, kind: str) -> float:
    """Hauteur vraisemblable quand OSM ne la donne pas. Règle simple, à remplacer par l'analyse de quartier."""
    if kind in ("roof", "shed", "hut", "kiosk", "garage", "carport") or area < 30:
        return round(rng.uniform(2.6, 3.2), 2)
    if area < 250:
        levels = rng.choices([1, 2, 3], weights=[70, 24, 6])[0]
    elif area < 1200:
        levels = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
    else:
        levels = rng.choices([1, 2, 3], weights=[55, 30, 15])[0]
    return round(levels * 3.0 + rng.uniform(0.3, 0.9), 2)


def run(ctx) -> dict:
    src = ctx.project.work / "nettoyage"
    out = ctx.project.stage_dir(STAGE)
    frame = LocalFrame(ctx.config.bbox)
    zone = frame.zone_polygon()
    seed = ctx.config.seed

    filled = ctx.project.work / "secours"  # routes et bâtiments après l'étape de secours (réels + générés)
    roads = read_features(filled / "roads.geojson")
    buildings = read_features(filled / "buildings.geojson")
    water = unary_union([g for g, _ in read_features(src / "water.geojson")]) if (src / "water.geojson").is_file() else None
    surfaces = [g for g, _ in read_features(src / "surfaces.geojson")]

    def corridors(paved: bool):
        return [g.buffer(p["largeur"] / 2.0, cap_style="round", join_style="round") for g, p in roads
                if not p["tunnel"] and (p["revetement"] == "pave") == paved]

    # partition exacte du sol : eau, puis revêtu, puis non revêtu, puis terre
    water_part = water.intersection(zone) if water is not None and not water.is_empty else None
    remaining = zone if water_part is None else zone.difference(water_part)
    # une chaussée ne passe jamais sous un bâtiment (les abris ouverts, « roof », sont exclus)
    solid = unary_union([g for g, p in buildings if p.get("type") != "roof"]) if buildings else None
    paved_part = unary_union(corridors(True) + surfaces).intersection(remaining)
    if solid is not None:
        paved_part = paved_part.difference(solid)
    remaining = remaining.difference(paved_part)
    unpaved_part = unary_union(corridors(False)).intersection(remaining)
    if solid is not None:
        unpaved_part = unpaved_part.difference(solid)
    land_part = remaining.difference(unpaved_part)

    parts = {"eau": water_part, "revetu": paved_part, "non_revetu": unpaved_part, "terre": land_part}
    ground_features = []
    for kind in ("eau", "non_revetu", "revetu", "terre"):
        for k, p in enumerate(_polygons(parts[kind]) if parts[kind] is not None else []):
            if p.area > 0:
                ground_features.append((p, {"id": f"{kind}/{k}", "genre": kind}))
    write_features(out / "sol.geojson", ground_features, ndigits=6)  # précision fine : le contrôle de couverture en dépend

    layers: list[dict] = []

    def finish(builder: MeshBuilder, collision: bool, what: str) -> None:
        n = builder.save(out / f"{builder.name}.npz")
        layers.append({"nom": builder.name, "triangles": n, "collision": collision, "contenu": what})

    terrain = MeshBuilder("terrain")
    for p in _polygons(land_part):
        terrain.add_flat(p, 0.0, SAND)
    land_all = zone if water_part is None else zone.difference(water_part)
    for p in _polygons(land_all):
        terrain.add_walls(p, BED_LEVEL, 0.0, BED)  # berges : pas de vide entre la terre et l'eau
    finish(terrain, True, "terre nue et berges")

    chaussee = MeshBuilder("chaussees")
    for p in _polygons(paved_part):
        chaussee.add_flat(p, 0.0, ASPHALT)
    for p in _polygons(unpaved_part):
        chaussee.add_flat(p, 0.0, LATERITE)
    finish(chaussee, True, "chaussées revêtues et non revêtues, pistes d'aéroport")

    eau = MeshBuilder("eau")
    fond = MeshBuilder("fond_eau")
    for p in _polygons(water_part) if water_part is not None else []:
        eau.add_flat(p, WATER_LEVEL, WATER)
        fond.add_flat(p, BED_LEVEL, BED)
    finish(eau, False, "surface de l'eau")
    finish(fond, True, "fond de l'eau")

    road_all = unary_union([g for g in (paved_part, unpaved_part) if not g.is_empty])
    road_all = None if road_all.is_empty else road_all
    bati = MeshBuilder("batiments")
    estimated = 0
    final_buildings = []
    for geom, props in buildings:
        rng = rng_for(seed, props["id"])
        height = props.get("hauteur")
        source_h = "osm"
        if height is None:
            height = _estimate_height(rng, geom.area, props.get("type", "yes"))
            source_h = "genere"
            estimated += 1
        wall, roof = rng.choice(WALLS), rng.choice(ROOFS)
        if props.get("type") == "roof":
            # abri ouvert (auvent, préau) : une dalle en hauteur sur des poteaux, on passe dessous
            height = max(height, 3.2)
            for part in _polygons(geom):
                bati.add_prism(part, height - 0.25, height, roof, roof)
                bati.add_flat_down(part, height - 0.25, roof)
                corners = list(part.minimum_rotated_rectangle.buffer(-0.4).exterior.coords)[:4] if part.area > 4 else []
                for cx, cy in corners:
                    post = Point(cx, cy).buffer(0.12, quad_segs=1)
                    if part.contains(Point(cx, cy)) and (road_all is None or road_all.distance(Point(cx, cy)) > 0.6):
                        bati.add_walls(post, 0.0, height - 0.25, (0.45, 0.45, 0.47))
            final_buildings.append((geom, {**props, "hauteur": height, "hauteur_source": source_h}))
            continue
        for part in _polygons(geom):
            bati.add_prism(part, 0.0, height, wall, roof)
        final_buildings.append((geom, {**props, "hauteur": height, "hauteur_source": source_h}))
    finish(bati, True, "volumes des bâtiments, toits plats")
    write_features(out / "buildings.geojson", final_buildings)
    if estimated:
        ctx.journal.record("genere", "batiments", f"hauteur estimée pour {estimated} bâtiment(s) sans hauteur dans OSM (règle par surface, tirage lié à la graine)")

    # décors : points placés par règles, puis maillages légers ; la liste est aussi exportée telle quelle
    items = []
    if bool(ctx.config.option("decors", "actif", True)):
        road_surface = unary_union([g for g in (paved_part, unpaved_part) if not g.is_empty])
        items = place_decor(zone, roads, final_buildings, water_part, road_surface if not road_surface.is_empty else None,
                            read_features(src / "landuse.geojson"), read_features(src / "pois.geojson"), seed)
    decors = MeshBuilder("decors")
    for k, item in enumerate(items):
        pieces = place(CATALOGUE[item["type"]](rng_for(seed, f"decor:{item['type']}:{item['x']}:{item['y']}")), item["x"], item["y"], item["angle"])
        for tris, color in pieces:
            decors._add(tris, color)
    finish(decors, False, "décors légers : arbres, poteaux, lampadaires, étals, panneaux")
    write_features(out / "decors.geojson", [(Point(i["x"], i["y"]), {"id": f"decor/{k}", "type": i["type"], "angle": i["angle"], "source": i["source"]})
                                            for k, i in enumerate(items)])
    if items:
        ctx.journal.record("genere", "decors", f"{len(items)} décor(s) placés par règles selon le type de rue et de terrain",
                           par_type={t: sum(1 for i in items if i["type"] == t) for t in sorted({i["type"] for i in items})})

    (out / "scene.json").write_text(json.dumps({"couches": layers, "niveau_eau": WATER_LEVEL, "niveau_fond": BED_LEVEL}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return {
        "triangles": sum(layer["triangles"] for layer in layers),
        "couches": {layer["nom"]: layer["triangles"] for layer in layers},
        "batiments": len(buildings), "hauteurs_estimees": estimated, "decors": len(items),
    }
