"""Construction de maillages à partir de polygones (repère local : x est, y nord, z haut, en mètres)."""
from __future__ import annotations

import hashlib
import random

import mapbox_earcut as earcut
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def rng_for(seed: int, key: str) -> random.Random:
    """Générateur aléatoire propre à un élément : même graine + même identifiant = mêmes tirages."""
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def triangulate(poly: Polygon) -> np.ndarray:
    """Triangles (T, 3, 2) d'un polygone avec trous, orientés dans le sens direct (face vers le haut)."""
    poly = orient(poly, 1.0)
    rings = [np.asarray(poly.exterior.coords)[:-1, :2]] + [np.asarray(r.coords)[:-1, :2] for r in poly.interiors]
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return np.zeros((0, 3, 2))
    verts = np.vstack(rings).astype(np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    idx = earcut.triangulate_float64(verts, ends).reshape(-1, 3)
    tris = verts[idx]
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    area2 = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    flip = area2 < 0
    tris[flip] = tris[flip][:, ::-1]
    return tris[np.abs(area2) > 1e-9]


class MeshBuilder:
    """Accumule des triangles colorés. Chaque triangle a sa propre normale (arêtes vives)."""

    def __init__(self, name: str):
        self.name = name
        self._tris: list[np.ndarray] = []
        self._colors: list[np.ndarray] = []

    def _add(self, tris: np.ndarray, color) -> None:
        if len(tris):
            self._tris.append(np.asarray(tris, dtype=np.float64))
            self._colors.append(np.tile(np.asarray(color, dtype=np.float32), (len(tris), 1)))

    def add_flat(self, poly: Polygon, z: float, color) -> None:
        """Face horizontale tournée vers le haut, à l'altitude z."""
        t2 = triangulate(poly)
        if len(t2):
            self._add(np.concatenate([t2, np.full((len(t2), 3, 1), float(z))], axis=2), color)

    def add_flat_down(self, poly: Polygon, z: float, color) -> None:
        """Face horizontale tournée vers le bas (dessous d'une dalle), à l'altitude z."""
        t2 = triangulate(poly)
        if len(t2):
            self._add(np.concatenate([t2[:, ::-1], np.full((len(t2), 3, 1), float(z))], axis=2), color)

    def add_walls(self, poly: Polygon, z0: float, z1: float, color) -> None:
        """Murs verticaux le long de tous les contours du polygone, tournés vers l'extérieur de la matière."""
        poly = orient(poly, 1.0)
        quads = []
        for ring in [poly.exterior, *poly.interiors]:
            c = np.asarray(ring.coords)[:, :2]
            a, b = c[:-1], c[1:]
            keep = np.linalg.norm(b - a, axis=1) > 1e-6
            a, b = a[keep], b[keep]
            n = len(a)
            if n == 0:
                continue
            a0 = np.column_stack([a, np.full(n, z0)])
            b0 = np.column_stack([b, np.full(n, z0)])
            a1 = np.column_stack([a, np.full(n, z1)])
            b1 = np.column_stack([b, np.full(n, z1)])
            quads.append(np.stack([a0, b0, b1], axis=1))
            quads.append(np.stack([a0, b1, a1], axis=1))
        if quads:
            self._add(np.concatenate(quads), color)

    def add_prism(self, poly: Polygon, z0: float, z1: float, wall_color, top_color) -> None:
        self.add_walls(poly, z0, z1, wall_color)
        self.add_flat(poly, z1, top_color)

    def add_gable_prism(self, poly: Polygon, z0: float, z1: float, wall_color, roof_color, pitch_deg: float = 14.0,
                        min_rectangularity: float = 0.90, min_aspect: float = 1.2, max_rise: float = 1.8) -> float | None:
        """Bâtiment à toit à deux pentes. Retourne la hauteur du faîte au-dessus de z1, ou None si la forme ne s'y prête pas
        (rien n'est alors ajouté : l'appelant fait un toit plat).

        Le toit épouse exactement l'emprise (aucun débord sur la rue) : le polygone est coupé par la ligne de faîte, chaque
        moitié est triangulée à plat puis relevée selon la hauteur, et les murs suivent le toit (pignons compris).
        Forme acceptée : sans trou, presque rectangulaire, plus longue que large (le faîte suit la longueur).
        """
        if poly.is_empty or len(poly.interiors) or poly.area < 4.0:
            return None
        rect = poly.minimum_rotated_rectangle
        if rect.is_empty or rect.geom_type != "Polygon" or poly.area / rect.area < min_rectangularity:
            return None
        c = np.asarray(rect.exterior.coords)[:4]
        e1, e2 = c[1] - c[0], c[2] - c[1]
        l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
        long_, short = max(l1, l2), min(l1, l2)
        if short < 2.5 or long_ / short < min_aspect:
            return None
        u = (e1 if l1 >= l2 else e2) / long_          # direction du faîte
        n = np.array([-u[1], u[0]])                    # normale au faîte
        center = np.asarray(rect.centroid.coords)[0]
        half = short / 2.0
        rise = min(np.tan(np.radians(pitch_deg)) * half, max_rise)

        def perp(p):
            return (np.asarray(p)[..., :2] - center) @ n

        def top_at(p):
            return z1 + rise * np.clip(1.0 - np.abs(perp(p)) / half, 0.0, 1.0)

        from shapely.geometry import LineString
        from shapely.ops import split
        ridge = LineString([tuple(center - u * (long_ + 5.0)), tuple(center + u * (long_ + 5.0))])
        halves = [g for g in split(poly, ridge).geoms if g.geom_type == "Polygon" and g.area > 1e-6]
        if len(halves) != 2:
            return None
        # murs : chaque arête du contour est coupée là où elle traverse le faîte, le haut suit la hauteur du toit
        pts = np.asarray(orient(poly, 1.0).exterior.coords)[:, :2]
        quads = []
        for a, b in zip(pts[:-1], pts[1:]):
            if np.linalg.norm(b - a) < 1e-6:
                continue
            pa, pb = float(perp(a)), float(perp(b))
            segs = [(a, b)]
            if pa * pb < 0:
                m = a + (b - a) * (pa / (pa - pb))
                segs = [(a, m), (m, b)]
            for p, q in segs:
                p0, q0 = np.array([p[0], p[1], z0]), np.array([q[0], q[1], z0])
                p1, q1 = np.array([p[0], p[1], float(top_at(p))]), np.array([q[0], q[1], float(top_at(q))])
                quads.append(np.stack([p0, q0, q1]))
                quads.append(np.stack([p0, q1, p1]))
        self._add(np.stack(quads), wall_color)
        for h in halves:
            t2 = triangulate(h)
            if len(t2):
                z = top_at(t2.reshape(-1, 2)).reshape(len(t2), 3, 1)
                self._add(np.concatenate([t2, z], axis=2), roof_color)
        return float(rise)

    @property
    def triangles(self) -> np.ndarray:
        return np.concatenate(self._tris) if self._tris else np.zeros((0, 3, 3))

    @property
    def colors(self) -> np.ndarray:
        return np.concatenate(self._colors) if self._colors else np.zeros((0, 3), dtype=np.float32)

    def save(self, path) -> int:
        np.savez_compressed(path, triangles=self.triangles.astype(np.float32), colors=self.colors)
        return int(len(self.triangles))


def load_mesh(path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path) as data:
        return data["triangles"].astype(np.float64), data["colors"].astype(np.float32)
