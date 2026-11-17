"""Tests du contrôle des détections (ayigba.controle) : indicateurs sur données synthétiques, échantillon, exclusion. Sans réseau."""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest
from shapely import STRtree
from shapely.geometry import LineString, Polygon, box

sys.path.insert(0, str(Path(__file__).parent))
from test_detection import donnees_25d, projet  # noqa: E402
from test_pipeline_synthetique import decisions, lancer  # noqa: E402

from ayigba import batiments25d, cli, controle  # noqa: E402
from ayigba.controle import (  # noqa: E402
    allongement, cle_suspicion, densite_locale, drapeaux, ecrire_exclusions, echantillon, hauteur_et_presence,
    proche_de, rectangularite, score)


def ok(**kw):
    base = dict(aire=100.0, allong=1.5, rectang=0.95, hauteur=6.0, presence=0.95, densite=0.3, eau=False, route=False)
    base.update(kw)
    return drapeaux(**base)


# ---------- indicateurs ----------

def test_aucun_indice_pour_un_batiment_normal():
    assert ok() == []
    assert score(ok()) == 0


def test_aire_tres_petite_et_tres_grande():
    assert ok(aire=15.0) == ["aire_tres_petite"]
    assert ok(aire=20.0) == []                       # seuil strict
    assert ok(aire=801.0) == ["aire_tres_grande"]
    assert ok(aire=800.0) == []


def test_allongement_mesure_sur_le_rectangle_minimal():
    assert allongement(box(0, 0, 10, 10)) == pytest.approx(1.0)
    assert allongement(box(0, 0, 30, 4)) == pytest.approx(7.5)
    from shapely import affinity
    tourne = affinity.rotate(box(0, 0, 30, 4), 37, origin=(0, 0))
    assert allongement(tourne) == pytest.approx(7.5, rel=1e-3)   # invariant par rotation
    assert ok(allong=7.5) == ["allonge"]
    assert ok(allong=6.0) == []


def test_hauteur_incoherente_et_absente():
    assert ok(hauteur=2.0) == ["hauteur_incoherente"]
    assert ok(hauteur=2.4) == []
    assert ok(hauteur=41.0) == ["hauteur_incoherente"]
    assert ok(hauteur=40.0) == []
    assert ok(hauteur=None) == ["hauteur_absente"]


def test_densite_locale_dans_un_rayon_de_50_m():
    zone = box(-500, -500, 500, 500)
    cible = box(-5, -5, 5, 5)
    # le disque de 50 m (7854 m2) est rempli : un grand bloc le recouvre entièrement
    plein = [cible, box(-60, -60, 60, 60)]
    assert densite_locale(cible, STRtree(plein), plein, zone) == pytest.approx(1.0, abs=0.01)
    # seule la cible : 100 / 7854
    seul = [cible]
    assert densite_locale(cible, STRtree(seul), seul, zone) == pytest.approx(100 / 7854, rel=0.05)
    # un bâtiment à plus de 50 m ne compte pas
    loin = [cible, box(80, 80, 90, 90)]
    assert densite_locale(cible, STRtree(loin), loin, zone) == pytest.approx(100 / 7854, rel=0.05)
    assert ok(densite=0.9) == ["zone_tres_dense"]
    assert ok(densite=0.85) == []


def test_densite_limitee_a_la_zone():
    cible = box(-5, -5, 5, 5)
    zone = box(-10, -10, 10, 10)          # le disque est rogné par la zone : la part se mesure sur la zone seule
    assert densite_locale(cible, STRtree([cible]), [cible], zone) == pytest.approx(100 / 400, rel=0.01)


def test_proximite_eau_et_route():
    b = box(0, 0, 10, 10)
    eau = box(10.5, -50, 60, 50)
    route = LineString([(-50, -8), (50, -8)]).buffer(3.0)    # bord de chaussée à 5 m
    assert proche_de(b, eau)
    assert not proche_de(b, route)
    assert proche_de(b, route, distance=5.0)
    assert not proche_de(b, None)
    assert ok(eau=True) == ["proche_eau"]
    assert ok(route=True) == ["proche_route"]


def test_rectangularite():
    assert rectangularite(box(0, 0, 8, 5)) == pytest.approx(1.0)
    en_l = Polygon([(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10)])
    assert rectangularite(en_l) == pytest.approx(0.51, abs=0.02)
    assert ok(rectang=0.45) == ["faible_rectangularite"]
    assert ok(rectang=0.5) == []


def test_presence_et_hauteur_mesurees_sous_l_emprise():
    n = 50
    pres = np.zeros((n, n), dtype=np.float32)
    haut = np.zeros((n, n), dtype=np.float32)
    pres[10:20, 10:20] = 0.95
    haut[10:20, 10:20] = 7.0
    pres[10:20, 15:20] = 0.55                      # moitié du bâtiment à présence faible
    mesure = batiments25d.Hauteurs({"hauteur": haut, "presence": pres, "x0": 0.0, "y0": 100.0, "pas": 2.0})
    # pixels (10..19, 10..19) -> x 20..40, y 60..80
    h, p = hauteur_et_presence(mesure, box(20, 60, 40, 80))
    assert h == pytest.approx(7.0)
    assert p == pytest.approx((0.95 * 50 + 0.55 * 50) / 100, abs=0.01)
    assert ok(presence=0.52) == ["presence_faible"]
    assert ok(presence=0.55) == []
    # emprise tombant sur du vide : pas de hauteur
    h2, p2 = hauteur_et_presence(mesure, box(60, 20, 70, 30))
    assert h2 is None and p2 == 0.0


def test_score_est_la_somme_des_poids():
    d = ok(aire=10.0, eau=True, presence=0.5)
    assert d == ["aire_tres_petite", "proche_eau", "presence_faible"]
    assert score(d) == controle.POIDS["aire_tres_petite"] + controle.POIDS["proche_eau"] + controle.POIDS["presence_faible"]


# ---------- échantillon ----------

def entrees(n=100):
    out = []
    for i in range(n):
        e = {"id": f"g25d/{i:03d}", "score": i % 7, "presence_moyenne": 0.9 - (i % 5) * 0.03, "rectangularite": 0.9, "x": 0.0, "y": 0.0}
        out.append(e)
    return out


def test_echantillon_stratifie_reproductible_sans_doublon():
    e = entrees()
    a, b = echantillon(e), echantillon(e)
    assert [x["id"] for x in a] == [x["id"] for x in b]
    assert len(a) == 24
    assert len({x["id"] for x in a}) == 24
    for strate in ("suspect", "hasard", "sur"):
        assert sum(x["strate"] == strate for x in a) == 8
    suspects = [x for x in a if x["strate"] == "suspect"]
    surs = [x for x in a if x["strate"] == "sur"]
    assert min(x["score"] for x in suspects) >= max(x["score"] for x in surs)
    assert max(x["score"] for x in surs) == 0
    assert suspects[0]["score"] == 6


def test_echantillon_depend_de_la_graine_et_de_l_ordre_d_entree_non():
    e = entrees()
    hasard = lambda s: [x["id"] for x in echantillon(e, graine=s) if x["strate"] == "hasard"]
    assert hasard(1) != hasard(2)
    assert [x["id"] for x in echantillon(list(reversed(e))) if x["strate"] == "hasard"] == hasard(controle.GRAINE_ECHANTILLON)


def test_echantillon_petit_jeu():
    a = echantillon(entrees(9))
    assert len({x["id"] for x in a}) == len(a) == 9
    assert echantillon([]) == []


def test_ordre_de_suspicion_departage_les_scores_egaux():
    a = {"id": "a", "score": 3, "presence_moyenne": 0.9, "rectangularite": 0.9}
    b = {"id": "b", "score": 3, "presence_moyenne": 0.6, "rectangularite": 0.9}
    assert sorted([a, b], key=cle_suspicion)[0]["id"] == "b"


# ---------- exclusion dans config.toml ----------

BASE = '[ville]\nnom = "T"\n\n[zone]\nbbox = [2.38, 6.35, 2.384, 6.353]\n'


def test_ecrire_exclusions_cree_la_section(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BASE, encoding="utf-8")
    assert ecrire_exclusions(p, ["g25d/b", "g25d/a"]) == ["g25d/a", "g25d/b"]
    assert tomllib.loads(p.read_text(encoding="utf-8"))["batiments25d"]["exclure"] == ["g25d/a", "g25d/b"]


def test_ecrire_exclusions_fusionne_et_garde_le_reste(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BASE + '\n[batiments25d]\nactif = true\nexclure = [\n    "g25d/a",\n]\n\n[secours]\nactif = false\n', encoding="utf-8")
    ecrire_exclusions(p, ["g25d/c", "g25d/a"])
    cfg = tomllib.loads(p.read_text(encoding="utf-8"))
    assert cfg["batiments25d"] == {"actif": True, "exclure": ["g25d/a", "g25d/c"]}
    assert cfg["secours"] == {"actif": False}
    assert cfg["ville"]["nom"] == "T"


def test_ecrire_exclusions_section_sans_liste(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(BASE + "\n[batiments25d]\nactif = true\n", encoding="utf-8")
    ecrire_exclusions(p, ["g25d/a"])
    assert tomllib.loads(p.read_text(encoding="utf-8"))["batiments25d"] == {"actif": True, "exclure": ["g25d/a"]}


# ---------- de bout en bout, sur le projet synthétique ----------

def test_controle_de_bout_en_bout_et_exclusion(tmp_path):
    pytest.importorskip("matplotlib")
    d = projet(tmp_path)
    lancer(d)
    avant = (d / "config.toml").read_text(encoding="utf-8")
    code = cli.main(["controler-detections", str(d)])
    assert code == 0
    assert (d / "config.toml").read_text(encoding="utf-8") == avant      # rien n'est exclu sans demande
    rap = json.loads((d / "reports" / "controle_detections.json").read_text(encoding="utf-8"))
    assert "pas des" in rap["avertissement"] or "pas leur exactitude" in rap["avertissement"]
    assert rap["batiments_par_source"].get("google_25d", 0) >= 1
    assert rap["resume"]["nombre"] == len(rap["detections"]) >= 1
    det = rap["detections"][0]
    assert 6.34 < det["lat"] < 6.36 and 2.37 < det["lon"] < 2.39
    assert det["hauteur_m"] == pytest.approx(7.0)
    assert (d / "reports" / "controle_detections.png").stat().st_size > 1000
    assert list((d / "reports" / "controle_detections").glob("*.png"))

    # exclusion demandée : écrite dans la config, puis journalisée à la génération
    seuil = min(e["score"] for e in rap["detections"])
    assert cli.main(["controler-detections", str(d), "--sans-images", "--exclure-score", str(seuil)]) == 0
    exclure = tomllib.loads((d / "config.toml").read_text(encoding="utf-8"))["batiments25d"]["exclure"]
    assert exclure == sorted(e["id"] for e in rap["detections"])
    lancer(d)
    ligne = [x for x in decisions(d) if x["etape"] == "secours" and "exclu" in x["raison"]]
    assert ligne and ligne[0]["details"]["nombre"] == len(exclure)
    apres = [f for f in json.loads((d / "work" / "secours" / "buildings.geojson").read_text(encoding="utf-8"))["features"]
             if f["properties"].get("source") == "google_25d"]
    assert apres == []


def test_sans_grille_2_5d_message_clair(tmp_path):
    d = projet(tmp_path)
    lancer(d)
    (d / "cache" / "batiments25d.npz").unlink()
    assert cli.main(["controler-detections", str(d)]) == 1
