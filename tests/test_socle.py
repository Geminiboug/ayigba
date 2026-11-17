"""Tests du socle : config, journal, sources, projet, repère local, GeoJSON, pipeline."""
from __future__ import annotations

import json
import sys
import types

import pytest
from shapely.geometry import Point, Polygon

from ayigba import pipeline
from ayigba.config import ConfigError, load_config
from ayigba.geo import LocalFrame, read_features, write_features
from ayigba.journal import Journal
from ayigba.project import SUBDIRS, open_context
from ayigba.sources import read_sources, register_source

BBOX = (2.372, 6.346, 2.402, 6.366)


def ecrire_config(dossier, bbox="[2.372, 6.346, 2.402, 6.366]", graine=7):
    chemin = dossier / "config.toml"
    chemin.write_text(
        '[ville]\nnom = "Cotonou"\nquartier = "Test"\npays = "Bénin"\n\n'
        f"[zone]\nbbox = {bbox}\n\n[generation]\ngraine = {graine}\n",
        encoding="utf-8",
    )
    return chemin


# 1. config

def test_config_chargement_valide(tmp_path):
    cfg = load_config(ecrire_config(tmp_path))
    assert cfg.city == "Cotonou"
    assert cfg.district == "Test"
    assert cfg.country == "Bénin"
    assert cfg.bbox == BBOX
    assert (cfg.west, cfg.south, cfg.east, cfg.north) == BBOX
    assert cfg.seed == 7


def test_config_fichier_absent(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.toml")


def test_config_bbox_a_trois_nombres(tmp_path):
    with pytest.raises(ConfigError):
        load_config(ecrire_config(tmp_path, bbox="[2.372, 6.346, 2.402]"))


def test_config_ouest_superieur_ou_egal_a_est(tmp_path):
    with pytest.raises(ConfigError):
        load_config(ecrire_config(tmp_path, bbox="[2.402, 6.346, 2.372, 6.366]"))
    with pytest.raises(ConfigError):
        load_config(ecrire_config(tmp_path, bbox="[2.372, 6.346, 2.372, 6.366]"))


def test_config_bbox_trop_grande(tmp_path):
    with pytest.raises(ConfigError):
        load_config(ecrire_config(tmp_path, bbox="[2.0, 6.346, 2.6, 6.366]"))


def test_config_digest_stable_et_sensible_a_la_graine(tmp_path):
    a = load_config(ecrire_config(tmp_path)).digest()
    b = load_config(ecrire_config(tmp_path)).digest()
    c = load_config(ecrire_config(tmp_path, graine=8)).digest()
    assert a == b
    assert a != c


# 2. journal

def lignes(chemin):
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l]


def test_journal_record_puis_flush_ecrit_une_ligne_par_decision(tmp_path):
    j = Journal(tmp_path / "logs" / "decisions.jsonl")
    j.start_stage("x")
    j.record("corrige", "way/1", "raison un")
    j.record("supprime", "way/2", "raison deux", detail=3)
    j.flush()
    ls = lignes(tmp_path / "logs" / "decisions.jsonl")
    assert len(ls) == 2
    assert ls[0]["objet"] == "way/1" and ls[0]["etape"] == "x"
    assert ls[1]["details"] == {"detail": 3}


def test_journal_action_inconnue(tmp_path):
    j = Journal(tmp_path / "d.jsonl")
    with pytest.raises(ValueError):
        j.record("inconnue", "way/1", "x")


def test_journal_start_stage_efface_seulement_son_etape(tmp_path):
    j = Journal(tmp_path / "d.jsonl")
    j.start_stage("x")
    j.record("info", "a", "r")
    j.start_stage("y")
    j.record("info", "b", "r")
    j.flush()
    j.start_stage("x")
    ls = lignes(tmp_path / "d.jsonl")
    assert [l["etape"] for l in ls] == ["y"]


def test_journal_counts_par_etape(tmp_path):
    j = Journal(tmp_path / "d.jsonl")
    j.start_stage("x")
    j.record("info", "a", "r")
    j.record("info", "b", "r")
    j.record("genere", "c", "r")
    j.start_stage("y")
    j.record("signale", "d", "r")
    assert j.counts("x") == {"info": 2, "genere": 1}
    assert j.counts("y") == {"signale": 1}
    assert j.counts() == {"info": 2, "genere": 1, "signale": 1}


# 3. sources

def source(id_, nom="N"):
    return {
        "id": id_, "nom": nom, "licence": "ODbL", "url_licence": "https://exemple.org/l",
        "attribution": "auteurs", "url_source": "https://exemple.org/s", "date_collecte": "2026-01-01",
    }


def test_sources_incomplete_refusee(tmp_path):
    s = source("a")
    del s["licence"]
    with pytest.raises(ValueError, match="licence"):
        register_source(tmp_path, s)
    assert read_sources(tmp_path) == []


def test_sources_meme_id_remplace(tmp_path):
    register_source(tmp_path, source("a", "ancien"))
    register_source(tmp_path, source("a", "nouveau"))
    items = read_sources(tmp_path)
    assert len(items) == 1
    assert items[0]["nom"] == "nouveau"


def test_sources_triees_par_id(tmp_path):
    for i in ("c", "a", "b"):
        register_source(tmp_path, source(i))
    assert [s["id"] for s in read_sources(tmp_path)] == ["a", "b", "c"]


# 4. project

def test_open_context_cree_les_sous_dossiers(tmp_path):
    ecrire_config(tmp_path)
    ctx = open_context(tmp_path)
    assert set(SUBDIRS) == {"data", "cache", "work", "out", "reports", "logs"}
    for nom in ("data", "cache", "work", "out", "reports", "logs"):
        assert (tmp_path / nom).is_dir()
    assert ctx.config.city == "Cotonou"


# 5. geo.LocalFrame

def test_repere_epsg_et_centre():
    f = LocalFrame(BBOX)
    assert f.epsg == 32631
    x, y = f.to_local((BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2)
    assert abs(float(x)) < 1e-3 and abs(float(y)) < 1e-3


def test_repere_aller_retour():
    f = LocalFrame(BBOX)
    lon, lat = 2.3871, 6.3549
    x, y = f.to_local(lon, lat)
    lon2, lat2 = f.to_wgs84(x, y)
    assert abs(float(lon2) - lon) < 1e-7
    assert abs(float(lat2) - lat) < 1e-7


def test_repere_un_centieme_de_degre_vers_l_est():
    f = LocalFrame(BBOX)
    lon0, lat0 = 2.387, 6.356
    x0, _ = f.to_local(lon0, lat0)
    x1, _ = f.to_local(lon0 + 0.01, lat0)
    assert 1100 < float(x1 - x0) < 1110


def test_repere_polygone_de_zone():
    minx, miny, maxx, maxy = LocalFrame(BBOX).zone_polygon().bounds
    assert 3300 < maxx - minx < 3330
    assert 2200 < maxy - miny < 2220


# 6. GeoJSON

def test_geojson_aller_retour(tmp_path):
    chemin = tmp_path / "f.geojson"
    pt = Point(1.23456, 2.34567)
    poly = Polygon([(0, 0), (10.12345, 0), (10.12345, 5.6789), (0, 0)])
    write_features(chemin, [(pt, {"nom": "p", "n": 1}), (poly, {"nom": "q"})])
    res = read_features(chemin)
    assert len(res) == 2
    g0, p0 = res[0]
    assert p0 == {"nom": "p", "n": 1}
    assert (g0.x, g0.y) == (1.235, 2.346)
    g1, p1 = res[1]
    assert p1 == {"nom": "q"}
    assert g1.geom_type == "Polygon"
    # le recalage sur la grille peut changer le sommet de départ et le sens : on compare la forme
    assert g1.equals(Polygon([(0.0, 0.0), (10.123, 0.0), (10.123, 5.679), (0.0, 0.0)]))
    assert all(round(v, 3) == v for c in g1.exterior.coords for v in c)


# 7. pipeline

@pytest.fixture
def fausses_etapes(monkeypatch):
    appels: list[str] = []
    stages = []
    for nom in ("a", "b", "c"):
        mod = types.ModuleType(f"faux_{nom}")

        def run(ctx, _nom=nom):
            appels.append(_nom)
            return {"n": 1}

        mod.run = run
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
        stages.append((nom, mod.__name__))
    monkeypatch.setattr(pipeline, "STAGES", stages)
    monkeypatch.setattr(pipeline, "STAGE_NAMES", ["a", "b", "c"])
    return appels


def rien(*_):
    return None


def test_pipeline_premiere_execution_dans_l_ordre(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    res = pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    assert fausses_etapes == ["a", "b", "c"]
    assert res == {"a": {"n": 1}, "b": {"n": 1}, "c": {"n": 1}}


def test_pipeline_reprise_sans_reexecution(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    fausses_etapes.clear()
    res = pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    assert fausses_etapes == []
    assert res == {"a": {"n": 1}, "b": {"n": 1}, "c": {"n": 1}}


def test_pipeline_force_refait_tout(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    fausses_etapes.clear()
    pipeline.run_pipeline(open_context(tmp_path), force=True, echo=rien)
    assert fausses_etapes == ["a", "b", "c"]


def test_pipeline_only_avec_force_ne_lance_que_cette_etape(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    fausses_etapes.clear()
    res = pipeline.run_pipeline(open_context(tmp_path), only="b", force=True, echo=rien)
    assert fausses_etapes == ["b"]
    assert list(res) == ["b"]


def test_pipeline_until_s_arrete_apres_l_etape(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    res = pipeline.run_pipeline(open_context(tmp_path), until="a", echo=rien)
    assert fausses_etapes == ["a"]
    assert list(res) == ["a"]


def test_pipeline_nom_inconnu(tmp_path, fausses_etapes):
    ecrire_config(tmp_path)
    ctx = open_context(tmp_path)
    with pytest.raises(pipeline.StageError):
        pipeline.run_pipeline(ctx, until="zzz", echo=rien)
    with pytest.raises(pipeline.StageError):
        pipeline.run_pipeline(ctx, only="zzz", echo=rien)
    assert fausses_etapes == []


def test_pipeline_etape_en_echec(tmp_path, fausses_etapes, monkeypatch):
    def casse(ctx):
        raise RuntimeError("boum")

    monkeypatch.setattr(sys.modules["faux_b"], "run", casse)
    ecrire_config(tmp_path)
    ctx = open_context(tmp_path)
    with pytest.raises(pipeline.StageError) as exc:
        pipeline.run_pipeline(ctx, echo=rien)
    assert "b" in str(exc.value) and "boum" in str(exc.value)
    assert (tmp_path / "work" / "a" / "_fait.json").is_file()
    assert not (tmp_path / "work" / "b" / "_fait.json").exists()
    assert fausses_etapes == ["a"]


def test_pipeline_changement_de_graine_refait_tout(tmp_path, fausses_etapes):
    ecrire_config(tmp_path, graine=7)
    pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    fausses_etapes.clear()
    ecrire_config(tmp_path, graine=8)
    pipeline.run_pipeline(open_context(tmp_path), echo=rien)
    assert fausses_etapes == ["a", "b", "c"]
