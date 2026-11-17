"""Toits à deux pentes (MeshBuilder.add_gable_prism) sur des polygones synthétiques, sans réseau."""
from __future__ import annotations

import math

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Polygon, box

from ayigba.mesh import MeshBuilder

Z0, Z1 = 2.0, 5.0
MUR, TOIT = (0.8, 0.8, 0.8), (0.6, 0.2, 0.1)


def _prisme(poly, **kw):
    mb = MeshBuilder("test")
    r = mb.add_gable_prism(poly, Z0, Z1, MUR, TOIT, **kw)
    return r, mb.triangles


def _normales(tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    return n, np.linalg.norm(n, axis=1)


def _toit_et_murs(tris):
    n, ln = _normales(tris)
    nz = n[:, 2] / ln
    return tris[nz > 0.3], tris[np.abs(nz) < 1e-6]


def rect(w=10.0, h=6.0):
    return box(-w / 2, -h / 2, w / 2, h / 2)


def test_rectangle_altitudes_et_emprise():
    p = rect()
    r, t = _prisme(p)
    assert r is not None and r > 0
    assert r == pytest.approx(math.tan(math.radians(14.0)) * 3.0, abs=1e-6)
    assert len(t) > 0
    assert t[:, :, 2].max() == pytest.approx(Z1 + r, abs=1e-6)
    assert t[:, :, 2].min() == pytest.approx(Z0, abs=1e-6)
    _, ln = _normales(t)
    assert (ln > 1e-9).all(), "triangle dégénéré"
    emprise = p.buffer(1e-6)
    assert all(emprise.contains(__import__("shapely").geometry.Point(x, y)) for x, y in t[:, :, :2].reshape(-1, 2))


def test_carre_refuse():
    r, t = _prisme(rect(6.0, 6.0))
    assert r is None and len(t) == 0


def test_formes_refusees():
    avec_trou = Polygon(rect(20, 10).exterior.coords, [rect(4, 3).exterior.coords])
    forme_l = Polygon([(0, 0), (12, 0), (12, 4), (4, 4), (4, 12), (0, 12)])
    minuscule = box(0, 0, 1.5, 2.5)
    for p in (avec_trou, forme_l, minuscule):
        r, t = _prisme(p)
        assert r is None and len(t) == 0


def test_rectangle_tourne():
    p = affinity.rotate(rect(), 30, origin=(0, 0))
    r, t = _prisme(p)
    assert r is not None and r > 0
    assert t[:, :, 2].max() == pytest.approx(Z1 + r, abs=1e-6)
    from shapely.geometry import Point
    emprise = p.buffer(1e-6)
    assert all(emprise.contains(Point(x, y)) for x, y in t[:, :, :2].reshape(-1, 2))


@pytest.mark.parametrize("angle", [0, 30])
def test_toit_etanche(angle):
    p = affinity.rotate(rect(), angle, origin=(0, 0))
    _, t = _prisme(p)
    toit, _ = _toit_et_murs(t)
    a = toit[:, :, :2]
    aire = 0.5 * np.abs((a[:, 1, 0] - a[:, 0, 0]) * (a[:, 2, 1] - a[:, 0, 1]) - (a[:, 2, 0] - a[:, 0, 0]) * (a[:, 1, 1] - a[:, 0, 1]))
    assert aire.sum() == pytest.approx(p.area, abs=1e-6)


@pytest.mark.parametrize("angle", [0, 30])
def test_murs_couvrent_chaque_arete(angle):
    p = affinity.rotate(rect(), angle, origin=(0, 0))
    _, t = _prisme(p)
    _, murs = _toit_et_murs(t)
    pts = np.asarray(p.exterior.coords)[:, :2]
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        L2 = float(ab @ ab)
        trouve = False
        for tri in murs:
            bas = tri[np.isclose(tri[:, 2], Z0, atol=1e-9)][:, :2]
            if len(bas) < 2:
                continue
            ok = True
            for q in bas:
                s = float((q - a) @ ab) / L2
                dist = np.linalg.norm(a + s * ab - q)
                if dist > 1e-6 or s < -1e-6 or s > 1 + 1e-6:
                    ok = False
            if ok:
                trouve = True
                break
        assert trouve, f"arête sans mur : {a} -> {b}"


def test_orientation_des_normales():
    p = rect()
    _, t = _prisme(p)
    n, ln = _normales(t)
    nz = n[:, 2] / ln
    toit = nz > 0.3
    assert toit.any() and (nz[toit] > 0).all()
    centre = np.array([0.0, 0.0])
    nb_murs = 0
    for tri, nn in zip(t[np.abs(nz) < 1e-6], n[np.abs(nz) < 1e-6]):
        nb_murs += 1
        c = tri[:, :2].mean(axis=0)
        assert float(nn[:2] @ (c - centre)) > 0, "mur tourné vers l'intérieur"
    assert nb_murs > 0
    # aucun triangle ne regarde vers le bas (pas de plancher)
    assert (nz > -1e-6).all()
