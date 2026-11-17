"""Bâtiments absents d'OpenStreetMap, détectés dans la couche « présence » de Google Open Buildings 2.5D.

OpenStreetMap ne couvre qu'une partie des bâtiments du Bénin. La couche de présence (probabilité qu'un pixel de 2 m soit
un bâtiment) permet d'en retrouver d'autres : on seuille, on retire ce qu'OSM a déjà, on transforme chaque tache en
polygone simple. Ces bâtiments sont marqués source = « google_25d » : ce sont des détections par IA, pas des relevés.
"""
from __future__ import annotations

import numpy as np
import rasterio.features
import shapely
from affine import Affine
from shapely.geometry import shape
from shapely.ops import unary_union

SEUIL = 0.5
AIRE_MIN = 12.0       # m2 : en dessous, bruit
AIRE_MAX = 3000.0     # m2 : au-delà, souvent plusieurs bâtiments fusionnés ou une zone mal détectée
MARGE_OSM = 1.5       # m : une tache à moins de 1,5 m d'un bâtiment OSM lui appartient


def detecter(bat: dict, vers_local, zone, deja: list, interdit=None) -> list:
    """bat : dict de batiments25d ; vers_local(x_utm, y_utm) -> (x, y) locaux ; zone : polygone local ;
    deja : polygones locaux des bâtiments connus ; interdit : géométrie locale où aucun bâtiment ne doit être posé
    (chaussées, eau). Renvoie une liste de polygones locaux, triée de façon déterministe."""
    presence = np.asarray(bat["presence"], dtype=np.float32)
    masque = (presence >= SEUIL).astype(np.uint8)
    if not masque.any():
        return []
    p = float(bat["pas"])
    transform = Affine(p, 0.0, float(bat["x0"]), 0.0, -p, float(bat["y0"]))
    connus = unary_union(deja).buffer(MARGE_OSM) if deja else None
    out = []
    for geom, val in rasterio.features.shapes(masque, mask=masque.astype(bool), transform=transform, connectivity=4):
        if val != 1:
            continue
        poly = shape(geom)
        if poly.area < AIRE_MIN or poly.area > AIRE_MAX:
            continue
        loc = shapely.transform(poly, lambda c: np.column_stack(vers_local(c[:, 0], c[:, 1])))
        if not loc.is_valid:
            loc = shapely.make_valid(loc)
        loc = loc.intersection(zone)
        if connus is not None:
            loc = loc.difference(connus)
        if interdit is not None:
            loc = loc.difference(interdit)
        for q in getattr(loc, "geoms", [loc]):
            if q.geom_type != "Polygon" or q.area < AIRE_MIN:
                continue
            q = q.buffer(-0.5).buffer(0.5)               # retire les franges d'un pixel
            for r in getattr(q, "geoms", [q]):
                if r.geom_type != "Polygon" or r.area < AIRE_MIN:
                    continue
                rect = r.minimum_rotated_rectangle
                # un bâtiment est presque toujours un rectangle : on le garde rectangle dès qu'il en est proche,
                # sinon un contour simplifié (moins de sommets, donc moins de triangles)
                forme = rect if r.area / rect.area > 0.7 else r.simplify(1.0)
                if connus is not None:
                    forme = forme.difference(connus)
                if interdit is not None:
                    forme = forme.difference(interdit)
                forme = forme.intersection(zone)
                if forme.geom_type == "Polygon" and forme.area >= AIRE_MIN and forme.is_valid:
                    out.append(shapely.set_precision(forme, 0.01))
    out = [g for g in out if not g.is_empty and g.geom_type == "Polygon"]
    out.sort(key=lambda g: (round(g.centroid.x, 2), round(g.centroid.y, 2)))
    # deux détections qui se touchent après simplification : on garde la plus grande
    gardes = []
    for g in sorted(out, key=lambda g: -g.area):
        if not any(g.intersection(h).area > 0.5 for h in gardes):
            gardes.append(g)
    gardes.sort(key=lambda g: (round(g.centroid.x, 2), round(g.centroid.y, 2)))
    return gardes
