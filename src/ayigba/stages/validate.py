"""Étape « tests » : contrôle de la carte générée et rapport de qualité.

Contrôles de cette version :
1. Sol : la partition couvre toute la zone, sans trou ni chevauchement.
2. Maillages : valeurs finies, pas de triangle dégénéré, noms de couches autorisés, tout est dans la zone.
3. Conflits : aucun bâtiment sur une chaussée, aucun bâtiment sur un autre.
4. Réseau de routes : réseaux isolés.
5. Marcheur sur grille : depuis le réseau principal, un piéton avance de case en case (2 m) sans traverser
   bâtiments ni eau. Les poches libres qu'il n'atteint jamais sont des zones inaccessibles.

Ce n'est PAS encore un test dans un moteur de jeu : ni physique, ni véhicule, ni navmesh. Voir docs/CHANTIER.md.
"""
from __future__ import annotations

import json
from collections import deque

import numpy as np
import shapely
from shapely import STRtree
from shapely.ops import unary_union

from ..geo import LocalFrame, read_features
from ..gltf import check_name
from ..mesh import load_mesh

STAGE = "tests"
CELL = 2.0            # taille d'une case du marcheur, en mètres
POCKET_MIN = 100.0    # une poche inaccessible plus petite n'est pas signalée (m2)


def _rasterize(geoms, x0: float, y0: float, nx: int, ny: int) -> np.ndarray:
    """Cases dont le centre est dans une des géométries."""
    grid = np.zeros((ny, nx), dtype=bool)
    for g in geoms:
        minx, miny, maxx, maxy = g.bounds
        i0, i1 = max(int((minx - x0) // CELL), 0), min(int((maxx - x0) // CELL) + 1, nx)
        j0, j1 = max(int((miny - y0) // CELL), 0), min(int((maxy - y0) // CELL) + 1, ny)
        if i0 >= i1 or j0 >= j1:
            continue
        xs = x0 + (np.arange(i0, i1) + 0.5) * CELL
        ys = y0 + (np.arange(j0, j1) + 0.5) * CELL
        gx, gy = np.meshgrid(xs, ys)
        grid[j0:j1, i0:i1] |= shapely.contains_xy(g, gx, gy)
    return grid


def _flood(free: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    reach = seeds & free
    frontier = reach.copy()
    while frontier.any():
        grown = np.zeros_like(frontier)
        grown[1:, :] |= frontier[:-1, :]
        grown[:-1, :] |= frontier[1:, :]
        grown[:, 1:] |= frontier[:, :-1]
        grown[:, :-1] |= frontier[:, 1:]
        frontier = grown & free & ~reach
        reach |= frontier
    return reach


def _pockets(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Groupes de cases voisines (4 directions) dans un masque."""
    seen = np.zeros_like(mask)
    groups = []
    ny, nx = mask.shape
    for j, i in zip(*np.nonzero(mask)):
        if seen[j, i]:
            continue
        seen[j, i] = True
        group, queue = [], deque([(int(j), int(i))])
        while queue:
            cj, ci = queue.popleft()
            group.append((cj, ci))
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nj, ni = cj + dj, ci + di
                if 0 <= nj < ny and 0 <= ni < nx and mask[nj, ni] and not seen[nj, ni]:
                    seen[nj, ni] = True
                    queue.append((nj, ni))
        groups.append(group)
    return groups


def run(ctx) -> dict:
    clean = ctx.project.work / "nettoyage"
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
    walkable_area = 0.0  # surface des faces horizontales du sol et de l'eau, mesurée sur les maillages eux-mêmes
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
        if name in ("terrain", "chaussees", "eau"):
            level = np.ptp(tris[:, :, 2], axis=1) < 1e-6
            walkable_area += float(area[level].sum())
        flat = int((area < 1e-7).sum())
        if flat:
            warn("triangles_plats", f"couche {name} : {flat} triangle(s) de surface nulle (retirés à l'export)", couche=name, nombre=flat)
        lo, hi = tris.reshape(-1, 3).min(axis=0), tris.reshape(-1, 3).max(axis=0)
        if lo[0] < minx - 0.5 or lo[1] < miny - 0.5 or hi[0] > maxx + 0.5 or hi[1] > maxy + 0.5:
            error("hors_zone", f"couche {name} : des triangles sortent de la zone")

    if abs(walkable_area - zone.area) > 1.0:
        error("maillage_sol", f"la surface des maillages du sol ({walkable_area:.1f} m2) diffère de celle de la zone ({zone.area:.1f} m2)",
              ecart_m2=round(walkable_area - zone.area, 1))

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
    roads = read_features(clean / "roads.geojson")
    isolated = [(g, p) for g, p in roads if p.get("reseau") == "isole"]
    if isolated:
        warn("reseau_isole", f"{len(isolated)} route(s) sans lien avec le réseau principal ({sum(g.length for g, _ in isolated):.0f} m)",
             routes=[p["id"] for _, p in isolated][:50])

    # 5. marcheur sur grille
    nx, ny = int(np.ceil((maxx - minx) / CELL)), int(np.ceil((maxy - miny) / CELL))
    blocked = _rasterize([g for g, _ in solid], minx, miny, nx, ny)
    blocked |= _rasterize([g for g, p in ground if p["genre"] == "eau"], minx, miny, nx, ny)
    free = ~blocked
    main = [g.buffer(max(p["largeur"] / 2.0, CELL * 0.75)) for g, p in roads if p.get("reseau") == "principal" and not p["tunnel"]]
    seeds = _rasterize(main, minx, miny, nx, ny)
    reach = _flood(free, seeds)
    lost = free & ~reach
    pockets = []
    for group in _pockets(lost):
        surface = len(group) * CELL * CELL
        if surface < POCKET_MIN:
            continue
        js, is_ = np.array([c[0] for c in group]), np.array([c[1] for c in group])
        cx, cy = minx + (is_.mean() + 0.5) * CELL, miny + (js.mean() + 0.5) * CELL
        lon, lat = frame.to_wgs84(cx, cy)
        pockets.append({"surface_m2": round(surface), "x": round(float(cx), 1), "y": round(float(cy), 1), "lon": round(float(lon), 6), "lat": round(float(lat), 6)})
    pockets.sort(key=lambda q: (-q["surface_m2"], q["x"], q["y"]))
    if pockets:
        warn("zone_inaccessible", f"{len(pockets)} poche(s) libre(s) de plus de {POCKET_MIN:.0f} m2 qu'un piéton n'atteint pas depuis les routes "
             f"({sum(q['surface_m2'] for q in pockets):.0f} m2 au total) : cours fermées ou terrains enclavés", poches=pockets[:200])
    road_cells = _rasterize([g.buffer(max(p["largeur"] / 2.0, CELL * 0.75)) for g, p in isolated], minx, miny, nx, ny) if isolated else None
    if road_cells is not None and (road_cells & free & ~reach).any():
        warn("route_inatteignable", "des routes isolées ne sont pas atteignables à pied depuis le réseau principal")

    free_n = int(free.sum())
    sources = {"osm": sum(1 for _, p in buildings if p.get("source") == "osm") + sum(1 for _, p in roads if p.get("source") == "osm"),
               "genere": sum(1 for _, p in buildings if p.get("source") == "genere") + sum(1 for _, p in roads if p.get("source") == "genere")}
    report = {
        "projet": ctx.project.slug, "ville": ctx.config.city, "quartier": ctx.config.district,
        "zone_km2": round(zone.area / 1e6, 3), "triangles": triangles,
        "batiments": len(buildings), "hauteurs_estimees": sum(1 for _, p in buildings if p.get("hauteur_source") == "genere"),
        "routes": len(roads), "routes_km": round(sum(g.length for g, _ in roads) / 1000.0, 2),
        "elements_par_source": sources,
        "marcheur": {"case_m": CELL, "surface_libre_m2": round(free_n * CELL * CELL), "part_accessible": round(float(reach.sum()) / free_n, 4) if free_n else 1.0,
                     "poches_inaccessibles": len(pockets)},
        "decisions": {stage: ctx.journal.counts(stage) for stage in ("nettoyage", "generation")},
        "erreurs": errors, "avertissements": warnings,
        "non_verifie": [
            "aucun test dans un moteur de jeu avec physique (personnage, véhicule, navmesh)",
            "aucune comparaison avec le terrain réel",
            "relief absent : le terrain est plat",
        ],
    }
    ctx.project.reports.mkdir(parents=True, exist_ok=True)
    (ctx.project.reports / "qualite.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    lines = [f"# Rapport de qualité : {ctx.config.city}, {ctx.config.district}", "",
             f"- Zone : {report['zone_km2']} km2 ; {report['batiments']} bâtiments ({report['hauteurs_estimees']} hauteurs estimées) ; "
             f"{report['routes']} routes ({report['routes_km']} km) ; {triangles} triangles.",
             f"- Marcheur sur grille de {CELL:.0f} m : {report['marcheur']['part_accessible'] * 100:.1f} % de la surface libre est accessible depuis les routes.",
             f"- **Erreurs : {len(errors)}** ; avertissements : {len(warnings)}.", "", "## Erreurs"]
    lines += [f"- {e['texte']}" for e in errors[:100]] or ["Aucune."]
    lines += ["", "## Avertissements"]
    lines += [f"- {w['texte']}" for w in warnings] or ["Aucun."]
    lines += ["", "## Ce qui n'a pas été vérifié"] + [f"- {t}" for t in report["non_verifie"]]
    (ctx.project.reports / "qualite.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"erreurs": len(errors), "avertissements": len(warnings), "part_accessible": report["marcheur"]["part_accessible"],
            "poches_inaccessibles": len(pockets)}
