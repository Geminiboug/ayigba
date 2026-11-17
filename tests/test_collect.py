"""Tests de l'étape de collecte (aucun accès réseau)."""
import json
import urllib.error

import pytest

from ayigba.project import open_context
from ayigba.sources import read_sources
from ayigba.stages import collect

REPONSE = json.dumps({"elements": [
    {"type": "node", "id": 1}, {"type": "way", "id": 2}, {"type": "way", "id": 3}, {"type": "relation", "id": 4},
]}).encode()


def faire_ctx(tmp_path, offline=False):
    d = tmp_path / "ville-test"
    d.mkdir()
    (d / "config.toml").write_text(
        '[ville]\nnom = "Test"\n[zone]\nbbox = [2.372, 6.346, 2.402, 6.366]\n[generation]\ngraine = 1\n',
        encoding="utf-8")
    ctx = open_context(d, offline=offline)
    ctx.journal.start_stage("collecte")
    return ctx


def test_ordre_bbox():
    q = collect.build_query((2.372, 6.346, 2.402, 6.366))
    assert '(6.346000,2.372000,6.366000,2.402000)' in q
    assert q == collect.build_query((2.372, 6.346, 2.402, 6.366))


def test_telechargement(tmp_path, monkeypatch):
    ctx = faire_ctx(tmp_path)
    monkeypatch.setattr(collect, "fetch", lambda q: (REPONSE, "https://exemple/api"))
    res = collect.run(ctx)
    assert res == {"elements": 4, "noeuds": 1, "chemins": 2, "relations": 1, "depuis_cache": False}
    assert (ctx.project.cache / "osm_overpass.json").is_file()
    meta = json.loads((ctx.project.cache / "osm_overpass.meta.json").read_text(encoding="utf-8"))
    assert meta["point_acces"] == "https://exemple/api" and meta["elements"] == 4
    src = read_sources(ctx.project.data)
    assert src[0]["id"] == "osm" and src[0]["elements"] == 4


def test_deuxieme_appel_cache(tmp_path, monkeypatch):
    ctx = faire_ctx(tmp_path)
    monkeypatch.setattr(collect, "fetch", lambda q: (REPONSE, "https://exemple/api"))
    collect.run(ctx)

    def interdit(q):
        raise AssertionError("réseau appelé")
    monkeypatch.setattr(collect, "fetch", interdit)
    res = collect.run(ctx)
    assert res["depuis_cache"] is True and res["elements"] == 4


def test_hors_ligne_sans_cache(tmp_path):
    ctx = faire_ctx(tmp_path, offline=True)
    with pytest.raises(RuntimeError, match="Mode hors ligne"):
        collect.run(ctx)


def test_reponse_sans_elements(tmp_path, monkeypatch):
    ctx = faire_ctx(tmp_path)
    monkeypatch.setattr(collect, "fetch", lambda q: (b'{"elements": []}', "https://exemple/api"))
    with pytest.raises(RuntimeError):
        collect.run(ctx)
    assert not list(ctx.project.cache.glob("osm_overpass*"))


class FausseReponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


def test_fetch_reessaie(monkeypatch):
    appels, pauses = [], []

    def opener(req, timeout=None):
        appels.append(req.full_url)
        if len(appels) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "trop", {}, None)
        return FausseReponse(b"ok")

    octets, url = collect.fetch("q", endpoints=["https://a"], opener=opener, sleep=pauses.append)
    assert octets == b"ok" and url == "https://a"
    assert pauses == [5]


def test_fetch_echec_total():
    def opener(req, timeout=None):
        raise urllib.error.URLError("panne")

    pauses = []
    with pytest.raises(RuntimeError):
        collect.fetch("q", endpoints=["https://a", "https://b"], opener=opener, sleep=pauses.append)
    assert pauses == [5, 15, 5, 15]
