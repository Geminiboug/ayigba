"""Repère local en mètres et lecture/écriture GeoJSON.

Repère local : origine au centre de la zone, x vers l'est, y vers le nord, en mètres
(projection UTM de la zone, choisie d'après la longitude). Tous les fichiers de work/ sont dans ce repère.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry


class LocalFrame:
    def __init__(self, bbox: tuple[float, float, float, float]):
        west, south, east, north = bbox
        self.bbox = bbox
        self.lon0 = (west + east) / 2.0
        self.lat0 = (south + north) / 2.0
        zone = int((self.lon0 + 180.0) // 6) + 1
        self.epsg = (32600 if self.lat0 >= 0 else 32700) + zone
        self._fwd = Transformer.from_crs(4326, self.epsg, always_xy=True)
        self._inv = Transformer.from_crs(self.epsg, 4326, always_xy=True)
        self._e0, self._n0 = self._fwd.transform(self.lon0, self.lat0)

    def to_local(self, lon, lat):
        e, n = self._fwd.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
        return e - self._e0, n - self._n0

    def to_wgs84(self, x, y):
        return self._inv.transform(np.asarray(x, dtype=float) + self._e0, np.asarray(y, dtype=float) + self._n0)

    def zone_polygon(self):
        """Rectangle de la zone dans le repère local (enveloppe des quatre coins projetés)."""
        west, south, east, north = self.bbox
        xs, ys = self.to_local([west, east, east, west], [south, south, north, north])
        return box(float(np.max(xs[[0, 3]])), float(np.max(ys[[0, 1]])), float(np.min(xs[[1, 2]])), float(np.min(ys[[2, 3]])))


def round_geom(geom: BaseGeometry, ndigits: int = 3) -> dict:
    """Géométrie en dictionnaire GeoJSON, coordonnées arrondies (fichiers stables et plus petits)."""

    def _r(obj):
        if isinstance(obj, (list, tuple)):
            return [_r(v) for v in obj]
        return round(float(obj), ndigits)

    m = mapping(geom)
    return {"type": m["type"], "coordinates": _r(m["coordinates"])} if "coordinates" in m else {"type": m["type"], "geometries": [round_geom(g, ndigits) for g in geom.geoms]}


def write_features(path: Path, features: list[tuple[BaseGeometry, dict]], ndigits: int = 3, extra: dict | None = None) -> None:
    """Écrit une liste (géométrie, propriétés) en GeoJSON, dans l'ordre donné."""
    doc = {"type": "FeatureCollection"}
    if extra:
        doc.update(extra)
    doc["features"] = []
    for geom, props in features:
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            # arrondir des sommets peut rendre un polygone invalide : on le recale proprement sur la grille
            geom = shapely.set_precision(geom, 10.0 ** -ndigits)
            if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
                continue
        doc["features"].append({"type": "Feature", "properties": props, "geometry": round_geom(geom, ndigits)})
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def read_features(path: Path) -> list[tuple[BaseGeometry, dict]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for f in doc.get("features", []):
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = shapely.make_valid(geom)
        out.append((geom, f.get("properties") or {}))
    return out
