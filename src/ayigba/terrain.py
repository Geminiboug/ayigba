"""Maillage conforme du sol : une seule triangulation de toute la zone, drapée sur le relief.

Principe : les limites de toutes les parties du sol (terre, chaussées, trottoirs, eau) sont des contraintes d'une
triangulation de Delaunay contrainte (bibliothèque « triangle »). Chaque triangle appartient donc à une seule partie, et
deux parties voisines partagent exactement les mêmes sommets : aucune fissure, aucun chevauchement, même sur un relief.
L'altitude est calculée en chaque sommet par la fonction `hauteur(x, y)` fournie (modèle numérique d'altitude).

Étapes : calage sur une grille de 1 cm, calcul des nœuds de toutes les limites, découpe des longs segments, triangulation
avec une aire maximale, classement de chaque triangle selon la partie qui le contient.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
import triangle
from shapely import STRtree
from shapely.geometry import MultiLineString, Polygon

GRID = 0.01          # calage des coordonnées (m) : évite les segments minuscules qui feraient exploser le raffinement
SEGMENT_MAX = 25.0   # les limites plus longues sont découpées (m), pour que le relief les suive
WATER = "eau"
WATER_DROP = 0.25    # le niveau d'un plan d'eau est 25 cm sous le sol le plus bas de son pourtour
BED_DEPTH = 0.9      # profondeur du fond sous le niveau de l'eau
BANK_BLEND = 40.0    # le sol redescend en pente douce vers l'eau sur cette distance (m)
BANK_FREEBOARD = 0.15  # la rive est 15 cm au-dessus de l'eau


@dataclass
class Ground:
    xy: np.ndarray          # (V, 2) sommets
    z: np.ndarray           # (V,) altitude du sol à chaque sommet (hors eau)
    tris: np.ndarray        # (T, 3) indices de sommets, sens direct (face vers le haut)
    kind: np.ndarray        # (T,) nom de la partie de chaque triangle
    shore: list             # arêtes entre l'eau et la terre : (a, b, niveau de l'eau), l'eau est à gauche de a -> b
    level: np.ndarray       # (T,) niveau de l'eau de chaque triangle d'eau (NaN pour les autres)

    def triangles_of(self, kinds, dz=None) -> np.ndarray:
        """Triangles (T, 3, 3) des parties demandées. Sol : suit le relief (dz ignoré). Eau : à son niveau + dz
        (dz = 0 pour la surface, -BED_DEPTH pour le fond)."""
        sel = np.isin(self.kind, list(kinds))
        t = self.tris[sel]
        xy = self.xy[t]
        if dz is None:
            zz = self.z[t]
        else:
            zz = np.repeat(self.level[sel][:, None], 3, axis=1) + float(dz)
        return np.concatenate([xy, zz[:, :, None]], axis=2)


def _snap(geom, grid: float):
    return shapely.set_precision(geom, grid)


def build_ground(zone: Polygon, parts: dict, height, max_area: float = 400.0, grid: float = GRID,
                 segment_max: float = SEGMENT_MAX, default_level: float = -0.3) -> Ground:
    """parts : nom -> géométrie (ou None). height(x, y) -> altitudes du sol.
    Chaque plan d'eau (polygone de la partie « eau ») prend son propre niveau : 25 cm sous le point le plus bas de son pourtour."""
    polys: list[tuple[str, Polygon]] = []
    for name in sorted(parts):
        g = parts[name]
        if g is None or g.is_empty:
            continue
        for p in (g.geoms if hasattr(g, "geoms") else [g]):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            p = _snap(p, grid)
            if p.geom_type == "Polygon" and not p.is_empty and p.area > 0:
                polys.append((name, p))
            elif p.geom_type == "MultiPolygon":
                polys.extend((name, q) for q in p.geoms if q.area > 0)
    if not polys:
        raise ValueError("aucune partie de sol à trianguler")

    zone_s = _snap(zone, grid)
    lines = [zone_s.exterior] + [r for _, p in polys for r in (p.exterior, *p.interiors)]
    noded = shapely.union_all(lines, grid_size=grid)          # nœuds à chaque croisement, doublons fusionnés
    noded = shapely.segmentize(noded, segment_max)
    parts_l = list(noded.geoms) if hasattr(noded, "geoms") else [noded]

    verts: dict[tuple[float, float], int] = {}
    seen: set[tuple[int, int]] = set()
    segs: list[tuple[int, int]] = []
    coords = sorted({(round(x, 4), round(y, 4)) for ln in parts_l for x, y in ln.coords})
    for c in coords:
        verts[c] = len(verts)
    for ln in sorted(parts_l, key=lambda g: (round(g.coords[0][0], 3), round(g.coords[0][1], 3), g.length)):
        cs = [(round(x, 4), round(y, 4)) for x, y in ln.coords]
        for a, b in zip(cs[:-1], cs[1:]):
            ia, ib = verts[a], verts[b]
            key = (min(ia, ib), max(ia, ib))
            if ia != ib and key not in seen:
                seen.add(key)
                segs.append(key)
    xy = np.array(coords, dtype=np.float64)
    result = triangle.triangulate({"vertices": xy, "segments": np.array(sorted(segs), dtype=np.int32)}, f"pa{max_area:.1f}")
    xy = np.asarray(result["vertices"], dtype=np.float64)
    tris = np.asarray(result["triangles"], dtype=np.int64)

    a, b, c = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tris = tris[np.abs(area2) > 1e-9]
    flip = (area2[np.abs(area2) > 1e-9]) < 0
    tris[flip] = tris[flip][:, ::-1]

    # classement : la partie qui contient le centre du triangle ; à défaut, la plus proche
    centers = xy[tris].mean(axis=1)
    pts = shapely.points(centers)
    tree = STRtree([p for _, p in polys])
    owner_poly = np.full(len(tris), -1, dtype=np.int64)
    qi, ti = tree.query(pts, predicate="within")
    owner_poly[qi] = ti
    for i in np.nonzero(owner_poly < 0)[0]:
        owner_poly[i] = int(tree.nearest(pts[i]))
    kind = np.array([polys[k][0] for k in owner_poly], dtype=object)

    z = np.asarray(height(xy[:, 0], xy[:, 1]), dtype=np.float64)

    # niveau de chaque plan d'eau, puis sol qui redescend en pente douce vers l'eau (pas de falaise)
    water_polys = [(k, p) for k, (name, p) in enumerate(polys) if name == WATER]
    level_of: dict[int, float] = {}
    for k, p in water_polys:
        ring = np.asarray(p.exterior.coords)
        level_of[k] = float(np.min(height(ring[:, 0], ring[:, 1]))) - WATER_DROP
    level = np.full(len(tris), np.nan)
    for k, lv in level_of.items():
        level[owner_poly == k] = lv
    if water_polys:
        # chaque plan d'eau tire le sol vers sa rive avec un poids qui décroît en douceur jusqu'à BANK_BLEND mètres ;
        # les corrections s'additionnent puis sont ramenées à un poids total de 1 : le résultat est continu partout,
        # même là où deux plans d'eau voisins se disputent le même point
        pts_all = shapely.points(xy)
        correction = np.zeros(len(xy))
        weight = np.zeros(len(xy))
        for k, p in water_polys:
            minx, miny, maxx, maxy = p.bounds
            close = np.nonzero((xy[:, 0] > minx - BANK_BLEND) & (xy[:, 0] < maxx + BANK_BLEND) &
                               (xy[:, 1] > miny - BANK_BLEND) & (xy[:, 1] < maxy + BANK_BLEND))[0]
            if len(close) == 0:
                continue
            d = shapely.distance(pts_all[close], p)
            t = np.clip(d / BANK_BLEND, 0.0, 1.0)
            w = 1.0 - t * t * (3.0 - 2.0 * t)
            target = level_of[k] + BANK_FREEBOARD
            correction[close] += w * (target - z[close])
            weight[close] += w
        z = z + correction / np.maximum(weight, 1.0)

    # arêtes de rive : une arête commune à un triangle d'eau et à un triangle qui n'en est pas
    water = kind == WATER
    owner: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for t in np.nonzero(water | (kind != WATER))[0]:
        v = tris[t]
        for p, q in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            owner.setdefault((min(p, q), max(p, q)), []).append((int(t), int(p), int(q)))
    shore = []
    for _, items in sorted(owner.items()):
        if len(items) != 2:
            continue
        (t1, p1, q1), (t2, _, _) = items
        if water[t1] != water[t2]:
            wet_t, wet = (t1, (p1, q1)) if water[t1] else (t2, (items[1][1], items[1][2]))
            shore.append((wet[0], wet[1], float(level[wet_t])))  # sens vu du triangle d'eau : l'eau est à gauche
    return Ground(xy=xy, z=z, tris=tris, kind=kind.astype(str), shore=shore, level=level)


def shore_walls(ground: Ground) -> np.ndarray:
    """Berges verticales entre le fond de l'eau et le sol, tournées vers l'eau. Renvoie (T, 3, 3)."""
    out = []
    for a, b, lv in ground.shore:
        bed = lv - BED_DEPTH
        pa, pb = ground.xy[a], ground.xy[b]
        za, zb = ground.z[a], ground.z[b]
        la, lb = (pa[0], pa[1], bed), (pb[0], pb[1], bed)
        ha, hb = (pa[0], pa[1], za), (pb[0], pb[1], zb)
        out.append((la, hb, lb))
        out.append((la, ha, hb))
    return np.array(out, dtype=np.float64).reshape(-1, 3, 3) if out else np.zeros((0, 3, 3))
