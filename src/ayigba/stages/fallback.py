"""Étape « secours » : rendre la carte cohérente là où les données manquent ou enferment le joueur.

Entrée  : work/nettoyage/*.geojson
Sorties : work/secours/roads.geojson et buildings.geojson (données réelles + éléments générés, marqués source = genere)

Trois traitements, dans cet ordre :
1. Routes isolées : reliées au réseau principal par un lien droit s'il ne traverse ni bâtiment ni eau, sinon retirées.
2. Îlots vides : un îlot entouré de routes, sans aucun bâtiment, au milieu d'îlots construits et sans usage connu
   (parc, aéroport, terrain de sport...) est très probablement un trou dans les données. Il est rempli de bâtiments
   vraisemblables, de la taille et de la densité de ses voisins.
3. Poches fermées : un espace libre qu'aucun piéton ne peut atteindre (cour entièrement entourée de murs) est comblé
   par un volume plein. Un joueur ne peut donc pas y tomber sans pouvoir en sortir.

Cette étape passe avant la génération des maillages : ainsi les éléments générés suivent exactement le même chemin
(maillages, contrôles, export) que les données réelles.
"""
from __future__ import annotations

import math
import statistics

from shapely import STRtree
from shapely.affinity import rotate
from shapely.geometry import LineString, Point, box
from shapely.ops import nearest_points, polygonize, unary_union

from ..access import analyse, polygons
from ..detection import detecter, filtrer_fragments
from .. import batiments25d, empreintes
from .relief import batiments, vers_donnees, vers_local
import shapely

from ..geo import LocalFrame, read_features, write_features
from ..mesh import rng_for

STAGE = "secours"
LINK_MAX = 60.0                # longueur maximale d'un lien créé pour une route isolée (m)
BLOCK_MIN, BLOCK_MAX = 400.0, 40000.0
NEIGHBOR_RADIUS = 400.0
NO_FILL = {  # usages du sol où un îlot vide est normal
    "aerodrome", "military", "cemetery", "recreation_ground", "grass", "forest", "farmland", "basin", "railway", "meadow",
    "park", "pitch", "stadium", "golf_course", "garden", "playground", "sports_centre", "track", "nature_reserve",
    "beach", "sand", "wetland", "wood", "scrub", "grassland", "construction", "landfill", "quarry", "orchard", "greenfield", "brownfield",
}


def _connect_isolated(roads: list, solids_tree, solids: list, water, journal) -> tuple[list, int, int]:
    """roads : liste [géométrie, propriétés]. Renvoie (routes, nombre de liens créés, nombre de routes retirées)."""
    def main_lines():
        return [g for g, p in roads if p.get("reseau") != "isole"]

    def promote() -> None:
        changed = True
        while changed:
            changed = False
            ok = unary_union(main_lines())
            for item in roads:
                if item[1].get("reseau") == "isole" and item[0].distance(ok) < 0.02:
                    item[1]["reseau"] = "principal"
                    changed = True

    links = 0
    for item in sorted([r for r in roads if r[1].get("reseau") == "isole"], key=lambda r: r[1]["id"]):
        geom, props = item
        if props.get("reseau") != "isole":
            continue  # reliée entre-temps par une voisine
        target = unary_union(main_lines())
        p1, p2 = nearest_points(geom, target)
        d = p1.distance(p2)
        link = LineString([(p1.x, p1.y), (p2.x, p2.y)])
        blocked = d > LINK_MAX or (water is not None and link.intersects(water)) or \
            (solids_tree is not None and any(solids[k].intersects(link) for k in solids_tree.query(link).tolist()))
        if blocked:
            continue
        if d > 0.05:
            rid = f"genere/acces-{props['id'].replace('/', '-')}"
            roads.append([link, {**props, "id": rid, "nom": "", "classe": "path" if props["pieton"] else "service",
                                 "largeur": min(props["largeur"], 4.0), "largeur_supposee": True, "sens_unique": False, "sens_inverse": False,
                                 "rond_point": False, "pont": False, "tunnel": False, "couvert": False, "reseau": "principal", "source": "genere"}])
            journal.record("genere", rid, f"lien de {d:.0f} m créé pour relier la route isolée {props['id']}")
            links += 1
        props["reseau"] = "principal"
        promote()
    removed = 0
    kept = []
    for geom, props in roads:
        if props.get("reseau") == "isole":
            journal.record("supprime", props["id"], f"route isolée de {geom.length:.0f} m sans accès possible : retirée de la carte")
            removed += 1
        else:
            kept.append([geom, props])
    return kept, links, removed


def _comme_ecrit(features: list) -> list:
    """Les bâtiments tels que write_features les écrira : recalés sur la grille du millimètre, ceux qui disparaissent sont retirés."""
    res = []
    for g, p in features:
        g2 = shapely.set_precision(g, 1e-3) if g.geom_type in ("Polygon", "MultiPolygon") else g
        if not g2.is_empty and g2.geom_type in ("Polygon", "MultiPolygon"):
            res.append((g2, p))
    return res


def _fill_blocks(zone, roads: list, buildings: list, landuse: list, surfaces: list, water, seed: int, journal, max_density: float) -> list:
    """Renvoie les bâtiments générés [(géométrie, propriétés)] pour les îlots vides."""
    lines = [g for g, p in roads if not p["tunnel"]]
    blocks = [b for b in polygonize(unary_union([zone.exterior, *lines])) if BLOCK_MIN <= b.area <= BLOCK_MAX]
    if not blocks or not buildings:
        return []
    btree = STRtree([g for g, _ in buildings])
    built = []
    for b in blocks:
        built.append(sum(buildings[k][0].intersection(b).area for k in btree.query(b).tolist()) / b.area)
    centers = [b.centroid for b in blocks]
    ctree = STRtree(centers)
    excluded = unary_union([g for g, p in landuse if p.get("genre") in NO_FILL] + [g.buffer(30.0) for g, _ in surfaces] +
                           ([water.buffer(8.0)] if water is not None else []))
    corridors = STRtree([g.buffer(p["largeur"] / 2.0 + 1.5) for g, p in roads])
    corridor_geoms = corridors.geometries
    generated = []
    for i in sorted(range(len(blocks)), key=lambda k: (round(centers[k].x, 1), round(centers[k].y, 1))):
        block = blocks[i]
        if built[i] > max_density:
            continue
        if not excluded.is_empty and block.intersection(excluded).area > 0.1 * block.area:
            continue
        near = [k for k in ctree.query(centers[i].buffer(NEIGHBOR_RADIUS)).tolist() if k != i and built[k] >= 0.12]
        if len(near) < 3:
            continue
        target = statistics.median(built[k] for k in near)
        sizes = [buildings[k][0].area for n in near for k in btree.query(blocks[n]).tolist() if blocks[n].contains(buildings[k][0].centroid)]
        if len(sizes) < 5:
            continue
        footprint = min(max(statistics.median(sizes), 40.0), 250.0)
        inner = block.difference(unary_union([corridor_geoms[k] for k in corridors.query(block).tolist()])).buffer(-0.5)
        if inner.is_empty or inner.area < footprint:
            continue
        bid = f"{round(centers[i].x)}_{round(centers[i].y)}"
        rng = rng_for(seed, "ilot:" + bid)
        rect = block.minimum_rotated_rectangle
        c = list(rect.exterior.coords)
        e1, e2 = (c[1][0] - c[0][0], c[1][1] - c[0][1]), (c[2][0] - c[1][0], c[2][1] - c[1][1])
        long_edge = e1 if math.hypot(*e1) >= math.hypot(*e2) else e2
        angle = math.degrees(math.atan2(long_edge[1], long_edge[0]))
        width = math.sqrt(footprint * 1.3)
        depth = footprint / width
        pitch_x, pitch_y = width + 2.5, depth + 2.5
        keep = min(1.0, target / (footprint / (pitch_x * pitch_y)))
        flat = rotate(inner, -angle, origin=centers[i])
        minx, miny, maxx, maxy = flat.bounds
        made = 0
        y = miny + 0.5
        while y + depth <= maxy:
            x = minx + 0.5
            while x + width <= maxx:
                w, d = width * rng.uniform(0.85, 1.1), depth * rng.uniform(0.85, 1.1)
                if rng.random() <= keep:
                    cell = rotate(box(x, y, x + w, y + d), angle, origin=centers[i])
                    if inner.contains(cell) and not any(buildings[k][0].distance(cell) < 1.0 for k in btree.query(cell.buffer(1.0)).tolist()):
                        generated.append((cell, {"id": f"genere/bat-{bid}-{made}", "hauteur": None, "type": "yes", "nom": "", "toit": "",
                                                 "source": "genere", "raison": "ilot_vide"}))
                        made += 1
                x += pitch_x
            y += pitch_y
        if made:
            journal.record("genere", f"ilot/{bid}", f"îlot vide de {block.area:.0f} m2 au milieu d'îlots construits : {made} bâtiment(s) générés "
                           f"(densité visée {target:.2f}, emprise type {footprint:.0f} m2)", batiments=made)
    return generated


def run(ctx) -> dict:
    journal = ctx.journal
    src = ctx.project.work / "nettoyage"
    out = ctx.project.stage_dir(STAGE)
    frame = LocalFrame(ctx.config.bbox)
    zone = frame.zone_polygon()
    active = bool(ctx.config.option("secours", "actif", True))

    roads = [[g, p] for g, p in read_features(src / "roads.geojson")]
    buildings = read_features(src / "buildings.geojson")
    water_list = [g for g, _ in read_features(src / "water.geojson")]
    water = unary_union(water_list) if water_list else None
    landuse = read_features(src / "landuse.geojson")
    surfaces = read_features(src / "surfaces.geojson")
    extra = {"repere": {"epsg": frame.epsg, "lon0": frame.lon0, "lat0": frame.lat0, "unite": "metre", "axes": "x est, y nord"}}

    links = removed = filled = courtyards = fragments = 0
    detected = []
    supplementaires: dict[str, int] = {}
    wet = 0
    if active:
        solids = [g for g, p in buildings if p.get("type") != "roof"]
        roads, links, removed = _connect_isolated(roads, STRtree(solids) if solids else None, solids, water, journal)

        bat = batiments(ctx)
        if bat is not None and bool(ctx.config.option("batiments25d", "detecter", True)):
            interdit = unary_union([g.buffer(p["largeur"] / 2.0 + 0.5) for g, p in roads if not p["tunnel"]] + ([water] if water is not None else []))
            found = detecter(bat, vers_local(frame, bat["epsg"]), zone, [g for g, _ in buildings], interdit)
            detected = [(g, {"id": f"g25d/{round(g.centroid.x)}_{round(g.centroid.y)}_{k}", "hauteur": None, "type": "yes", "nom": "", "toit": "",
                             "source": "google_25d"}) for k, g in enumerate(found)]
            exclure = {str(i) for i in ctx.config.option("batiments25d", "exclure", [])}
            if exclure:
                # liste écrite par « ayigba controler-detections --exclure-score », seulement à la demande de l'utilisateur
                retires = [g for g in detected if g[1]["id"] in exclure]
                detected = [g for g in detected if g[1]["id"] not in exclure]
                inconnus = len(exclure) - len(retires)
                journal.record("supprime", "batiments25d", f"{len(retires)} bâtiment(s) détecté(s) exclu(s) à la demande de l'utilisateur "
                               f"(liste « exclure » de config.toml, {len(exclure)} identifiants dont {inconnus} sans correspondance)",
                               nombre=len(retires), identifiants_sans_correspondance=inconnus)
            if detected and bool(ctx.config.option("batiments25d", "fragments_actif", True)):
                surf = float(ctx.config.option("batiments25d", "fragment_surface_m2", 20.0))
                haut = float(ctx.config.option("batiments25d", "fragment_hauteur_m", 2.4))
                voisin = float(ctx.config.option("batiments25d", "fragment_voisin_m", 3.0))
                mesure, en_donnees = batiments25d.Hauteurs(bat), vers_donnees(frame, bat["epsg"])
                cand = [(g, mesure.pour_emprise(en_donnees(g)) if g.area < surf else None) for g, _ in detected]
                gardes, ret = filtrer_fragments(cand, [g for g, _ in buildings], surf, haut, voisin)
                fragments = len(ret)
                detected = [detected[k] for k in gardes]
                journal.record("supprime", "batiments25d", f"{len(ret)} fragment(s) douteux retiré(s) parmi les détections : surface < {surf:g} m2 et "
                               f"(hauteur < {haut:g} m ou à {voisin:g} m ou moins d'un bâtiment plus grand) ; ce sont des indices, pas une vérité terrain",
                               nombre=len(ret), surface_m2=surf, hauteur_m=haut, voisin_m=voisin)
            buildings = buildings + detected
            if detected:
                journal.record("genere", "batiments25d", f"{len(detected)} bâtiment(s) absent(s) d'OpenStreetMap ajouté(s) d'après la détection Google Open Buildings 2.5D "
                               f"({sum(g.area for g, _ in detected) / 1e4:.1f} ha)", nombre=len(detected))
        else:
            detected = []

        # sources d'empreintes supplémentaires, choisies dans config.toml : [empreintes] sources = ["microsoft"]
        noms = [str(n) for n in ctx.config.option("empreintes", "sources", [])]
        if noms:
            interdit_s = unary_union([g.buffer(p["largeur"] / 2.0 + 0.5) for g, p in roads if not p["tunnel"]] + ([water] if water is not None else []))
            for nom in noms:
                source = empreintes.obtenir(nom)
                cands = source.collecter(ctx, frame, zone)
                gardes, rejets = empreintes.fusionner([g for g, _ in buildings], cands, interdit_s)
                ajoutes = [(cands[k].geom, {"id": cands[k].identifiant or f"{source.id}/{round(cands[k].geom.centroid.x)}_{round(cands[k].geom.centroid.y)}_{k}",
                                            "hauteur": cands[k].hauteur, "type": "yes", "nom": "", "toit": "", "source": source.id}) for k in gardes]
                buildings = buildings + ajoutes
                supplementaires[source.id] = len(ajoutes)
                journal.record("genere", source.id, f"{len(ajoutes)} bâtiment(s) ajouté(s) depuis la source « {source.nom} » ({len(cands)} candidats ; "
                               f"écartés : {rejets['doublon']} doublons de bâtiments déjà connus, {rejets['chaussee_ou_eau']} sur chaussée ou eau, "
                               f"{rejets['surface']} de surface hors limites, {rejets['invalide']} géométries invalides)", nombre=len(ajoutes), candidats=len(cands), rejets=rejets)

        new = _fill_blocks(zone, roads, buildings, landuse, surfaces, water, ctx.config.seed, journal,
                           float(ctx.config.option("secours", "densite_ilot_vide", 0.0)))
        filled = len(new)
        buildings = buildings + new

        # le comblement d'une poche peut en faire apparaître une autre (quartier dense) : on recommence tant qu'il progresse
        for attempt in range(8):
            avant = courtyards
            # on analyse les géométries telles qu'elles seront ÉCRITES (même recalage sur la grille du millimètre que write_features) :
            # un interstice de moins de 1 mm entre deux bâtiments n'existe pas dans le fichier, et l'étape de contrôle verrait sinon une
            # poche que cette boucle ne voit pas
            vus = _comme_ecrit(buildings)  # copie d'analyse : les bâtiments eux-mêmes ne sont pas modifiés
            solids = [g for g, p in vus if p.get("type") != "roof"]
            seeds = [g for g, p in roads if not p["pieton"] and not p["tunnel"]]
            result = analyse(zone, solids, water_list, seeds)
            wet = len(result.wet_pockets)
            if not result.pockets:
                break
            all_geoms = [g for g, _ in vus]
            all_tree = STRtree(all_geoms)
            for pocket in sorted(result.pockets, key=lambda q: (round(q.centroid.x, 1), round(q.centroid.y, 1))):
                # le volume plein ne doit mordre sur aucun bâtiment voisin (abris ouverts compris)
                around = [all_geoms[k] for k in all_tree.query(pocket).tolist()]
                core = pocket.difference(unary_union(around).buffer(0.02)) if around else pocket
                for piece in [q for q in polygons(core) if q.area >= 1.0]:
                    c = piece.centroid
                    pid = f"genere/cour-{round(c.x)}_{round(c.y)}-{courtyards}"
                    buildings.append((piece, {"id": pid, "hauteur": 3.0, "type": "yes", "nom": "", "toit": "",
                                              "source": "genere", "raison": "poche_fermee"}))
                    journal.record("genere", pid, f"espace fermé de {piece.area:.0f} m2 inaccessible à pied : comblé par un volume plein")
                    courtyards += 1
            if courtyards == avant:
                break
        for piece in (result.wet_pockets if active else []):
            c = piece.centroid
            journal.record("signale", f"ile/{round(c.x)}_{round(c.y)}", f"terrain de {piece.area:.0f} m2 bordé par l'eau, inaccessible à pied (île ou berge) : laissé tel quel")
    else:
        journal.record("info", "secours", "étape désactivée dans la configuration ([secours] actif = false)")

    roads.sort(key=lambda r: r[1]["id"])
    buildings = sorted(buildings, key=lambda b: b[1]["id"])
    write_features(out / "roads.geojson", [(g, p) for g, p in roads], extra=extra)
    write_features(out / "buildings.geojson", buildings, extra=extra)
    return {"batiments_detectes": len(detected) if active else 0, "sources_supplementaires": supplementaires, "fragments_retires": fragments, "liens_crees": links, "routes_isolees_retirees": removed, "batiments_generes": filled, "poches_comblees": courtyards,
            "terrains_bordes_eau": wet, "elements_generes": links + filled + courtyards}
