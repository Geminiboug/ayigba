"""Tests de la détection de bâtiments (ayigba.detection) et de son usage dans le pipeline, sans réseau."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).parent))
from test_pipeline_synthetique import (  # noqa: E402
    FRAME, ecrire_projet, geojson, lancer, qualite, ville_de_base)
from test_terrain import z_terrain  # noqa: E402

from ayigba import batiments25d, dem  # noqa: E402
from ayigba.detection import detecter  # noqa: E402

ZONE = box(-500, -500, 500, 500)
PAS = 2.0


def vers_local(x, y):
    return np.asarray(x) - 1000.0, np.asarray(y) - 1000.0


def grille(taches, n=400):
    """Grille 2.5D de n x n pixels (800 m), origine UTM (600, 1400) -> locaux (-400, 400). taches : (xmin, ymin, xmax, ymax) locaux."""
    pres = np.zeros((n, n), dtype=np.float32)
    for x0, y0, x1, y1 in taches:
        j0, j1 = int(round((x0 + 400) / PAS)), int(round((x1 + 400) / PAS))
        i0, i1 = int(round((400 - y1) / PAS)), int(round((400 - y0) / PAS))
        pres[i0:i1, j0:j1] = 1.0
    return {"hauteur": pres * 7, "presence": pres, "x0": 600.0, "y0": 1400.0, "pas": PAS, "epsg": 32631}


# ---------- A. detecter() ----------

def test_tache_de_80_m2_devient_polygone_rectangulaire():
    res = detecter(grille([(0, 0, 10, 8)]), vers_local, ZONE, [])
    assert len(res) == 1
    g = res[0]
    assert g.area == pytest.approx(80.0, rel=0.25)
    assert g.area / g.minimum_rotated_rectangle.area > 0.9


def test_batiment_deja_connu_non_rendu():
    res = detecter(grille([(0, 0, 10, 8)]), vers_local, ZONE, [box(-1, -1, 11, 9)])
    assert res == []


def test_zone_interdite_retire_la_tache():
    res = detecter(grille([(0, 0, 10, 8)]), vers_local, ZONE, [], interdit=box(-20, -20, 20, 20))
    assert res == []


def test_bruit_et_tache_enorme_ignores():
    assert detecter(grille([(0, 0, 2, 1)]), vers_local, ZONE, []) == []
    assert detecter(grille([(-100, -100, -30, -28)]), vers_local, ZONE, []) == []  # 70 x 72 = 5040 m2


def test_deterministe_et_sans_chevauchement():
    g = grille([(0, 0, 10, 8), (30, 0, 44, 12), (-60, 20, -48, 30), (-60, -40, -30, -20)])
    a = detecter(g, vers_local, ZONE, [])
    b = detecter(g, vers_local, ZONE, [])
    assert len(a) == 4
    assert [x.wkt for x in a] == [x.wkt for x in b]
    for i, p in enumerate(a):
        for q in a[i + 1:]:
            assert p.intersection(q).area <= 0.5


# ---------- B. pipeline ----------

TACHE = (-116, -50, -104, -40)   # 12 x 10 m, loin des routes, sans bâtiment OSM
OSM14 = (24, -55, 36, -45)       # bâtiment OSM 14 (centre (30, -50), 12 x 10)


def donnees_25d(partout=None):
    """Grille 2.5D en EPSG du projet couvrant toute la zone."""
    e0, n0 = FRAME._e0, FRAME._n0
    n = 400
    x0, y0 = e0 - 400.0, n0 + 400.0
    d = {"x0": x0, "y0": y0, "pas": PAS, "epsg": FRAME.epsg}
    if partout is not None:
        d["presence"] = np.full((n, n), partout[0], dtype=np.float32)
        d["hauteur"] = np.full((n, n), partout[1], dtype=np.float32)
        return d
    pres = np.zeros((n, n), dtype=np.float32)
    haut = np.zeros((n, n), dtype=np.float32)
    for (xa, ya, xb, yb), h in ((OSM14, 12.0), (TACHE, 7.0)):
        j0, j1 = int(round((xa + 400) / PAS)), int(round((xb + 400) / PAS))
        i0, i1 = int(round((400 - yb) / PAS)), int(round((400 - ya) / PAS))
        pres[i0:i1, j0:j1] = 1.0
        haut[i0:i1, j0:j1] = h
    d["presence"], d["hauteur"] = pres, haut
    return d


def projet(tmp_path, nom="ville-test", extra="", donnees=None, avec_dem=False):
    d = ecrire_projet(tmp_path / nom, ville_de_base())
    batiments25d.enregistrer(d / "cache" / "batiments25d.npz", donnees or donnees_25d())
    if avec_dem:
        ouest, nord, pas = 2.3790, 6.3540, 0.0001
        m, n = int(round(0.006 / pas)), int(round(0.005 / pas))
        dem.enregistrer(d / "cache" / "dem_copernicus.npz",
                        {"altitudes": np.full((n, m), 10.0, dtype=np.float32), "ouest": ouest, "nord": nord, "pas": pas})
    if extra:
        with (d / "config.toml").open("a", encoding="utf-8") as f:
            f.write(extra)
    return d


def props(d, etape):
    return [f["properties"] for f in geojson(d / "work" / etape / "buildings.geojson")]


@pytest.fixture(scope="module")
def ville25d(tmp_path_factory):
    d = projet(tmp_path_factory.mktemp("v25d"))
    lancer(d)
    return d


def test_batiment_detecte_dans_secours(ville25d):
    det = [f for f in geojson(ville25d / "work" / "secours" / "buildings.geojson")
           if f["properties"].get("source") == "google_25d"]
    assert det
    from shapely.geometry import shape
    c = shape(det[0]["geometry"]).centroid
    assert np.hypot(c.x - (-110), c.y - (-45)) < 8


def test_hauteur_mesuree_sur_batiment_osm(ville25d):
    p14 = [p for p in props(ville25d, "generation") if p["id"].endswith("/14")][0]
    assert p14["hauteur"] == pytest.approx(12.0, abs=0.5)
    assert p14["hauteur_source"] == "google_25d"
    p13 = [p for p in props(ville25d, "generation") if p["id"].endswith("/13")][0]
    assert p13["hauteur_source"] == "osm" and p13["hauteur"] == 9.0


def test_qualite_avec_25d(ville25d):
    q = qualite(ville25d)
    assert q["erreurs"] == []
    assert q["hauteurs_par_source"]["google_25d"] >= 1


def test_25d_desactive(tmp_path):
    d = projet(tmp_path, extra="\n[batiments25d]\nactif = false\n")
    lancer(d)
    assert not any(p.get("source") == "google_25d" for p in props(d, "secours"))
    assert not any(p.get("hauteur_source") == "google_25d" for p in props(d, "generation"))


def test_detection_desactivee_garde_les_hauteurs(tmp_path):
    d = projet(tmp_path, extra="\n[batiments25d]\ndetecter = false\n")
    lancer(d)
    assert not any(p.get("source") == "google_25d" for p in props(d, "secours"))
    assert any(p.get("hauteur_source") == "google_25d" for p in props(d, "generation"))


def test_glb_identique_entre_deux_executions(tmp_path):
    a, b = projet(tmp_path, "a/ville-test"), projet(tmp_path, "b/ville-test")
    lancer(a)
    lancer(b)
    glb = lambda p: (p / "out" / "neutre" / "carte.glb").read_bytes()
    assert glb(a) == glb(b)


# ---------- C. sol nu ----------

def centre_du_sol(d):
    from ayigba.mesh import load_mesh
    tris, _ = load_mesh(d / "work" / "generation" / "terrain.npz")
    c = tris.mean(axis=1)
    loin = (np.abs(c[:, 0]) < 100) & (np.abs(c[:, 1]) < 80)
    assert loin.any()
    return tris[loin][:, :, 2]


def test_sol_nu_abaisse_le_sol(tmp_path):
    d = projet(tmp_path, donnees=donnees_25d((0.5, 4.0)), avec_dem=True)
    lancer(d)
    assert np.abs(centre_du_sol(d) - 8.0).max() < 0.3


def test_sol_nu_desactive_garde_l_altitude(tmp_path):
    d = projet(tmp_path, donnees=donnees_25d((0.5, 4.0)), avec_dem=True, extra="\n[relief]\nsol_nu = false\n")
    lancer(d)
    assert np.abs(centre_du_sol(d) - 10.0).max() < 0.3
