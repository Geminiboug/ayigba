"""Accessibilité à pied, calculée sur les formes exactes (pas sur une grille).

Un personnage est un disque de rayon `radius`. L'espace où son centre peut se trouver est l'espace libre
(zone moins bâtiments moins eau) rétréci de ce rayon. Chaque morceau de cet espace que le réseau de routes
carrossables ne touche pas est une poche inaccessible : cour fermée, terrain enclavé, passage trop étroit.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely import STRtree
from shapely.geometry import Polygon
from shapely.ops import unary_union

RADIUS = 0.4       # rayon d'un personnage, en mètres
POCKET_MIN = 4.0   # surface minimale (du centre du personnage) pour compter une poche, en m2


def polygons(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in polygons(g)]
    return []


@dataclass
class Access:
    free_area: float            # surface libre totale (m2)
    reachable_area: float       # surface libre atteignable depuis les routes (m2)
    pockets: list[Polygon]      # poches à combler (forme réelle, dans l'espace libre)
    wet_pockets: list[Polygon]  # poches bordées par l'eau : îles ou berges, laissées telles quelles

    @property
    def ratio(self) -> float:
        return self.reachable_area / self.free_area if self.free_area > 0 else 1.0


def analyse(zone: Polygon, solids: list, water: list, seed_lines: list, radius: float = RADIUS) -> Access:
    """solids : emprises infranchissables ; water : polygones d'eau ; seed_lines : axes des routes carrossables du réseau principal."""
    blocked = unary_union([*solids, *water]) if (solids or water) else None
    free = zone if blocked is None else zone.difference(blocked)
    walk_parts = [p for p in polygons(free.buffer(-radius)) if p.area > 0]
    if not walk_parts:
        return Access(free.area, 0.0, [], [])
    tree = STRtree(walk_parts)
    touched: set[int] = set()
    for line in seed_lines:
        for k in tree.query(line).tolist():
            if k not in touched and walk_parts[k].intersects(line):
                touched.add(k)
    water_union = unary_union(water) if water else None
    pockets, wet, lost = [], [], 0.0
    for k, part in enumerate(walk_parts):
        if k in touched or part.area < POCKET_MIN:
            continue
        shape = part.buffer(radius + 0.05).intersection(free)
        lost += shape.area
        for piece in polygons(shape):
            if water_union is not None and piece.distance(water_union) < 0.5:
                wet.append(piece)
            else:
                pockets.append(piece)
    return Access(free.area, max(free.area - lost, 0.0), pockets, wet)
