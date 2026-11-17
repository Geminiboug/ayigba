"""Étape « export » : format neutre, lisible par tout moteur.

Sorties dans out/neutre/ :
  carte.glb            maillages (un nœud par couche, couleurs par sommet, Y vers le haut, mètres)
  routes.geojson       réseau de routes en WGS84 (classe, largeur, sens, revêtement) pour GPS et mini-carte
  batiments.geojson    emprises et hauteurs en WGS84
  points_interet.geojson
  manifeste.json       repère, couches (avec ou sans collision), compteurs, résumé de qualité
  CREDITS.md           sources et licences
"""
from __future__ import annotations

import json

import numpy as np
import shapely

from .. import __version__
from ..credits import write_credits
from ..geo import LocalFrame, read_features, write_features
from ..gltf import write_glb
from ..mesh import load_mesh

STAGE = "export"


def run(ctx) -> dict:
    clean = ctx.project.work / "nettoyage"
    gen = ctx.project.work / "generation"
    out = ctx.project.out / "neutre"
    out.mkdir(parents=True, exist_ok=True)
    frame = LocalFrame(ctx.config.bbox)

    scene = json.loads((gen / "scene.json").read_text(encoding="utf-8"))
    layers = []
    for layer in scene["couches"]:
        tris, colors = load_mesh(gen / f"{layer['nom']}.npz")
        layers.append((layer["nom"], tris, colors))
    stats = write_glb(out / "carte.glb", layers, extras={"generateur": f"ayigba {__version__}", "unite": "metre", "graine": ctx.config.seed})

    def to_wgs84(features):
        def convert(coords: np.ndarray) -> np.ndarray:
            lon, lat = frame.to_wgs84(coords[:, 0], coords[:, 1])
            return np.column_stack([lon, lat])
        return [(shapely.transform(g, convert), p) for g, p in features]

    roads = read_features(clean / "roads.geojson")
    buildings = read_features(gen / "buildings.geojson")
    pois = read_features(clean / "pois.geojson")
    write_features(out / "routes.geojson", to_wgs84(roads), ndigits=7)
    write_features(out / "batiments.geojson", to_wgs84(buildings), ndigits=7)
    write_features(out / "points_interet.geojson", to_wgs84(pois), ndigits=7)

    generated = sum(1 for _, p in roads + buildings if p.get("source") == "genere")
    write_credits(ctx, out, nb_generes=generated)

    quality_path = ctx.project.reports / "qualite.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}
    manifest = {
        "generateur": f"ayigba {__version__}",
        "projet": ctx.project.slug, "ville": ctx.config.city, "quartier": ctx.config.district,
        "graine": ctx.config.seed, "zone_wgs84": list(ctx.config.bbox),
        "repere": {"origine_lon": frame.lon0, "origine_lat": frame.lat0, "epsg_projection": frame.epsg, "unite": "metre",
                   "gltf": "X = est, Y = haut, Z = sud (soit -nord) ; origine au centre de la zone"},
        "couches": [{**layer, "triangles": stats.get(layer["nom"], 0)} for layer in scene["couches"]],
        "fichiers": ["carte.glb", "routes.geojson", "batiments.geojson", "points_interet.geojson", "CREDITS.md"],
        "compteurs": {"routes": len(roads), "batiments": len(buildings), "points_interet": len(pois), "elements_generes": generated},
        "qualite": {"erreurs": len(quality.get("erreurs", [])), "avertissements": len(quality.get("avertissements", [])),
                    "non_verifie": quality.get("non_verifie", [])},
    }
    (out / "manifeste.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    size = (out / "carte.glb").stat().st_size
    return {"dossier": str(out.relative_to(ctx.project.root)), "glb_mo": round(size / 1e6, 2), "triangles": sum(stats.values()), "elements_generes": generated}
