"""Étape « tests » : contrôle de la carte générée et rapport de qualité.

Contrôles de cette étape (calculs sur les formes et les maillages, sans moteur de jeu) :
1. Sol : la partition couvre toute la zone, sans trou ni chevauchement ; même contrôle sur les maillages.
2. Maillages : valeurs finies, noms de couches autorisés, tout est dans la zone.
3. Conflits : aucun bâtiment sur une chaussée, aucun bâtiment sur un autre.
4. Réseau de routes : aucune route isolée ne doit rester après l'étape de secours.
5. Accessibilité à pied (module access) : aucun espace libre fermé ne doit rester. Les terrains bordés par l'eau
   (îles, berges) sont signalés mais acceptés.

Une erreur ici est un défaut de l'outil ou une situation que le secours n'a pas su traiter.
Les bots qui marchent dans un vrai moteur sont dans verif/godot (voir docs/CHANTIER.md).
"""
from __future__ import annotations

import json

import numpy as np
import shapely
from shapely import STRtree
from shapely.ops import unary_union

from ..access import analyse
from ..geo import LocalFrame, read_features
from ..gltf import check_name
from ..mesh import load_mesh

STAGE = "tests"
GROUND_LAYERS = ("terrain", "chaussees", "trottoirs", "eau")


def run(ctx) -> dict:
    clean = ctx.project.work / "nettoyage"
    filled = ctx.project.work / "secours"
    gen = ctx.project.work / "generation"
    frame = LocalFrame(ctx.config.bbox)
    zone = frame.zone_polygon()
    errors: list[dict] = []
    warnings: list[dict] = []

    def error(kind: str, text: str, **more) -> None:
        errors.append({"genre": kind, "texte": text, **more})
        ctx.journal.record("signale", kind, "ERREUR : " + text, **more)

    def warn(kind: str, text: str, **more) -> None:
        warnings.append({"genre": kind, "texte": text, **more})

    # 1. sol
    ground = read_features(gen / "sol.geojson")
    total = sum(g.area for g, _ in ground)
    covered = unary_union([g for g, _ in ground]).area
    hole, overlap = zone.area - covered, total - covered
    if hole > 1.0:
        error("trou_sol", f"le sol ne couvre pas toute la zone : {hole:.1f} m2 manquent", surface_m2=round(hole, 1))
    if overlap > 1.0:
        error("chevauchement_sol", f"des parties du sol se chevauchent sur {overlap:.1f} m2", surface_m2=round(overlap, 1))

    # 2. maillages
    scene = json.loads((gen / "scene.json").read_text(encoding="utf-8"))
    minx, miny, maxx, maxy = zone.bounds
    triangles = 0
    ground_area = 0.0
    for layer in scene["couches"]:
        name = layer["nom"]
        try:
            check_name(name)
        except ValueError as exc:
            error("nom_couche", str(exc))
        tris, _ = load_mesh(gen / f"{name}.npz")
        triangles += len(tris)
        if len(tris) == 0:
            continue
        if not np.isfinite(tris).all():
            error("maillage", f"couche {name} : coordonnées non finies")
            continue
        area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
        if name in GROUND_LAYERS:
            # surface vue du dessus : une bordure en pente compte pour sa projection, une berge verticale pour zéro
            a, b, c = tris[:, 0, :2], tris[:, 1, :2], tris[:, 2, :2]
            ground_area += float((0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))).sum())
        lo, hi = tris.reshape(-1, 3).min(axis=0), tris.reshape(-1, 3).max(axis=0)
        if lo[0] < minx - 0.5 or lo[1] < miny - 0.5 or hi[0] > maxx + 0.5 or hi[1] > maxy + 0.5:
            error("hors_zone", f"couche {name} : des triangles sortent de la zone")
    # pente du sol, mesurée le long des arêtes (robuste, contrairement à la normale d'un triangle très mince) :
    # on ignore les arêtes verticales (berges) et celles de moins de 0,5 m
    steepest = 0.0
    for name in ("terrain", "chaussees", "trottoirs"):
        tris, _ = load_mesh(gen / f"{name}.npz")
        for i, j in ((0, 1), (1, 2), (2, 0)):
            d = tris[:, j] - tris[:, i]
            run_ = np.hypot(d[:, 0], d[:, 1])
            ok = run_ > 0.5
            if ok.any():
                steepest = max(steepest, float(np.degrees(np.arctan(np.abs(d[ok, 2]) / run_[ok])).max()))
    if steepest > 25.0:
        warn("pente_forte", f"pente maximale du sol de {steepest:.1f} degrés : à vérifier (donnée d'altitude bruitée ?)", pente_max_deg=round(steepest, 1))
    # le mailleur cale les coordonnées sur 1 cm : on compare à la zone calée, pas à la zone brute
    zone_snapped = shapely.set_precision(zone, 0.01).area
    if abs(ground_area - zone_snapped) > 1.0:
        error("maillage_sol", f"la surface des maillages du sol ({ground_area:.1f} m2) diffère de celle de la zone ({zone_snapped:.1f} m2)",
              ecart_m2=round(ground_area - zone_snapped, 1))

    # 3. conflits
    buildings = read_features(gen / "buildings.geojson")
    solid = [(g, p) for g, p in buildings if p.get("type") != "roof"]
    road_surface = [g for g, p in ground if p["genre"] in ("revetu", "non_revetu")]
    if solid and road_surface:
        tree = STRtree(road_surface)
        for g, p in solid:
            on_road = sum(g.intersection(road_surface[k]).area for k in tree.query(g).tolist())
            if on_road > 1.0:
                error("batiment_sur_route", f"{p['id']} empiète de {on_road:.1f} m2 sur une chaussée", objet=p["id"])
    if solid:
        geoms = [g for g, _ in solid]
        tree = STRtree(geoms)
        for i, g in enumerate(geoms):
            for j in tree.query(g).tolist():
                if j > i and g.intersection(geoms[j]).area > 0.5:
                    error("batiments_superposes", f"{solid[i][1]['id']} et {solid[j][1]['id']} se chevauchent", objet=solid[i][1]["id"])

    # 4. réseau
    roads = read_features(filled / "roads.geojson")
    isolated = [(g, p) for g, p in roads if p.get("reseau") == "isole"]
    if isolated:
        error("reseau_isole", f"{len(isolated)} route(s) sans lien avec le réseau principal ({sum(g.length for g, _ in isolated):.0f} m)",
              routes=[p["id"] for _, p in isolated][:50])

    # 5. accessibilité à pied
    water = [g for g, p in ground if p["genre"] == "eau"]
    seeds = [g for g, p in roads if not p["pieton"] and not p["tunnel"]]
    access = analyse(zone, [g for g, _ in solid], water, seeds)

    def locate(piece) -> dict:
        c = piece.representative_point()
        lon, lat = frame.to_wgs84(c.x, c.y)
        return {"surface_m2": round(piece.area), "x": round(c.x, 1), "y": round(c.y, 1), "lon": round(float(lon), 6), "lat": round(float(lat), 6)}

    if access.pockets:
        spots = sorted((locate(p) for p in access.pockets), key=lambda q: (-q["surface_m2"], q["x"], q["y"]))
        error("zone_inaccessible", f"{len(spots)} espace(s) fermé(s) inaccessible(s) à pied ({sum(q['surface_m2'] for q in spots)} m2)", poches=spots[:200])
    if access.wet_pockets:
        spots = sorted((locate(p) for p in access.wet_pockets), key=lambda q: (-q["surface_m2"], q["x"], q["y"]))
        warn("terrain_borde_eau", f"{len(spots)} terrain(s) bordé(s) par l'eau, inaccessibles à pied ({sum(q['surface_m2'] for q in spots)} m2) : îles ou berges, laissés tels quels",
             terrains=spots[:200])

    def by_source(features) -> dict:
        out = {"osm": 0, "genere": 0}
        for _, p in features:
            out[p.get("source", "osm")] = out.get(p.get("source", "osm"), 0) + 1
        return out

    b_src, r_src = by_source(buildings), by_source(roads)
    report = {
        "projet": ctx.project.slug, "ville": ctx.config.city, "quartier": ctx.config.district,
        "zone_km2": round(zone.area / 1e6, 3), "triangles": triangles, "pente_max_deg": round(steepest, 1),
        "altitudes_m": scene.get("altitudes"),
        "batiments": len(buildings), "hauteurs_estimees": sum(1 for _, p in buildings if p.get("hauteur_source") == "genere"),
        "routes": len(roads), "routes_km": round(sum(g.length for g, _ in roads) / 1000.0, 2),
        "elements_par_source": {"osm": b_src["osm"] + r_src["osm"], "genere": b_src["genere"] + r_src["genere"]},
        "batiments_par_source": b_src, "routes_par_source": r_src,
        "part_generee": round(b_src["genere"] / len(buildings), 4) if buildings else 0.0,
        "marcheur": {"rayon_m": 0.4, "surface_libre_m2": round(access.free_area), "part_accessible": round(access.ratio, 4),
                     "poches_inaccessibles": len(access.pockets), "terrains_bordes_eau": len(access.wet_pockets)},
        "decisions": {stage: ctx.journal.counts(stage) for stage in ("nettoyage", "secours", "generation")},
        "erreurs": errors, "avertissements": warnings,
        "non_verifie": [
            "ce rapport ne remplace pas les bots dans un moteur de jeu (voir verif/godot)",
            "aucune comparaison avec le terrain réel",
            "relief : modèle de surface de 30 m de résolution, lissé ; il contient des bâtiments et des arbres, et ne voit pas les petits reliefs (talus, remblais, caniveaux)",
        ],
    }
    ctx.project.reports.mkdir(parents=True, exist_ok=True)
    (ctx.project.reports / "qualite.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    lines = [f"# Rapport de qualité : {ctx.config.city}" + (f", {ctx.config.district}" if ctx.config.district else ""), "",
             f"- Zone : {report['zone_km2']} km2 ; {report['batiments']} bâtiments, dont {b_src['genere']} générés ({report['part_generee'] * 100:.1f} %) "
             f"et {report['hauteurs_estimees']} hauteurs estimées ; {report['routes']} routes ({report['routes_km']} km), dont {r_src['genere']} générées ; {triangles} triangles.",
             f"- Accessibilité à pied : {access.ratio * 100:.2f} % de la surface libre est atteignable depuis les routes.",
             f"- **Erreurs : {len(errors)}** ; avertissements : {len(warnings)}.", "", "## Erreurs"]
    lines += [f"- {e['texte']}" for e in errors[:100]] or ["Aucune."]
    lines += ["", "## Avertissements"]
    lines += [f"- {w['texte']}" for w in warnings] or ["Aucun."]
    lines += ["", "## Ce qui n'a pas été vérifié"] + [f"- {t}" for t in report["non_verifie"]]
    (ctx.project.reports / "qualite.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"erreurs": len(errors), "avertissements": len(warnings), "part_accessible": round(access.ratio, 4),
            "poches_inaccessibles": len(access.pockets)}
