"""Tests du maillage du sol (ayigba.terrain) et du relief dans le pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).parent))
from test_pipeline_synthetique import (  # noqa: E402
    FRAME, ecrire_projet, geojson, lancer, qualite, ville_de_base)

from ayigba import dem  # noqa: E402
from ayigba.mesh import load_mesh  # noqa: E402
from ayigba.terrain import (  # noqa: E402
    BANK_FREEBOARD, BED_DEPTH, WATER_DROP, build_ground, shore_walls)

ZONE = box(-100, -100, 100, 100)


def hauteur(x, y):
    return 0.02 * np.asarray(x, dtype=float) + 3.0


def aires_signees(g):
    a, b, c = (g.xy[g.tris[:, i]] for i in range(3))
    return 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def aire_par_genre(g, genre):
    return float(aires_signees(g)[g.kind == genre].sum())


def sommets_de(g, genre):
    return {tuple(np.round(p, 4)) for p in g.xy[g.tris[g.kind == genre]].reshape(-1, 2)}


def ground_avec_eau(parts_eau, pente=None):
    eau = parts_eau
    terre = ZONE.difference(eau)
    return build_ground(ZONE, {"terre": terre, "eau": eau}, hauteur)


# ---------- A. build_ground ----------

def test_une_seule_partie_terre_couvre_toute_la_zone():
    g = build_ground(ZONE, {"terre": ZONE}, hauteur)
    assert set(g.kind) == {"terre"}
    a = aires_signees(g)
    assert (a > 0).all()
    assert a.sum() == pytest.approx(40000.0, abs=0.5)
    assert np.allclose(g.z, 0.02 * g.xy[:, 0] + 3.0, atol=1e-3)
    tri = g.triangles_of(["terre"])
    assert np.allclose(tri[:, :, 2], 0.02 * tri[:, :, 0] + 3.0, atol=1e-3)


def test_deux_parties_voisines_sans_chevauchement_et_sommets_partages():
    chaussee = box(-100, -4, 100, 4)
    terre = ZONE.difference(chaussee)
    g = build_ground(ZONE, {"revetu": chaussee, "terre": terre}, hauteur)
    assert aire_par_genre(g, "revetu") == pytest.approx(chaussee.area, abs=0.5)
    assert aire_par_genre(g, "terre") == pytest.approx(terre.area, abs=0.5)
    assert aires_signees(g).sum() == pytest.approx(ZONE.area, abs=0.5)
    communs = sommets_de(g, "revetu") & sommets_de(g, "terre")
    assert len(communs) >= 4


def test_plan_d_eau_a_son_propre_niveau():
    eau = box(-10, -10, 10, 10)
    g = ground_avec_eau(eau)
    assert "eau" in set(g.kind)
    attendu = float(hauteur(np.array([-10.0]), np.array([0.0]))[0]) - WATER_DROP
    surf = g.triangles_of(["eau"], dz=0.0)
    assert np.allclose(surf[:, :, 2], attendu, atol=1e-3)
    fond = g.triangles_of(["eau"], dz=-BED_DEPTH)
    assert np.allclose(fond[:, :, 2], attendu - BED_DEPTH, atol=1e-3)
    # sommets du pourtour de l'eau : sol a niveau + franc-bord
    bord = eau.exterior
    from shapely.geometry import Point
    sur_bord = [i for i, p in enumerate(g.xy) if bord.distance(Point(p)) < 1e-6]
    assert sur_bord
    assert np.allclose(g.z[sur_bord], attendu + BANK_FREEBOARD, atol=0.01)


def test_berges_verticales_jusqu_au_fond():
    g = ground_avec_eau(box(-10, -10, 10, 10))
    m = shore_walls(g)
    assert m.ndim == 3 and m.shape[1:] == (3, 3) and len(m) > 0
    n = np.cross(m[:, 1] - m[:, 0], m[:, 2] - m[:, 0])
    n = n / np.linalg.norm(n, axis=1, keepdims=True)
    assert np.abs(n[:, 2]).max() < 1e-6
    niveau = float(np.nanmin(g.level))
    assert m[:, :, 2].min() == pytest.approx(niveau - BED_DEPTH, abs=1e-6)


def test_determinisme():
    chaussee = box(-100, -4, 100, 4)
    eau = box(30, 30, 50, 50)
    parts = {"revetu": chaussee, "eau": eau, "terre": ZONE.difference(chaussee).difference(eau)}
    a = build_ground(ZONE, parts, hauteur)
    b = build_ground(ZONE, parts, hauteur)
    assert np.array_equal(a.xy, b.xy)
    assert np.array_equal(a.tris, b.tris)
    assert np.array_equal(a.z, b.z)
    assert np.array_equal(a.kind, b.kind)


def test_deux_plans_d_eau_voisins_sol_continu_sur_pente():
    e1, e2 = box(-35, -10, -15, 10), box(15, -10, 35, 10)
    plan = lambda x, y: 0.2 * np.asarray(x, dtype=float)
    terre = ZONE.difference(e1).difference(e2)
    g = build_ground(ZONE, {"terre": terre, "eau": e1.union(e2)}, plan)
    t = g.tris[g.kind == "terre"]
    pentes = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        p, q = t[:, i], t[:, j]
        d = np.linalg.norm(g.xy[p] - g.xy[q], axis=1)
        ok = d > 0.5
        pentes.append(np.degrees(np.arctan(np.abs(g.z[p] - g.z[q])[ok] / d[ok])))
    assert np.concatenate(pentes).max() <= 30.0


def test_aucune_partie_leve_valueerror():
    with pytest.raises(ValueError):
        build_ground(ZONE, {}, hauteur)
    with pytest.raises(ValueError):
        build_ground(ZONE, {"terre": None, "eau": None}, hauteur)


# ---------- B. relief dans le pipeline ----------

def fabriquer_dem(dossier: Path):
    """Plan incliné de 0 m (ouest) à 6 m (est), couvrant la ville avec une marge."""
    ouest, est, nord, sud, pas = 2.3790, 2.3850, 6.3540, 6.3490, 0.0001
    m = int(round((est - ouest) / pas))
    n = int(round((nord - sud) / pas))
    lon = ouest + (np.arange(m) + 0.5) * pas
    ligne = 6.0 * (lon - ouest) / (est - ouest)
    grille = np.tile(ligne, (n, 1)).astype(np.float32)
    dem.enregistrer(dossier / "cache" / "dem_copernicus.npz",
                    {"altitudes": grille, "ouest": ouest, "nord": nord, "pas": pas})
    return ouest, est


def plan_attendu(x, y, ouest=2.3790, est=2.3850):
    lon, _ = FRAME.to_wgs84(x, y)
    return 6.0 * (np.asarray(lon, dtype=float) - ouest) / (est - ouest)


def z_terrain(d: Path) -> np.ndarray:
    tris, _ = load_mesh(d / "work" / "generation" / "terrain.npz")
    return tris[:, :, 2]


def info_relief(d: Path) -> dict:
    return json.loads((d / "work" / "relief" / "info.json").read_text(encoding="utf-8"))


def projet_avec_dem(tmp_path, nom="ville-test", extra=""):
    d = ecrire_projet(tmp_path / nom, ville_de_base())
    fabriquer_dem(d)
    if extra:
        with (d / "config.toml").open("a", encoding="utf-8") as f:
            f.write(extra)
    return d


def test_sans_cache_d_altitude_terrain_plat(tmp_path):
    d = ecrire_projet(tmp_path / "ville-test", ville_de_base())
    assert not (d / "cache" / "dem_copernicus.npz").exists()
    lancer(d)
    assert info_relief(d)["relief"] == "plat"
    assert np.abs(z_terrain(d)).max() < 1e-6


def test_avec_cache_d_altitude_relief_applique(tmp_path):
    d = projet_avec_dem(tmp_path)
    lancer(d)
    assert info_relief(d)["relief"] == "copernicus_glo30"
    z = z_terrain(d)
    assert z.max() - z.min() > 1.0
    assert qualite(d)["erreurs"] == []
    for f in geojson(d / "work" / "generation" / "buildings.geojson"):
        p = f["properties"]
        assert "base" in p and "sommet" in p
        assert p["sommet"] - p["base"] > p["hauteur"]


def test_relief_identique_octet_pour_octet(tmp_path):
    a = projet_avec_dem(tmp_path, "a/ville-test")
    b = projet_avec_dem(tmp_path, "b/ville-test")
    lancer(a)
    lancer(b)
    glb = lambda p: (p / "out" / "neutre" / "carte.glb").read_bytes()
    assert glb(a) == glb(b)


def test_relief_desactive_terrain_plat(tmp_path):
    d = projet_avec_dem(tmp_path, extra="\n[relief]\nactif = false\n")
    lancer(d)
    assert np.abs(z_terrain(d) - z_terrain(d).flat[0]).max() < 1e-6


def test_routes_locales_ont_trois_valeurs_coherentes_avec_le_plan(tmp_path):
    d = projet_avec_dem(tmp_path, extra="\n[relief]\nenveloppe = 0\nlissage = 0\n")
    lancer(d)
    doc = json.loads((d / "out" / "neutre" / "routes_local.json").read_text(encoding="utf-8"))
    pts = [p for r in doc["routes"] for p in r["points"]]
    assert pts and all(len(p) == 3 for p in pts)
    for x, y, z in pts:
        assert z == pytest.approx(float(plan_attendu(x, y)), abs=0.05)
    assert max(p[2] for p in pts) - min(p[2] for p in pts) > 1.0  # le plan monte bien vers l'est
