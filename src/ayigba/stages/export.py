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
import shutil

import numpy as np
import shapely
from shapely import STRtree

from .. import __version__
from ..credits import write_credits
from ..geo import LocalFrame, read_features, write_features
from ..gltf import write_glb
from ..mesh import load_mesh

STAGE = "export"

# Densité de motos-taxis (zems) par route, de 0 à 1 : une DONNÉE pour les jeux, estimée par une règle simple
# (classe de la route, proximité d'un lieu qui attire les zems). Aucune mesure de terrain derrière ces valeurs.
ZEM_BASE = {"trunk": 0.8, "primary": 0.9, "secondary": 0.8, "tertiary": 0.7, "unclassified": 0.5, "residential": 0.4,
            "living_street": 0.3, "service": 0.15, "track": 0.1}
ZEM_MAGNETS = {"marketplace", "bus_station", "taxi", "fuel", "hospital", "clinic", "university", "college", "school", "bank", "place_of_worship"}


def _zem_density(roads, pois) -> None:
    magnets = [g for g, p in pois if p.get("type") in ZEM_MAGNETS]
    tree = STRtree(magnets) if magnets else None
    for g, p in roads:
        d = 0.0 if p["pieton"] else ZEM_BASE.get(p["classe"], 0.2)
        if d > 0 and tree is not None and len(tree.query(g.buffer(150.0))) > 0:
            d = min(1.0, d + 0.2)
        p["densite_zems"] = round(d, 2)
        p["densite_zems_source"] = "regle"


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

    roads = read_features(ctx.project.work / "secours" / "roads.geojson")
    _zem_density(roads, read_features(clean / "pois.geojson"))
    buildings = read_features(gen / "buildings.geojson")
    pois = read_features(clean / "pois.geojson")
    write_features(out / "routes.geojson", to_wgs84(roads), ndigits=7)
    write_features(out / "batiments.geojson", to_wgs84(buildings), ndigits=7)
    write_features(out / "points_interet.geojson", to_wgs84(pois), ndigits=7)

    decors = read_features(gen / "decors.geojson") if (gen / "decors.geojson").is_file() else []
    write_features(out / "decors.geojson", to_wgs84(decors), ndigits=7)

    # routes dans le repère de la carte (mètres), pour les bots, le GPS et la circulation d'un jeu
    local_roads = [{"id": p["id"], "classe": p["classe"], "largeur": p["largeur"], "sens_unique": p["sens_unique"], "sens_inverse": p.get("sens_inverse", False), "voies": p.get("voies", 1),
                    "pieton": p["pieton"], "densite_zems": p["densite_zems"],
                    "revetement": p["revetement"], "points": [[round(x, 2), round(y, 2)] for x, y in g.coords]} for g, p in roads if g.geom_type == "LineString"]
    (out / "routes_local.json").write_text(json.dumps({"repere": "x est, y nord, metres ; dans le glTF : X = x, Z = -y", "routes": local_roads},
                                                      ensure_ascii=False, sort_keys=True), encoding="utf-8")

    # zones chargeables à la demande (étape optimisation)
    opt = ctx.project.work / "optimisation"
    zones_doc = None
    if (opt / "zones.json").is_file():
        zones_doc = json.loads((opt / "zones.json").read_text(encoding="utf-8"))
        zdir = out / "zones"
        if zdir.exists():
            shutil.rmtree(zdir)
        zdir.mkdir()
        for z in zones_doc["zones"]:
            with np.load(opt / "zones" / f"{z['nom']}.npz") as data:
                zl = [(c["nom"], data[f"{c['nom']}__triangles"].astype(np.float64), data[f"{c['nom']}__couleurs"]) for c in z["couches"]]
            write_glb(zdir / f"{z['nom']}.glb", zl, extras={"zone": z["nom"], "emprise_locale": z["emprise"]})
            z["fichier"] = f"zones/{z['nom']}.glb"
        (out / "zones.json").write_text(json.dumps(zones_doc, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    generated = sum(1 for _, p in roads + buildings + decors if p.get("source") == "genere")
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
        "fichiers": ["carte.glb", "routes.geojson", "routes_local.json", "batiments.geojson", "points_interet.geojson", "decors.geojson", "CREDITS.md"]
                    + (["zones.json", "zones/"] if zones_doc else []),
        "zones": {"nombre": len(zones_doc["zones"]), "taille_zone_m": zones_doc["taille_zone_m"], "distance_detail_m": zones_doc["distance_detail_m"]} if zones_doc else None,
        "compteurs": {"routes": len(roads), "batiments": len(buildings), "points_interet": len(pois), "decors": len(decors), "elements_generes": generated},
        "qualite": {"erreurs": len(quality.get("erreurs", [])), "avertissements": len(quality.get("avertissements", [])),
                    "non_verifie": quality.get("non_verifie", [])},
    }
    (out / "manifeste.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    size = (out / "carte.glb").stat().st_size
    return {"dossier": str(out.relative_to(ctx.project.root)), "glb_mo": round(size / 1e6, 2), "triangles": sum(stats.values()), "elements_generes": generated}
