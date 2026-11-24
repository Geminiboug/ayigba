"""Visionneuse : un fichier HTML autonome, avec les données de la carte et les défauts des bots."""
import json
import re

from ayigba import voir
from test_pipeline_synthetique import construire, ville_de_base


def _donnees(html: str) -> dict:
    m = re.search(r"const D=(\{.*?\});\nconst \$=", html, re.S)
    assert m, "données introuvables dans le HTML"
    return json.loads(m.group(1))


def test_voir_ecrit_un_html_autonome(tmp_path):
    dossier = construire(tmp_path, ville_de_base())
    bots = tmp_path / "bots.json"
    bots.write_text(json.dumps({"defauts": [{"genre": "bloque", "route": "navmesh:3", "x": 12.0, "y": 1.5, "z": -40.0}]}), encoding="utf-8")
    f = voir.ecrire(dossier, [bots])
    html = f.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html   # aucune ressource externe
    d = _donnees(html)
    assert len(d["batiments"]) > 0 and len(d["routes"]) > 0
    assert d["chiffres"]["batiments"] == len(d["batiments"])
    b = [x for x in d["defauts"] if x["genre"] == "bot_bloque"]
    assert len(b) == 1 and b[0]["x"] == 12.0 and b[0]["y"] == 40.0     # (x, z) Godot -> (x, -z) local
    assert d["emprise"][0] < d["emprise"][2] and d["emprise"][1] < d["emprise"][3]


def test_voir_sans_resultat(tmp_path):
    import pytest
    from test_pipeline_synthetique import ecrire_projet
    dossier = ecrire_projet(tmp_path / "vide", ville_de_base())
    with pytest.raises(LookupError):
        voir.ecrire(dossier)


def test_points_controle(tmp_path):
    from ayigba import points_controle
    dossier = construire(tmp_path, ville_de_base())
    f = points_controle.ecrire(dossier)
    pts = json.loads(f.read_text(encoding="utf-8"))
    assert pts and all({"id", "genre", "x", "y", "z", "mode"} <= set(p) for p in pts)
    assert {p["mode"] for p in pts} <= {"sol", "toit"}
    assert any(p["mode"] == "toit" for p in pts)
