"""Tests de l'historique des générations."""
import json

import pytest

from ayigba.history import (
    compare,
    compare_files,
    list_snapshots,
    load_metrics,
    restore,
    snapshot,
)
from ayigba.project import Project

QUALITE = {
    "erreurs": ["e1", "e2"],
    "avertissements": ["a1"],
    "batiments": 12,
    "routes": 3,
    "routes_km": 1.5,
    "triangles": 1000,
    "elements_par_source": {"genere": 4},
    "marcheur": {"part_accessible": 0.9, "poches_inaccessibles": 2},
}


def faux_projet(tmp_path):
    p = Project(tmp_path / "ville")
    p.ensure_dirs()
    neutre = p.out / "neutre"
    neutre.mkdir(parents=True)
    (neutre / "carte.glb").write_bytes(b"glb-v1")
    (neutre / "manifeste.json").write_text('{"v": 1}', encoding="utf-8")
    (p.reports / "qualite.json").write_text(json.dumps(QUALITE), encoding="utf-8")
    return p


def test_numerotation(tmp_path):
    p = faux_projet(tmp_path)
    d1 = snapshot(p, "premier")
    d2 = snapshot(p, "second")
    assert d1.name == "001_premier"
    assert d2.name == "002_second"
    assert [s["numero"] for s in list_snapshots(p)] == [1, 2]


def test_copie_fidele(tmp_path):
    p = faux_projet(tmp_path)
    d = snapshot(p, "x")
    assert (d / "neutre" / "carte.glb").read_bytes() == b"glb-v1"
    assert (d / "qualite.json").exists()
    meta = json.loads((d / "instantane.json").read_text(encoding="utf-8"))
    assert meta["numero"] == 1
    assert set(meta["empreintes"]) == {"carte.glb", "manifeste.json"}


def test_etiquette_nettoyee(tmp_path):
    p = faux_projet(tmp_path)
    assert snapshot(p, "test / v2 !").name == "001_test-v2"
    assert snapshot(p, "").name == "002_sans-nom"


def test_sans_neutre(tmp_path):
    p = Project(tmp_path / "vide")
    p.ensure_dirs()
    with pytest.raises(RuntimeError):
        snapshot(p)


def test_load_metrics(tmp_path):
    p = faux_projet(tmp_path)
    m = load_metrics(None, p)
    assert m["erreurs"] == 2 and m["avertissements"] == 1
    assert m["part_accessible"] == 0.9 and m["elements_generes"] == 4
    assert m["hauteurs_estimees"] is None
    d = snapshot(p, "a")
    assert load_metrics(d, p) == m


def test_compare():
    avant = {"erreurs": 1, "batiments": 10, "routes_km": 2.0, "triangles": 5, "routes": None}
    apres = {"erreurs": 3, "batiments": 22, "routes_km": 1.5, "triangles": 5, "routes": 4}
    t = compare(avant, apres)
    assert "| Mesure | Avant | Après | Écart |" in t
    assert "| batiments | 10 | 22 | +12 |" in t
    assert "| routes_km | 2.0 | 1.5 | -0.5 |" in t
    assert "| triangles | 5 | 5 | = |" in t
    assert "| routes | ? | 4 | ? |" in t
    assert "Régression : le nombre d'erreurs augmente." in t
    assert "Pas de régression sur les erreurs." in compare(apres, avant)


def test_compare_files(tmp_path):
    p = faux_projet(tmp_path)
    d1 = snapshot(p, "a")
    (p.out / "neutre" / "carte.glb").write_bytes(b"glb-v2")
    (p.out / "neutre" / "nouveau.txt").write_text("n", encoding="utf-8")
    (p.out / "neutre" / "manifeste.json").unlink()
    d2 = snapshot(p, "b")
    r = compare_files(d1, d2)
    assert r["differents"] == ["carte.glb"]
    assert r["seulement_avant"] == ["manifeste.json"]
    assert r["seulement_apres"] == ["nouveau.txt"]
    assert r["identiques"] == []
    assert compare_files(d1, d1)["identiques"] == ["carte.glb", "manifeste.json"]


def test_restore(tmp_path):
    p = faux_projet(tmp_path)
    snapshot(p, "base")
    (p.out / "neutre" / "carte.glb").write_bytes(b"glb-v2")
    (p.out / "neutre" / "extra.txt").write_text("e", encoding="utf-8")
    (p.reports / "qualite.json").write_text("{}", encoding="utf-8")
    restore(p, 1)
    assert (p.out / "neutre" / "carte.glb").read_bytes() == b"glb-v1"
    assert not (p.out / "neutre" / "extra.txt").exists()
    assert load_metrics(None, p)["batiments"] == 12
    snaps = list_snapshots(p)
    assert snaps[-1]["etiquette"] == "avant-retour"
    assert (snaps[-1]["dossier"] / "neutre" / "carte.glb").read_bytes() == b"glb-v2"


def test_restore_inconnu(tmp_path):
    p = faux_projet(tmp_path)
    with pytest.raises(LookupError):
        restore(p, 7)
