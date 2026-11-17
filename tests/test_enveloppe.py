"""Enveloppe basse du modèle d'altitude : retire les bosses de bâtiments sans écraser un vrai relief."""
import numpy as np

from ayigba.dem import Altitudes, _enveloppe_basse
from ayigba.geo import LocalFrame

BBOX = (2.372, 6.346, 2.402, 6.366)


def _dem(grille):
    return {"altitudes": grille.astype(np.float32), "ouest": 2.37, "nord": 6.37, "pas": 0.00027777777777777778}


def test_enveloppe_rayon_zero_inchangee():
    g = np.arange(25, dtype=float).reshape(5, 5)
    assert np.array_equal(_enveloppe_basse(g, 0), g)


def test_enveloppe_retire_un_pic_isole():
    g = np.full((9, 9), 3.0)
    g[4, 4] = 14.0                       # un immeuble vu comme un pic de 11 m
    assert _enveloppe_basse(g, 1).max() == 3.0


def test_enveloppe_garde_un_plateau_large():
    g = np.full((15, 15), 2.0)
    g[3:12, 3:12] = 10.0                 # un plateau de 9 x 9 pixels : un vrai relief
    out = _enveloppe_basse(g, 1)
    assert out[7, 7] == 10.0             # le coeur du plateau reste à 10 m
    assert out[0, 0] == 2.0


def test_enveloppe_ne_depasse_jamais_le_modele():
    rng = np.random.default_rng(3)
    g = rng.uniform(0, 12, size=(20, 20))
    assert (_enveloppe_basse(g, 1) <= g + 1e-12).all()


def test_altitudes_avec_enveloppe_abaisse_le_pic():
    g = np.full((40, 40), 4.0)
    g[20, 20] = 15.0
    frame = LocalFrame(BBOX)
    brut = Altitudes(_dem(g), frame, lissage=0.0, enveloppe=0)
    propre = Altitudes(_dem(g), frame, lissage=0.0, enveloppe=1)
    assert brut.stats()["max"] == 15.0
    assert propre.stats()["max"] == 4.0
    assert brut.empreinte() != propre.empreinte()
