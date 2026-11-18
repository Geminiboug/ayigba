"""Étape « generation » : des couches propres vers les maillages 3D.

Entrée  : work/nettoyage/*.geojson
Sorties : work/generation/<couche>.npz (triangles + couleurs), sol.geojson (partition du sol),
          buildings.geojson (bâtiments avec leur hauteur finale), scene.json (liste des couches).

Le sol est une partition exacte de la zone : terre, chaussées revêtues, chaussées non revêtues, trottoirs, eau.
Il est maillé d'un seul tenant (ayigba.terrain) et drapé sur le relief : aucune fissure entre deux parties, aucun trou.
Les bâtiments reposent sur le point le plus bas de leur emprise ; les décors sont posés à l'altitude du sol.
Limites de cette version : relief de 30 m de résolution (modèle de surface, lissé), toits plats, ponts rendus comme des remblais.
"""
from __future__ import annotations

import json

import numpy as np
from shapely.geometry import Point
from shapely.ops import unary_union

from ..decor import place_decor
from ..geo import LocalFrame, read_features, write_features
from ..mesh import MeshBuilder, rng_for
from ..props import CATALOGUE, place
from ..terrain import BED_DEPTH, build_ground, shore_walls
from .clean import _polygons
from .. import batiments25d, carrefours
from .relief import altitudes, batiments, vers_donnees

STAGE = "generation"

SIDEWALK_CLASSES = {"trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street"}
SIDEWALK = (0.63, 0.62, 0.59)
SAND = (0.78, 0.69, 0.52)
LATERITE = (0.72, 0.52, 0.36)
PAINT = (0.92, 0.92, 0.89)
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
    paved_raw = unary_union(corridors(True) + surfaces)
    # carrefours : coins arrondis près des croisements (congés), puis passages piétons peints sur les grandes rues
    junctions = carrefours.noeuds(roads) if bool(ctx.config.option("carrefours", "actif", True)) else []
    fillet = carrefours.arrondir(unary_union(corridors(True)), junctions, float(ctx.config.option("carrefours", "arrondi_m", 4.0))) if junctions else None
    if fillet is not None:
        paved_raw = paved_raw.union(fillet)
    paved_part = paved_raw.intersection(remaining)
    if solid is not None:
        paved_part = paved_part.difference(solid)
    paint_part = None
    if junctions and bool(ctx.config.option("carrefours", "passages", True)):
        paint_part = carrefours.passages(junctions, roads, paved_part)
        if paint_part is not None:
            paved_part = paved_part.difference(paint_part)
    remaining = remaining.difference(paved_part if paint_part is None else paved_part.union(paint_part))  # la peinture reste de la chaussée
    unpaved_part = unary_union(corridors(False)).intersection(remaining)
    if solid is not None:
        unpaved_part = unpaved_part.difference(solid)
    land_part = remaining.difference(unpaved_part)

    # trottoirs : une bande le long des rues revêtues, prise sur la terre (jamais sur une chaussée, un bâtiment ou l'eau)
    walk_part = None
    if bool(ctx.config.option("trottoirs", "actif", True)):
        width = float(ctx.config.option("trottoirs", "largeur_m", 1.6))
        bands = [g.buffer(p["largeur"] / 2.0 + width, cap_style="round") for g, p in roads
                 if p["classe"] in SIDEWALK_CLASSES and p["revetement"] == "pave" and not p["tunnel"] and not p["pieton"]]
        if bands:
            walk_part = unary_union(bands).intersection(land_part)
            if solid is not None:
                walk_part = walk_part.difference(solid.buffer(0.05))
            walk_part = unary_union([q for q in _polygons(walk_part) if q.area >= 2.0])
            if walk_part.is_empty:
                walk_part = None
            else:
                land_part = land_part.difference(walk_part)

    parts = {"eau": water_part, "revetu": paved_part, "marquage": paint_part, "non_revetu": unpaved_part, "trottoir": walk_part, "terre": land_part}
    ground_features = []
    for kind in ("eau", "non_revetu", "revetu", "marquage", "trottoir", "terre"):
        for k, p in enumerate(_polygons(parts[kind]) if parts[kind] is not None else []):
            if p.area > 0:
                ground_features.append((p, {"id": f"{kind}/{k}", "genre": kind}))
    write_features(out / "sol.geojson", ground_features, ndigits=6)  # précision fine : le contrôle de couverture en dépend

    layers: list[dict] = []

    def finish(builder: MeshBuilder, collision: bool, what: str) -> None:
        n = builder.save(out / f"{builder.name}.npz")
        layers.append({"nom": builder.name, "triangles": n, "collision": collision, "contenu": what})

    # sol : une seule triangulation conforme, drapée sur le relief (voir ayigba.terrain)
    alt = altitudes(ctx, frame)
    relief = alt.stats()
    ground = build_ground(zone, parts, alt.hauteur, max_area=float(ctx.config.option("terrain", "aire_max_m2", 400.0)))

    terrain = MeshBuilder("terrain")
    terrain._add(ground.triangles_of(["terre"]), SAND)
    finish(terrain, True, "terre nue, drapée sur le relief")

    berges = MeshBuilder("berges")
    berges._add(shore_walls(ground), BED)  # pas de vide entre la terre et l'eau
    finish(berges, True, "berges verticales entre le sol et le fond de l'eau")

    chaussee = MeshBuilder("chaussees")
    chaussee._add(ground.triangles_of(["revetu"]), ASPHALT)
    chaussee._add(ground.triangles_of(["marquage"]), PAINT)
    chaussee._add(ground.triangles_of(["non_revetu"]), LATERITE)
    finish(chaussee, True, "chaussées revêtues et non revêtues, pistes d'aéroport, passages piétons peints")
    if junctions:
        n_bars = len(getattr(paint_part, "geoms", [paint_part])) if paint_part is not None else 0
        ctx.journal.record("genere", "carrefours", f"{len(junctions)} carrefour(s) détecté(s) ; coins arrondis ; {n_bars} bande(s) de passage piéton peintes à l'entrée des grandes rues "
                           "(règle générale de style : la présence réelle des passages n'est pas dans les données)")

    # Trottoirs à plat par rapport à la chaussée (pas de bordure). Un essai de bordure surélevée en pente a été retiré le
    # 17/11/2026 : des faces presque verticales bloquaient les bots piétons. Une bordure ne reviendra que si chaque face
    # est garantie franchissable.
    trottoirs = MeshBuilder("trottoirs")
    trottoirs._add(ground.triangles_of(["trottoir"]), SIDEWALK)
    finish(trottoirs, True, "trottoirs au niveau de la chaussée, sans bordure")

    eau = MeshBuilder("eau")
    fond = MeshBuilder("fond_eau")
    eau._add(ground.triangles_of(["eau"], dz=0.0), WATER)
    fond._add(ground.triangles_of(["eau"], dz=-BED_DEPTH), BED)
    finish(eau, False, "surface de l'eau")
    finish(fond, True, "fond de l'eau")

    road_all = unary_union([g for g in (paved_part, unpaved_part) if not g.is_empty])
    road_all = None if road_all.is_empty else road_all
    bat25 = batiments(ctx)
    mesure = batiments25d.Hauteurs(bat25) if bat25 is not None else None
    to_data = vers_donnees(frame, bat25["epsg"]) if bat25 is not None else None
    measured = 0
    pitched = 0
    pitched_share = float(ctx.config.option("toits", "part_deux_pentes", 0.6)) if bool(ctx.config.option("toits", "actif", True)) else 0.0
    bati = MeshBuilder("batiments")
    estimated = 0
    final_buildings = []
    for geom, props in buildings:
        rng = rng_for(seed, props["id"])
        height = props.get("hauteur")
        source_h = "osm"
        if height is None and mesure is not None:
            h = mesure.pour_emprise(to_data(geom))
            if h is not None:
                height = round(min(max(float(h), 2.4), 100.0), 2)
                source_h = "google_25d"
                measured += 1
        if height is None:
            height = _estimate_height(rng, geom.area, props.get("type", "yes"))
            source_h = "genere"
            estimated += 1
        wall, roof = rng.choice(WALLS), rng.choice(ROOFS)
        # altitude du sol sous l'emprise : le bâtiment repose sur le point le plus bas (et s'enfonce de 30 cm), son toit est
        # à la hauteur indiquée au-dessus du point le plus haut
        edge = np.concatenate([np.asarray(q.exterior.coords) for q in _polygons(geom)])
        ground_z = alt.hauteur(edge[:, 0], edge[:, 1])
        low, high = float(ground_z.min()), float(ground_z.max())
        if props.get("type") == "roof":
            # abri ouvert (auvent, préau) : une dalle en hauteur sur des poteaux, on passe dessous
            height = max(height, 3.2)
            top = high + height
            for part in _polygons(geom):
                bati.add_prism(part, top - 0.25, top, roof, roof)
                bati.add_flat_down(part, top - 0.25, roof)
                corners = list(part.minimum_rotated_rectangle.buffer(-0.4).exterior.coords)[:4] if part.area > 4 else []
                for cx, cy in corners:
                    post = Point(cx, cy).buffer(0.12, quad_segs=1)
                    if part.contains(Point(cx, cy)) and (road_all is None or road_all.distance(Point(cx, cy)) > 0.6):
                        bati.add_walls(post, float(alt.hauteur(cx, cy)) - 0.3, top - 0.25, (0.45, 0.45, 0.47))
            final_buildings.append((geom, {**props, "hauteur": height, "hauteur_source": source_h, "base": round(low - 0.3, 2), "sommet": round(top, 2)}))
            continue
        top = high + height
        # toit à deux pentes : choix de style (les données ne disent pas la forme des toits), seulement pour les petits bâtiments
        # presque rectangulaires ; tirage lié à la graine, donc reproductible
        gable = pitched_share > 0.0 and height <= 9.0 and 25.0 <= geom.area <= 500.0 and rng_for(seed, props["id"] + "/toit").random() < pitched_share
        ridge = None
        for part in _polygons(geom):
            r = bati.add_gable_prism(part, low - 0.3, top, wall, roof) if gable else None
            if r is None:
                bati.add_prism(part, low - 0.3, top, wall, roof)
            else:
                ridge = r
        if ridge is not None:
            pitched += 1
        final_buildings.append((geom, {**props, "hauteur": height, "hauteur_source": source_h, "base": round(low - 0.3, 2), "sommet": round(top, 2),
                                       **({"toit": "deux_pentes", "faitage_m": round(ridge, 2)} if ridge is not None else {})}))
    finish(bati, True, "volumes des bâtiments (toits plats ou à deux pentes), posés sur le relief")
    if pitched:
        ctx.journal.record("genere", "batiments", f"toit à deux pentes ajouté à {pitched} bâtiment(s) presque rectangulaires (choix de style tiré selon la graine, part {pitched_share:.0%}) : la forme réelle des toits n'est pas dans les données")
    write_features(out / "buildings.geojson", final_buildings)
    if measured:
        ctx.journal.record("info", "batiments", f"hauteur mesurée par Google Open Buildings 2.5D pour {measured} bâtiment(s) (médiane des pixels sous l'emprise)")
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
        item["z"] = round(float(alt.hauteur(item["x"], item["y"])), 2)
        for tris, color in pieces:
            decors._add(tris + np.array([0.0, 0.0, item["z"]]), color)
    finish(decors, False, "décors légers : arbres, poteaux, lampadaires, étals, panneaux")
    write_features(out / "decors.geojson", [(Point(i["x"], i["y"]), {"id": f"decor/{k}", "type": i["type"], "angle": i["angle"], "z": i["z"], "source": i["source"]})
                                            for k, i in enumerate(items)])
    if items:
        ctx.journal.record("genere", "decors", f"{len(items)} décor(s) placés par règles selon le type de rue et de terrain",
                           par_type={t: sum(1 for i in items if i["type"] == t) for t in sorted({i["type"] for i in items})})

    (out / "scene.json").write_text(json.dumps({"couches": layers, "niveau_eau": "propre à chaque plan d'eau (voir ayigba.terrain)", "altitudes": relief}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return {
        "triangles": sum(layer["triangles"] for layer in layers),
        "couches": {layer["nom"]: layer["triangles"] for layer in layers},
        "batiments": len(buildings), "toits_deux_pentes": pitched, "hauteurs_estimees": estimated, "hauteurs_mesurees_25d": measured, "decors": len(items), "altitudes_m": relief,
    }
