"""Tests du module batiments25d. Aucun accès réseau : fonctions injectées et GeoTIFF fabriqués."""
import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import box

from ayigba import batiments25d as B
from ayigba.project import open_context
from ayigba.sources import read_sources

PREF = "gs://open-buildings-temporal-data/v1/geotiffs/1"
BASE = "https://storage.googleapis.com/open-buildings-temporal-data/v1/geotiffs/1"
BBOX = (2.372, 6.346, 2.402, 6.366)


def _centre_utm():
    return Transformer.from_crs(4326, 32631, always_xy=True).transform(2.387, 6.356)


def _tif(chemin, x0, y0, taille=400, carre=None):
    """Tuile taille x taille de 0,5 m, coin nord-ouest (x0, y0). carre = (i0, i1, j0, j1, hauteur)."""
    d = np.zeros((3, taille, taille), dtype="float32")
    if carre:
        i0, i1, j0, j1, h = carre
        d[0, i0:i1, j0:j1] = 1
        d[1, i0:i1, j0:j1] = h
        d[2, i0:i1, j0:j1] = 1
    with rasterio.open(chemin, "w", driver="GTiff", height=taille, width=taille, count=3, dtype="float32",
                       crs="EPSG:32631", transform=from_origin(x0, y0, 0.5, 0.5)) as ds:
        ds.write(d)
    return chemin


def _manifeste(sources):
    """sources : liste de (uri, x0, y_nord, taille)."""
    return {"uriPrefix": PREF, "tilesets": [{"sources": [
        {"uris": [u], "affineTransform": {"translateX": x, "translateY": y, "scaleX": 0.5, "scaleY": -0.5},
         "dimensions": {"width": t, "height": t}} for u, x, y, t in sources]}]}


def _ouvrir(table):
    def f(url):
        assert url.startswith("/vsicurl/")
        return rasterio.open(table[url[len("/vsicurl/"):]])
    return f


def _get(manifeste, nom="v1/manifests/11_EPSG_32631_2023_06_30.json"):
    def g(url):
        if "storage/v1/b" in url:
            return {"items": [{"name": nom}]}
        return manifeste
    return g


def _ctx(tmp_path, offline=False):
    d = tmp_path / "ville-test"
    d.mkdir(exist_ok=True)
    (d / "config.toml").write_text(
        '[ville]\nnom = "Test"\n[zone]\nbbox = [2.372, 6.346, 2.402, 6.366]\n[generation]\ngraine = 1\n', encoding="utf-8")
    return open_context(d, offline=offline)


def test_lister_manifestes_pages_et_filtre():
    pages = [
        {"items": [{"name": "v1/manifests/a_EPSG_32631_2023_06_30.json"},
                   {"name": "v1/manifests/b_EPSG_32632_2023_06_30.json"}], "nextPageToken": "T"},
        {"items": [{"name": "v1/manifests/c_EPSG_32631_2022_06_30.json"},
                   {"name": "v1/manifests/0_EPSG_32631_2023_06_30.json"}]},
    ]
    vus = []

    def get(url):
        vus.append(url)
        return pages[1] if "pageToken=T" in url else pages[0]
    assert B.lister_manifestes(32631, get=get) == [
        "v1/manifests/0_EPSG_32631_2023_06_30.json", "v1/manifests/a_EPSG_32631_2023_06_30.json"]
    assert len(vus) == 2
    assert B.lister_manifestes(32631, annee=2022, get=get) == ["v1/manifests/c_EPSG_32631_2022_06_30.json"]


def test_tuiles_pour_intersection_url_et_doublons():
    man = _manifeste([("1/t.tif", 1000.0, 2000.0, 400), ("2/t.tif", 5000.0, 9000.0, 400)])
    r = B.tuiles_pour((1100, 1900, 1150, 1950), [man, man])
    assert r == [{"url": BASE + "1/t.tif", "emprise": (1000.0, 1800.0, 1200.0, 2000.0)}]
    assert r[0]["url"].startswith("https://storage.googleapis.com/")


def test_tuiles_pour_aucune():
    man = _manifeste([("1/t.tif", 1000.0, 2000.0, 400)])
    assert B.tuiles_pour((0, 0, 10, 10), [man]) == []
    assert B.tuiles_pour((1200, 1900, 1300, 1950), [man]) == []


def test_tuiles_pour_echelle_y_positive():
    man = {"uriPrefix": PREF, "tilesets": [{"sources": [
        {"uris": ["z.tif"], "affineTransform": {"translateX": 0.0, "translateY": 0.0, "scaleX": 0.5, "scaleY": 0.5},
         "dimensions": {"width": 20, "height": 20}}]}]}
    assert B.tuiles_pour((1, 1, 2, 2), [man])[0]["emprise"] == (0.0, 0.0, 10.0, 10.0)


def test_telecharger_une_tuile_carre(tmp_path):
    cx, cy = _centre_utm()
    x0, y0 = round(cx) - 100.0, round(cy) + 100.0
    chemin = _tif(tmp_path / "a.tif", x0, y0, carre=(160, 240, 160, 240, 10.0))
    man = _manifeste([("a.tif", x0, y0, 400)])
    d = B.telecharger(BBOX, 32631, ouvrir=_ouvrir({BASE + "a.tif": chemin}), get=_get(man))
    assert d["pas"] == 2.0 and d["epsg"] == 32631
    assert d["hauteur"].dtype == np.float32 and d["hauteur"].shape == d["presence"].shape
    # la zone (environ 3 km) est plus grande que la tuile : la grille déborde, le reste vaut 0
    assert d["x0"] < x0 and d["y0"] > y0
    assert float(d["hauteur"].max()) == pytest.approx(10.0, abs=0.01)
    h = B.Hauteurs(d)
    mx, my = x0 + 100, y0 - 100
    hh, pp = h.echantillon([mx, mx + 80], [my, my])
    assert hh[0] == pytest.approx(10.0, abs=0.01) and pp[0] == pytest.approx(1.0, abs=0.01)
    assert hh[1] == 0 and pp[1] == 0
    assert h.pour_emprise(box(mx - 10, my - 10, mx + 10, my + 10)) == pytest.approx(10.0, abs=0.01)
    assert h.pour_emprise(box(mx + 40, my + 40, mx + 60, my + 60)) is None
    assert 0 < h.couverture() < 1


def test_telecharger_aucune_tuile():
    man = _manifeste([("a.tif", 100.0, 200.0, 400)])
    with pytest.raises(LookupError, match="aucune donnée"):
        B.telecharger(BBOX, 32631, ouvrir=lambda u: None, get=_get(man))


def test_telecharger_deux_tuiles_voisines(tmp_path):
    cx, cy = _centre_utm()
    xa, y0 = round(cx) - 100.0, round(cy) + 100.0
    a = _tif(tmp_path / "a.tif", xa, y0, taille=200, carre=(80, 120, 120, 160, 8.0))
    b = _tif(tmp_path / "b.tif", xa + 100, y0, taille=200, carre=(80, 120, 40, 80, 20.0))
    man = _manifeste([("a.tif", xa, y0, 200), ("b.tif", xa + 100, y0, 200)])
    d = B.telecharger(BBOX, 32631, ouvrir=_ouvrir({BASE + "a.tif": a, BASE + "b.tif": b}), get=_get(man))
    h = B.Hauteurs(d)
    ha, _ = h.echantillon([xa + 70], [y0 - 50])
    hb, _ = h.echantillon([xa + 130], [y0 - 50])
    assert ha[0] == pytest.approx(8.0, abs=0.01)
    assert hb[0] == pytest.approx(20.0, abs=0.01)


def test_echantillon_hors_grille():
    d = {"hauteur": np.full((3, 3), 5, np.float32), "presence": np.ones((3, 3), np.float32),
         "x0": 0.0, "y0": 6.0, "pas": 2.0, "epsg": 32631}
    hh, pp = B.Hauteurs(d).echantillon([-5.0, 1.0, 100.0], [3.0, 5.0, 3.0])
    assert list(hh) == [0, 5, 0] and list(pp) == [0, 1, 0]


def test_enregistrer_charger(tmp_path):
    d = {"hauteur": np.arange(6, dtype=np.float32).reshape(2, 3), "presence": np.ones((2, 3), np.float32),
         "x0": 10.5, "y0": 20.5, "pas": 2.0, "epsg": 32631}
    B.enregistrer(tmp_path / "sous" / "c.npz", d)
    r = B.charger(tmp_path / "sous" / "c.npz")
    assert np.array_equal(r["hauteur"], d["hauteur"]) and r["x0"] == 10.5 and r["epsg"] == 32631
    assert not list((tmp_path / "sous").glob("*.tmp"))


def _fake(appels):
    def f(bbox, epsg, ouvrir=None, get=None):
        appels.append(1)
        return {"hauteur": np.ones((2, 2), np.float32), "presence": np.ones((2, 2), np.float32),
                "x0": 0.0, "y0": 4.0, "pas": 2.0, "epsg": epsg}
    return f


def test_obtenir_telechargement_puis_cache_et_source(tmp_path):
    ctx = _ctx(tmp_path)
    appels = []
    d = B.obtenir(ctx, 32631, telecharger_fn=_fake(appels))
    assert d["epsg"] == 32631 and len(appels) == 1
    assert (ctx.project.cache / "batiments25d.npz").is_file()
    srcs = [s for s in read_sources(ctx.project.data) if s["id"] == B.SOURCE["id"]]
    assert len(srcs) == 1 and srcs[0]["zone"] == list(BBOX)
    ctx2 = _ctx(tmp_path, offline=True)
    assert B.obtenir(ctx2, 32631, telecharger_fn=_fake(appels)) is not None
    assert len(appels) == 1
    assert len([s for s in read_sources(ctx2.project.data) if s["id"] == B.SOURCE["id"]]) == 1


def test_obtenir_hors_ligne_sans_cache(tmp_path):
    appels = []
    assert B.obtenir(_ctx(tmp_path, offline=True), 32631, telecharger_fn=_fake(appels)) is None
    assert appels == []


def test_obtenir_erreur_reseau(tmp_path):
    ctx = _ctx(tmp_path)

    def mauvais(bbox, epsg, ouvrir=None, get=None):
        raise OSError("coupé")
    with pytest.raises(RuntimeError, match="impossible"):
        B.obtenir(ctx, 32631, telecharger_fn=mauvais)
    assert not (ctx.project.cache / "batiments25d.npz").exists()


def test_obtenir_lookup_error(tmp_path):
    ctx = _ctx(tmp_path)

    def vide(bbox, epsg, ouvrir=None, get=None):
        raise LookupError("rien")
    assert B.obtenir(ctx, 32631, telecharger_fn=vide) is None
    assert not (ctx.project.cache / "batiments25d.npz").exists()
    assert not [s for s in read_sources(ctx.project.data) if s["id"] == B.SOURCE["id"]]
