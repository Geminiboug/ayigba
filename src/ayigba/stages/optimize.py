"""Étape « optimisation » : découpage en zones chargeables à la demande, niveaux de détail, budget par zone.

Entrée  : work/generation/*.npz, buildings.geojson
Sorties : work/optimisation/zones/<zone>.npz (une archive par zone : triangles et couleurs de chaque couche)
          work/optimisation/zones.json (index : emprise, triangles par couche, distances de niveau de détail)

Règles :
- La carte est découpée en carrés de `taille_zone_m` (250 m par défaut). Un triangle appartient à la zone qui contient
  son centre : aucun triangle n'est coupé ni perdu, donc aucun trou aux limites de zones.
- Deux niveaux de détail pour les bâtiments : de près, le volume réel ; de loin, une boîte orientée (10 triangles) pour
  les bâtiments d'au moins 60 m2, rien pour les plus petits. Les décors ne sont visibles que de près. Le sol ne change pas.
- Budget : si une zone dépasse `budget_triangles` de près, ses décors sont retirés ; si elle dépasse encore, c'est signalé.

Options de config.toml : [optimisation] taille_zone_m, budget_triangles, distance_detail_m.
"""
from __future__ import annotations

import json
import shutil

import numpy as np

from ..geo import LocalFrame, read_features
from ..mesh import MeshBuilder, load_mesh
from .clean import _polygons

STAGE = "optimisation"
FAR_MIN_AREA = 60.0
FAR_LAYER = "batiments_loin"
NEAR_ONLY = ("batiments", "decors")  # couches visibles seulement de près


def run(ctx) -> dict:
    gen = ctx.project.work / "generation"
    out = ctx.project.stage_dir(STAGE)
    zones_dir = out / "zones"
    if zones_dir.exists():
        shutil.rmtree(zones_dir)
    zones_dir.mkdir(parents=True)

    size = float(ctx.config.option("optimisation", "taille_zone_m", 250.0))
    budget = int(ctx.config.option("optimisation", "budget_triangles", 15000))
    detail = float(ctx.config.option("optimisation", "distance_detail_m", 350.0))
    zone = LocalFrame(ctx.config.bbox).zone_polygon()
    minx, miny, maxx, maxy = zone.bounds
    nx, ny = max(int(np.ceil((maxx - minx) / size)), 1), max(int(np.ceil((maxy - miny) / size)), 1)

    def cell_of(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        i = np.clip(((x - minx) // size).astype(int), 0, nx - 1)
        j = np.clip(((y - miny) // size).astype(int), 0, ny - 1)
        return j * nx + i

    scene = json.loads((gen / "scene.json").read_text(encoding="utf-8"))
    per_zone: dict[int, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
    for layer in scene["couches"]:
        tris, colors = load_mesh(gen / f"{layer['nom']}.npz")
        if len(tris) == 0:
            continue
        centers = tris.mean(axis=1)
        cells = cell_of(centers[:, 0], centers[:, 1])
        for c in np.unique(cells):
            sel = cells == c
            per_zone.setdefault(int(c), {})[layer["nom"]] = (tris[sel], colors[sel])

    # bâtiments vus de loin : une boîte orientée par bâtiment assez grand
    far: dict[int, MeshBuilder] = {}
    for geom, props in read_features(gen / "buildings.geojson"):
        if geom.area < FAR_MIN_AREA:
            continue
        c = geom.centroid
        cell = int(cell_of(np.array([c.x]), np.array([c.y]))[0])
        for part in _polygons(geom.minimum_rotated_rectangle):
            far.setdefault(cell, MeshBuilder(FAR_LAYER)).add_prism(part, float(props.get("base", 0.0)), float(props.get("sommet", props["hauteur"])), (0.80, 0.76, 0.68), (0.52, 0.50, 0.50))
    for cell, builder in far.items():
        per_zone.setdefault(cell, {})[FAR_LAYER] = (builder.triangles, builder.colors)

    collisions = {layer["nom"]: layer["collision"] for layer in scene["couches"]}
    index = []
    over = stripped = 0
    for cell in sorted(per_zone):
        j, i = divmod(cell, nx)
        name = f"z_{i:02d}_{j:02d}"
        layers = per_zone[cell]
        near = sum(len(t) for n, (t, _) in layers.items() if n != FAR_LAYER)
        if near > budget and "decors" in layers:
            near -= len(layers["decors"][0])
            del layers["decors"]
            stripped += 1
            ctx.journal.record("corrige", f"zone/{name}", f"budget de {budget} triangles dépassé : décors retirés de cette zone")
        if near > budget:
            over += 1
            ctx.journal.record("signale", f"zone/{name}", f"{near} triangles de près pour un budget de {budget}")
        arrays = {}
        for lname, (t, col) in sorted(layers.items()):
            arrays[f"{lname}__triangles"] = t.astype(np.float32)
            arrays[f"{lname}__couleurs"] = col.astype(np.float32)
        np.savez_compressed(zones_dir / f"{name}.npz", **arrays)
        index.append({
            "nom": name, "colonne": i, "ligne": j,
            "emprise": [round(minx + i * size, 3), round(miny + j * size, 3), round(min(minx + (i + 1) * size, maxx), 3), round(min(miny + (j + 1) * size, maxy), 3)],
            "couches": [{"nom": n, "triangles": int(len(t)), "collision": bool(collisions.get(n, False)),
                         "visible": "loin" if n == FAR_LAYER else ("pres" if n in NEAR_ONLY else "toujours")} for n, (t, _) in sorted(layers.items())],
            "triangles_pres": int(near), "triangles_loin": int(sum(len(t) for n, (t, _) in layers.items() if n not in NEAR_ONLY)),
        })
    doc = {"taille_zone_m": size, "distance_detail_m": detail, "budget_triangles": budget, "colonnes": nx, "lignes": ny, "zones": index}
    (out / "zones.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    near_all = [z["triangles_pres"] for z in index]
    return {"zones": len(index), "taille_zone_m": size, "triangles_max_pres": max(near_all) if near_all else 0,
            "triangles_moyens_pres": int(np.mean(near_all)) if near_all else 0, "zones_hors_budget": over, "zones_sans_decors": stripped}
