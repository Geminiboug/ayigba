"""Tests de l'accessibilité, de l'étape de secours, des zones, des niveaux de détail et des décors."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from test_pipeline_synthetique import (  # noqa: E402
    Ville, construire, decisions, ecrire_projet, geojson, lancer, qualite, ville_de_base)

from ayigba.access import analyse  # noqa: E402
from ayigba.geo import read_features  # noqa: E402
from ayigba.props import CATALOGUE  # noqa: E402


# ---------- A. accessibilité ----------

def anneau(cx, cy, cote=20.0, epais=1.0, ouverture=0.0):
    """Quatre murs formant un anneau carré ; ouverture (m) découpée au milieu du mur du haut."""
    h = cote / 2
    ext = box(cx - h, cy - h, cx + h, cy + h)
    interieur = box(cx - h + epais, cy - h + epais, cx + h - epais, cy + h - epais)
    forme = ext.difference(interieur)
    if ouverture > 0:
        forme = forme.difference(box(cx - ouverture / 2, cy + h - epais - 0.1, cx + ouverture / 2, cy + h + 0.1))
    return forme


ZONE = box(-50, -50, 50, 50)
ROUTE = LineString([(-50, -45), (50, -45)])


def test_zone_vide_ratio_un_sans_poche():
    r = analyse(ZONE, [], [], [LineString([(-50, 0), (50, 0)])])
    assert r.ratio == 1.0
    assert r.pockets == [] and r.wet_pockets == []


def test_cour_fermee_donne_une_poche():
    r = analyse(ZONE, [anneau(0, 0)], [], [ROUTE])
    assert len(r.pockets) == 1
    assert r.pockets[0].area == pytest.approx(18 * 18, rel=0.10)
    assert r.wet_pockets == []
    assert r.ratio < 1.0


def test_cour_avec_ouverture_de_2_m_sans_poche():
    r = analyse(ZONE, [anneau(0, 0, ouverture=2.0)], [], [ROUTE])
    assert r.pockets == []


def test_cour_avec_ouverture_trop_etroite_garde_une_poche():
    r = analyse(ZONE, [anneau(0, 0, ouverture=0.5)], [], [ROUTE])
    assert len(r.pockets) == 1


def test_ile_est_une_poche_mouillee():
    ile = box(-7.5, -7.5, 7.5, 7.5)
    eau = box(-12.5, -12.5, 12.5, 12.5).difference(ile)
    r = analyse(ZONE, [], [eau], [ROUTE])
    assert r.pockets == []
    assert len(r.wet_pockets) == 1


# ---------- B. étape de secours ----------

def ville_avec_cour() -> Ville:
    v = ville_de_base()
    cx, cy = 80, 80  # anneau de 24 m de côté, murs de 4 m, loin des routes
    v.rect(cx, cy + 10, 24, 4)
    v.rect(cx, cy - 10, 24, 4)
    v.rect(cx - 10, cy, 4, 16)
    v.rect(cx + 10, cy, 4, 16)
    return v


def test_cour_fermee_comblee_par_le_pipeline(tmp_path):
    d = construire(tmp_path, ville_avec_cour())
    bats = geojson(d / "work" / "secours" / "buildings.geojson")
    cours = [f for f in bats if f["properties"].get("raison") == "poche_fermee"]
    assert cours and all(f["properties"]["source"] == "genere" for f in cours)
    q = qualite(d)
    assert q["erreurs"] == []
    assert q["marcheur"]["part_accessible"] == 1.0
    assert any(x["action"] == "genere" and x["etape"] == "secours" for x in decisions(d))


def test_secours_desactive_laisse_la_poche(tmp_path):
    d = ecrire_projet(tmp_path / "ville-test", ville_avec_cour())
    with (d / "config.toml").open("a", encoding="utf-8") as f:
        f.write("\n[secours]\nactif = false\n")
    lancer(d)
    bats = geojson(d / "work" / "secours" / "buildings.geojson")
    assert not any(f["properties"]["source"] == "genere" for f in bats)
    assert "zone_inaccessible" in [e["genre"] for e in qualite(d)["erreurs"]]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    return construire(tmp_path_factory.mktemp("base"), ville_de_base())


def test_marquage_source_des_fichiers_de_secours(base):
    fichiers = list((base / "work" / "secours").glob("*.geojson"))
    assert fichiers
    for fic in fichiers:
        for f in geojson(fic):
            assert f["properties"].get("source") in ("osm", "genere"), (fic.name, f["properties"])


# ---------- C. zones et niveaux de détail ----------

def zones_json(d: Path) -> dict:
    return json.loads((d / "out" / "neutre" / "zones.json").read_text(encoding="utf-8"))


def triangles_npz(d: Path) -> int:
    total = 0
    for fic in (d / "work" / "optimisation" / "zones").glob("*.npz"):
        with np.load(fic) as data:
            total += sum(len(data[k]) for k in data.files
                         if k.endswith("__triangles") and not k.startswith("batiments_loin__"))
    return total


def test_zones_fichiers_et_triangles_conserves(base):
    doc = zones_json(base)
    assert doc["zones"]
    for z in doc["zones"]:
        f = base / "out" / "neutre" / z["fichier"]
        assert f.is_file() and f.read_bytes()[:4] == b"glTF"
    scene = json.loads((base / "work" / "generation" / "scene.json").read_text(encoding="utf-8"))
    attendu = 0
    for c in scene["couches"]:
        with np.load(base / "work" / "generation" / f"{c['nom']}.npz") as data:
            attendu += len(data[data.files[0]])
    somme_json = sum(c["triangles"] for z in doc["zones"] for c in z["couches"] if c["nom"] != "batiments_loin")
    assert abs(somme_json - attendu) <= 5 or abs(triangles_npz(base) - attendu) <= 5


def test_taille_de_zone_reduite_donne_plus_de_zones(tmp_path):
    ref = construire(tmp_path, ville_de_base(), "ref")
    d = ecrire_projet(tmp_path / "petit", ville_de_base())
    with (d / "config.toml").open("a", encoding="utf-8") as f:
        f.write("\n[optimisation]\ntaille_zone_m = 100\n")
    lancer(d)
    a, b = zones_json(ref), zones_json(d)
    assert len(b["zones"]) > len(a["zones"])
    for z in b["zones"]:
        x0, y0, x1, y1 = z["emprise"]
        assert x1 - x0 <= 100.0 + 1e-6 and y1 - y0 <= 100.0 + 1e-6


def test_budget_minuscule_signale_les_zones(tmp_path):
    d = ecrire_projet(tmp_path / "budget", ville_de_base())
    with (d / "config.toml").open("a", encoding="utf-8") as f:
        f.write("\n[optimisation]\nbudget_triangles = 1\n")
    lancer(d)
    fait = json.loads((d / "work" / "optimisation" / "_fait.json").read_text(encoding="utf-8"))
    assert fait["resume"]["zones_hors_budget"] >= 1
    assert any(x["action"] == "signale" and x["etape"] == "optimisation" for x in decisions(d))


def test_niveaux_de_detail_des_couches(base):
    gros = [(g, p) for g, p in read_features(base / "work" / "generation" / "buildings.geojson") if g.area >= 60]
    assert gros
    for z in zones_json(base)["zones"]:
        couches = {c["nom"]: c for c in z["couches"]}
        e = z["emprise"]
        contient_gros = any(e[0] <= g.centroid.x < e[2] and e[1] <= g.centroid.y < e[3] for g, _ in gros)
        if "batiments" in couches and contient_gros:
            assert "batiments_loin" in couches and couches["batiments_loin"]["visible"] == "loin"
        if "decors" in couches:
            assert couches["decors"]["visible"] == "pres"
        if "batiments" in couches:
            assert couches["batiments"]["visible"] == "pres"
        if "terrain" in couches:
            assert couches["terrain"]["visible"] == "toujours"


# ---------- D. décors ----------

def test_decors_valides_et_hors_batiments(base):
    fic = base / "out" / "neutre" / "decors.geojson"
    assert fic.is_file()
    items = geojson(fic)
    assert items and all(f["properties"]["type"] in CATALOGUE for f in items)
    bats = unary_union([g for g, _ in read_features(base / "work" / "generation" / "buildings.geojson")])
    for g, p in read_features(base / "work" / "generation" / "decors.geojson"):
        assert not bats.contains(g), p["id"]


def test_decors_identiques_entre_deux_pipelines(tmp_path):
    a = construire(tmp_path, ville_de_base(), "a/v")
    b = construire(tmp_path, ville_de_base(), "b/v")
    fa, fb = (x / "out" / "neutre" / "decors.geojson" for x in (a, b))
    assert fa.read_bytes() == fb.read_bytes()


def test_decors_desactives(tmp_path):
    d = ecrire_projet(tmp_path / "sans", ville_de_base())
    with (d / "config.toml").open("a", encoding="utf-8") as f:
        f.write("\n[decors]\nactif = false\n")
    lancer(d)
    assert read_features(d / "work" / "generation" / "decors.geojson") == []
    scene = json.loads((d / "work" / "generation" / "scene.json").read_text(encoding="utf-8"))
    couche = next((c for c in scene["couches"] if c["nom"] == "decors"), None)
    if couche is not None:
        with np.load(d / "work" / "generation" / "decors.npz") as data:
            assert len(data[data.files[0]]) == 0


# ---------- E. reproductibilité globale ----------

def test_exports_identiques_entre_deux_projets(tmp_path):
    a = construire(tmp_path, ville_de_base(), "a/v") / "out" / "neutre"
    b = construire(tmp_path, ville_de_base(), "b/v") / "out" / "neutre"
    for nom in ("carte.glb", "zones.json"):
        assert (a / nom).read_bytes() == (b / nom).read_bytes(), nom
    fa = sorted(p.name for p in (a / "zones").iterdir())
    assert fa == sorted(p.name for p in (b / "zones").iterdir()) and fa
    for nom in fa:
        assert (a / "zones" / nom).read_bytes() == (b / "zones" / nom).read_bytes(), nom
