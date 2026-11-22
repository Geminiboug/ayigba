"""Tests de ayigba.style : chargement de la configuration, préréglages, champ de cohérence, teinte et mesure de cohérence.

Aucun réseau : la configuration est un vrai `Config` construit avec une section `options` en JSON.
"""
from __future__ import annotations

import json
import math
import random

import numpy as np
import pytest

from ayigba.config import Config
from ayigba.style import (
    AFRIQUE_DE_L_OUEST,
    PRESETS,
    Teinte,
    champ,
    charger,
    coherence_voisins,
    preset_pour_pays,
)


def _config(**sections) -> Config:
    """Configuration minimale : seules les sections facultatives passées en arguments sont présentes."""
    return Config(
        city="Ville de test",
        district="",
        country="",
        bbox=(0.0, 0.0, 0.01, 0.01),
        seed=0,
        style="defaut",
        engine="neutre",
        options=json.dumps(sections, sort_keys=True, ensure_ascii=False),
    )


def _composantes(style):
    """Toutes les couleurs d'un style, sols et murs et toits compris."""
    couleurs = [style.sol, style.laterite, style.asphalte, style.piste, style.trottoir, style.eau, style.fond, style.peinture]
    couleurs += list(style.murs) + list(style.toits)
    return couleurs


# ------------------------------------------------------------------------------------------------------ 1. charger

def test_charger_sans_section_style_donne_afrique_de_l_ouest():
    s = charger(_config())
    assert s.nom == "afrique_de_l_ouest"
    assert s.coherence == 0.0
    assert s == AFRIQUE_DE_L_OUEST


def test_charger_preset_inconnu_leve_erreur_avec_les_noms_disponibles():
    with pytest.raises(ValueError) as exc:
        charger(_config(style={"preset": "atlantide"}))
    message = str(exc.value)
    for nom in ("afrique_de_l_ouest", "europe_temperee", "andes", "generique"):
        assert nom in message


def test_charger_couleur_hexadecimale_convertie():
    s = charger(_config(style={"sol": "#ff8000"}))
    assert s.sol == pytest.approx((1.0, 0.502, 0.0), abs=0.001)


@pytest.mark.parametrize("couleur", [[0.1, 0.2], [2, 0, 0]])
def test_charger_couleur_invalide_leve_erreur(couleur):
    with pytest.raises(ValueError):
        charger(_config(style={"sol": couleur}))


def test_charger_coherence_hors_bornes_leve_erreur():
    with pytest.raises(ValueError):
        charger(_config(style={"coherence": 1.5}))


def test_charger_taille_quartier_trop_petite_leve_erreur():
    with pytest.raises(ValueError):
        charger(_config(style={"taille_quartier_m": 5}))


def test_charger_murs_vide_leve_erreur():
    with pytest.raises(ValueError):
        charger(_config(style={"murs": []}))


# ------------------------------------------------------------------------------------------- 2. preset_pour_pays

@pytest.mark.parametrize(
    "code, attendu",
    [
        ("bj", "afrique_de_l_ouest"),
        ("FR", "europe_temperee"),
        ("fr", "europe_temperee"),
        ("pe", "andes"),
        ("", "generique"),
        (None, "generique"),
        ("zz", "generique"),
    ],
)
def test_preset_pour_pays(code, attendu):
    assert preset_pour_pays(code) == attendu


# ------------------------------------------------------------------------------------------------------ 3. champ

def test_champ_deterministe():
    f1 = champ(seed=3, taille_m=150.0)
    f2 = champ(seed=3, taille_m=150.0)
    rng = random.Random(5)
    for _ in range(200):
        x, y = rng.uniform(-3000, 3000), rng.uniform(-3000, 3000)
        assert f1(x, y) == f1(x, y)
        assert f1(x, y) == f2(x, y)


def test_champ_valeurs_dans_zero_un():
    f = champ(seed=12, taille_m=150.0)
    rng = random.Random(0)
    valeurs = [f(rng.uniform(-5000, 5000), rng.uniform(-5000, 5000)) for _ in range(2000)]
    assert min(valeurs) >= 0.0
    assert max(valeurs) <= 1.0


def test_champ_lisse_a_1_m_et_contrasté_a_2000_m():
    f = champ(seed=7, taille_m=150.0)
    rng = random.Random(11)
    proche, loin = [], []
    for _ in range(500):
        x, y = rng.uniform(0, 20000), rng.uniform(0, 20000)
        theta = rng.uniform(0, 2 * math.pi)
        proche.append(abs(f(x, y) - f(x + math.cos(theta), y + math.sin(theta))))
        phi = rng.uniform(0, 2 * math.pi)
        loin.append(abs(f(x, y) - f(x + 2000 * math.cos(phi), y + 2000 * math.sin(phi))))
    moyenne_proche = float(np.mean(proche))
    moyenne_loin = float(np.mean(loin))
    assert moyenne_proche < 0.05
    assert moyenne_proche * 5 < moyenne_loin


def test_champ_graines_differentes_donnent_des_champs_differents():
    f1 = champ(seed=1, taille_m=150.0)
    f2 = champ(seed=2, taille_m=150.0)
    rng = random.Random(9)
    points = [(rng.uniform(0, 5000), rng.uniform(0, 5000)) for _ in range(100)]
    differents = sum(1 for x, y in points if abs(f1(x, y) - f2(x, y)) > 1e-9)
    assert differents > 90


# ------------------------------------------------------------------------------------------------- 4. Teinte.choisir

def test_teinte_coherence_zero_reproduit_l_ancien_tirage():
    s = charger(_config())
    assert s.coherence == 0.0
    for graine in (0, 1, 42, 2024):
        t = Teinte(s, graine)
        rng = random.Random(graine)
        ref = random.Random(graine)
        for x, y in [(0.0, 0.0), (100.0, 50.0), (900.0, -300.0), (12.5, 7.5)]:
            attendu = (ref.choice(s.murs), ref.choice(s.toits))
            assert t.choisir(x, y, rng) == attendu


def test_teinte_coherence_voisins_meme_teinte_ou_teinte_adjacente_a_5_m():
    """À cohérence 1, chaque bâtiment prend la dominante de SON endroit. Le champ est découpé en intervalles : deux voisins de part
    et d'autre d'une frontière d'intervalle prennent deux teintes différentes, mais ADJACENTES dans la palette triée par
    luminance (donc proches). On vérifie les deux propriétés : même teinte dans la grande majorité des cas, jamais plus d'un cran
    d'écart sinon."""
    s = charger(_config(style={"coherence": 1}))
    t = Teinte(s, 7)
    murs, toits = s.murs_tries(), s.toits_tries()
    origine = random.Random(2)
    memes_murs = memes_toits = 0
    for i in range(200):
        x, y = origine.uniform(0, 5000), origine.uniform(0, 5000)
        theta = origine.uniform(0, 2 * math.pi)
        mur1, toit1 = t.choisir(x, y, random.Random(i))
        mur2, toit2 = t.choisir(x + 5 * math.cos(theta), y + 5 * math.sin(theta), random.Random(10_000 + i))
        memes_murs += mur1 == mur2
        memes_toits += toit1 == toit2
        assert abs(murs.index(mur1) - murs.index(mur2)) <= 1
        assert abs(toits.index(toit1) - toits.index(toit2)) <= 1
    assert memes_murs >= 170
    assert memes_toits >= 170


def test_teinte_coherence_intermediaire_pioche_dans_la_palette():
    s = charger(_config(style={"coherence": 0.65}))
    t = Teinte(s, 99)
    rng = random.Random(4)
    for _ in range(300):
        x, y = rng.uniform(0, 5000), rng.uniform(0, 5000)
        mur, toit = t.choisir(x, y, rng)
        assert mur in s.murs
        assert toit in s.toits


def test_teinte_reproductible_a_graine_egale():
    s = charger(_config(style={"coherence": 0.65}))

    def tirages():
        t = Teinte(s, 123)
        rng = random.Random(55)
        return [t.choisir(float(i * 37 % 900), float(i * 91 % 700), rng) for i in range(100)]

    assert tirages() == tirages()


# --------------------------------------------------------------------------------------- 5. coherence_voisins

def test_coherence_voisins_blocs_de_couleur_donne_rapport_inferieur_a_un_demi():
    xs, ys = np.meshgrid(np.arange(20) * 10.0, np.arange(20) * 10.0)
    points = np.column_stack([xs.ravel(), ys.ravel()])
    lignes, colonnes = np.divmod(np.arange(400), 20)
    bloc = (lignes // 10) * 2 + (colonnes // 10)
    palette = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 0.0]])
    couleurs = palette[bloc]
    res = coherence_voisins(points, couleurs)
    assert res["n"] == 400
    assert res["rapport"] is not None
    assert res["rapport"] < 0.5


def test_coherence_voisins_couleurs_aleatoires_donne_rapport_proche_de_un():
    rng = np.random.default_rng(3)
    xs, ys = np.meshgrid(np.arange(20) * 10.0, np.arange(20) * 10.0)
    points = np.column_stack([xs.ravel(), ys.ravel()])
    couleurs = rng.random((400, 3))
    res = coherence_voisins(points, couleurs)
    assert res["rapport"] is not None
    assert 0.85 <= res["rapport"] <= 1.15


def test_coherence_voisins_moins_de_20_points_renvoie_none():
    rng = np.random.default_rng(1)
    points = rng.random((19, 2)) * 100
    couleurs = rng.random((19, 3))
    res = coherence_voisins(points, couleurs)
    assert res["rapport"] is None
    assert res["voisins"] is None


# ------------------------------------------------------------------------------------ 6. préréglages intégrés

@pytest.mark.parametrize("nom", sorted(PRESETS))
def test_preset_est_coherent(nom):
    s = PRESETS[nom]
    assert s.nom == nom
    assert len(s.murs) > 0
    assert len(s.toits) > 0
    for couleur in _composantes(s):
        assert len(couleur) == 3
        assert all(0.0 <= c <= 1.0 for c in couleur), (nom, couleur)
    for poids in (s.etages_petit, s.etages_moyen, s.etages_grand):
        assert all(w >= 0 for w in poids), (nom, poids)
        assert any(w > 0 for w in poids), (nom, poids)


@pytest.mark.parametrize("nom", sorted(PRESETS))
def test_murs_tries_croissent_en_luminance(nom):
    lum = [0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] for c in PRESETS[nom].murs_tries()]
    assert lum == sorted(lum)
    assert len(lum) == len(PRESETS[nom].murs)


# ------------------------------------------------------------------------------------------------- 5. classes de bâtiments
def test_classe_batiment():
    from ayigba.style import classe_batiment
    assert classe_batiment("mosque") == "religieux" and classe_batiment("warehouse") == "industriel"
    assert classe_batiment("school") == "institution" and classe_batiment("retail") == "commerce"
    assert classe_batiment("yes") == "residentiel" and classe_batiment(None) == "residentiel"


def test_classes_actives_restreignent_les_couleurs_et_restent_reproductibles():
    import random
    from dataclasses import replace
    from ayigba.style import AFRIQUE_DE_L_OUEST, Teinte, _luminance
    s = replace(AFRIQUE_DE_L_OUEST, classes=True, coherence=0.5)
    t = Teinte(s, 7)
    claires = s.murs_tries()[len(s.murs) // 2:]
    for i in range(30):
        mur, _ = t.choisir(10.0 * i, 5.0, random.Random(i), "school")
        assert mur in claires
        assert t.choisir(3.0, 4.0, random.Random(i), "mosque") == t.choisir(3.0, 4.0, random.Random(i), "mosque")
    assert min(_luminance(t.choisir(1.0, 1.0, random.Random(i), "mosque")[0]) for i in range(30)) >= _luminance(s.murs_tries()[-2])
    # désactivées : même résultat qu'avant, quel que soit le genre
    t0 = Teinte(AFRIQUE_DE_L_OUEST, 7)
    assert t0.choisir(1.0, 1.0, random.Random(3), "school") == t0.choisir(1.0, 1.0, random.Random(3), "yes")


def test_genre_par_poi_pour_les_batiments_yes():
    from shapely.geometry import Point, box
    from ayigba.stages.generate import _genres_par_batiment
    bats = [(box(0, 0, 10, 10), {"id": "a", "type": "yes"}), (box(20, 0, 30, 10), {"id": "b", "type": "house"}), (box(40, 0, 50, 10), {"id": "c", "type": "yes"})]
    pois = [(Point(5, 5), {"genre": "shop", "type": "supermarket"}), (Point(25, 5), {"genre": "amenity", "type": "school"}), (Point(45, 5), {"genre": "arbre", "type": "tree"})]
    assert _genres_par_batiment(bats, pois) == {"a": "supermarket"}
