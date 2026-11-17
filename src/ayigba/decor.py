"""Placement automatique des décors (arbres, poteaux, lampadaires, étals...) selon le type de lieu.

Le résultat est une liste de points : type de décor, position, angle, source. L'outil en fait des maillages légers,
et exporte aussi la liste : un jeu peut y poser ses propres modèles à la place.
Règles simples de cette version, toutes marquées « genere » sauf les arbres relevés dans OpenStreetMap.
"""
from __future__ import annotations

import math

from shapely import STRtree, prepare
from shapely.geometry import Point
from shapely.ops import unary_union

from .mesh import rng_for
from .props import emprise

PARKS = {"park", "garden", "grass", "recreation_ground", "cemetery", "meadow", "village_green"}
BEACHES = {"beach", "sand"}
MARKETS = {"marketplace"}


class _Placer:
    def __init__(self, zone, buildings, forbidden):
        self.zone = zone
        self.buildings = buildings
        self.tree = STRtree(buildings) if buildings else None
        self.forbidden = forbidden  # chaussées + eau : aucun décor dessus
        if forbidden is not None:
            prepare(forbidden)
        self.cells: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
        self.items: list[dict] = []

    def add(self, kind: str, x: float, y: float, angle: float, source: str = "genere") -> bool:
        r = emprise(kind)
        p = Point(x, y)
        if not self.zone.contains(p) or self.zone.exterior.distance(p) < r + 0.5:
            return False
        if self.forbidden is not None and self.forbidden.distance(p) < min(r, 0.6):
            return False
        if self.tree is not None and any(self.buildings[k].distance(p) < min(r, 1.0) + 0.2 for k in self.tree.query(p.buffer(r + 0.5)).tolist()):
            return False
        cx, cy = int(x // 6), int(y // 6)
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for ox, oy, orad in self.cells.get((i, j), ()):
                    if math.hypot(x - ox, y - oy) < min(r + orad, 3.0):
                        return False
        self.cells.setdefault((cx, cy), []).append((x, y, r))
        self.items.append({"type": kind, "x": round(x, 2), "y": round(y, 2), "angle": round(angle, 3), "source": source})
        return True


def _along(line, step: float, offset: float, start: float):
    """Points le long d'une ligne, tous les `step` mètres, décalés de `offset` à gauche (positif) ou à droite. Renvoie (x, y, cap)."""
    d = start
    while d < line.length:
        a, b = line.interpolate(max(d - 0.5, 0.0)), line.interpolate(min(d + 0.5, line.length))
        heading = math.atan2(b.y - a.y, b.x - a.x)
        c = line.interpolate(d)
        yield c.x - math.sin(heading) * offset, c.y + math.cos(heading) * offset, heading
        d += step


def place_decor(zone, roads, buildings, water, road_surface, landuse, pois, seed: int) -> list[dict]:
    """roads, buildings, landuse, pois : listes (géométrie, propriétés). water, road_surface : géométries ou None."""
    forbidden = [g for g in (water, road_surface) if g is not None and not g.is_empty]
    placer = _Placer(zone, [g for g, _ in buildings], unary_union(forbidden) if forbidden else None)

    for g, p in pois:  # arbres réels d'abord : ils ont la priorité sur les décors générés
        if p.get("genre") == "arbre":
            placer.add("arbre", g.x, g.y, rng_for(seed, "arbre:" + p["id"]).uniform(0, 6.28), source="osm")

    for g, p in roads:
        if p["tunnel"] or p["pieton"] or g.length < 25:
            continue
        rng = rng_for(seed, "decor-route:" + p["id"])
        half = p["largeur"] / 2.0
        if p["classe"] in ("motorway", "trunk", "primary", "secondary", "tertiary") and p["revetement"] == "pave":
            side = 1.0
            for x, y, h in _along(g, 40.0, half + 1.0, rng.uniform(5, 30)):
                placer.add("lampadaire", x * 1.0 + 0.0, y, h + (math.pi / 2 if side > 0 else -math.pi / 2))
                side = -side
        else:
            for x, y, h in _along(g, 50.0, -(half + 0.7), rng.uniform(5, 45)):
                placer.add("poteau_electrique", x, y, h)
            if p["revetement"] == "non_pave":
                for x, y, h in _along(g, 260.0, half + 1.2, rng.uniform(20, 240)):
                    if rng.random() < 0.6:
                        placer.add("tas_dechets", x, y, rng.uniform(0, 6.28))
            if p["classe"] in ("residential", "unclassified", "living_street"):
                for x, y, h in _along(g, 140.0, half + 1.6, rng.uniform(10, 130)):
                    if rng.random() < 0.5:
                        placer.add("etal", x, y, h)

    for g, p in pois:
        if p.get("type") in MARKETS:
            rng = rng_for(seed, "marche:" + p["id"])
            for _ in range(40):
                a, d = rng.uniform(0, 6.28), rng.uniform(3, 35)
                placer.add("etal", g.x + math.cos(a) * d, g.y + math.sin(a) * d, rng.uniform(0, 6.28))
        elif p.get("type") == "bus_stop":
            placer.add("panneau", g.x, g.y, 0.0)

    for g, p in landuse:
        kind = p.get("genre")
        if kind not in PARKS and kind not in BEACHES:
            continue
        rng = rng_for(seed, "vegetation:" + p["id"] + f":{round(g.centroid.x)}")
        per = 180.0 if kind in PARKS else 500.0
        minx, miny, maxx, maxy = g.bounds
        for _ in range(min(int(g.area / per), 400)):
            x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
            if g.contains(Point(x, y)):
                placer.add("arbre" if kind in PARKS else "palmier", x, y, rng.uniform(0, 6.28))
    return placer.items
