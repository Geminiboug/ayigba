"""Tests des petits décors urbains."""
import math
import random

import numpy as np
import pytest

from ayigba import props
from ayigba.props import CATALOGUE, _box, emprise, place

BUDGETS = {"arbre": 40, "palmier": 40, "poteau_electrique": 30, "lampadaire": 30,
           "etal": 60, "panneau": 20, "tas_dechets": 30}
GRAINES = range(12)


def _tout(morceaux):
    return np.concatenate([t for t, _ in morceaux])


def test_catalogue_complet():
    assert set(CATALOGUE) == set(BUDGETS)


@pytest.mark.parametrize("nom", sorted(BUDGETS))
def test_decor(nom):
    for graine in GRAINES:
        morceaux = CATALOGUE[nom](random.Random(graine))
        tris = _tout(morceaux)
        assert tris.ndim == 3 and tris.shape[1:] == (3, 3)
        assert np.isfinite(tris).all()
        assert 0 < len(tris) <= BUDGETS[nom]
        assert -0.001 <= tris[..., 2].min() <= 0.05
        assert np.hypot(tris[..., 0], tris[..., 1]).max() <= emprise(nom) + 1.5
        for t, couleur in morceaux:
            assert len(couleur) == 3 and all(0.0 <= c <= 1.0 for c in couleur)
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            assert (np.linalg.norm(n, axis=1) > 1e-9).all()
        autre = _tout(CATALOGUE[nom](random.Random(graine)))
        assert np.array_equal(tris, autre)


def test_box():
    t = _box(1.0, 2.0, 0.0, 1.5, 2.0, 0.5)
    assert t.shape == (10, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    haut = np.isclose(t[..., 2], 1.5).all(axis=1)
    assert haut.sum() == 2
    assert np.isclose(np.linalg.norm(n[haut], axis=1).sum() / 2, 2.0 * 0.5)
    assert (n[haut][:, 2] > 0).all()
    centre = np.array([1.0, 2.0])
    for tri, normale in zip(t[~haut], n[~haut]):
        milieu = tri[:, :2].mean(axis=0)
        assert np.dot(normale[:2], milieu - centre) > 0


def test_box_tournee():
    t = _box(0, 0, 0, 1, 2.0, 1.0, angle=math.pi / 4)
    haut = np.isclose(t[..., 2], 1.0).all(axis=1)
    n = np.cross(t[haut][:, 1] - t[haut][:, 0], t[haut][:, 2] - t[haut][:, 0])
    assert np.isclose(np.linalg.norm(n, axis=1).sum() / 2, 2.0)


def test_place():
    tri = np.array([[[1.0, 0.0, 0.5], [2.0, 0.0, 0.5], [1.0, 1.0, 0.5]]])
    res = place([(tri, (0.1, 0.2, 0.3))], 10.0, 5.0, math.pi / 2)
    t, couleur = res[0]
    attendu = np.array([[[10.0, 6.0, 0.5], [10.0, 7.0, 0.5], [9.0, 6.0, 0.5]]])
    assert np.allclose(t, attendu)
    assert couleur == (0.1, 0.2, 0.3)
    assert np.allclose(tri[0, 0], [1.0, 0.0, 0.5])
