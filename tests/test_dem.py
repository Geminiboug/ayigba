"""Tests du module dem : tuiles, lecture, cache, interpolation. Aucun accès réseau."""
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ayigba import dem as D
from ayigba.geo import LocalFrame
from ayigba.project import open_context

BBOX = (2.372, 6.346, 2.402, 6.366)


def _tif(chemin, data, nodata=None):
    h, w = data.shape
    with rasterio.open(chemin, "w", driver="GTiff", height=h, width=w, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(2.0, 7.0, 0.001, 0.001), nodata=nodata) as ds:
        ds.write(data.astype("float32"), 1)
    return chemin


def _ctx(tmp_path, offline=False):
    d = tmp_path / "ville-test"
    d.mkdir(exist_ok=True)
    (d / "config.toml").write_text(
        '[ville]\nnom = "Test"\n[zone]\nbbox = [2.372, 6.346, 2.402, 6.366]\n[generation]\ngraine = 1\n', encoding="utf-8")
    return open_context(d, offline=offline)


def _pente(frame, n=60, pas=0.0005):
    """Plan z = 2 x lon_relatif (en degrés), centré sur la zone."""
    ouest = frame.lon0 - n * pas / 2
    nord = frame.lat0 + n * pas / 2
    lons = ouest + (np.arange(n) + 0.5) * pas
    z = np.tile(2.0 * (lons - frame.lon0), (n, 1))
    return {"altitudes": z.astype(np.float32), "ouest": ouest, "nord": nord, "pas": pas}


def test_tuile_url():
    u = D.tuile_url(6.36, 2.42)
    assert "_N06_00_E002_00_" in u and u.endswith("_DEM.tif")
    u = D.tuile_url(-0.5, -12.3)
    assert "_S01_00_W013_00_" in u


def test_tuiles_pour():
    assert D.tuiles_pour(BBOX) == [(6, 2)]
    assert D.tuiles_pour((2.9995, 6.3, 3.1, 6.4)) == [(6, 2), (6, 3)]


def test_telecharger_une_tuile(tmp_path):
    data = np.arange(1000 * 1000, dtype="float32").reshape(1000, 1000) % 50
    data[1:3, 1:3] = -32768.0
    chemin = _tif(tmp_path / "t.tif", data, nodata=-32768.0)
    vus = []

    def ouvrir(url):
        vus.append(url)
        return rasterio.open(chemin)

    bbox = (2.1005, 6.5005, 2.1105, 6.5105)
    dem = D.telecharger(bbox, ouvrir=ouvrir)
    assert vus == [D.tuile_url(6.5, 2.1)]
    a = dem["altitudes"]
    assert a.dtype == np.float32 and a.ndim == 2
    assert dem["pas"] == pytest.approx(0.001)
    assert dem["ouest"] == pytest.approx(2.097)
    assert dem["nord"] == pytest.approx(6.514)
    assert a.shape == (16, 16)

    # nodata remplacé par 0
    chemin2 = _tif(tmp_path / "n.tif", np.full((1000, 1000), -32768.0), nodata=-32768.0)
    dem2 = D.telecharger(bbox, ouvrir=lambda url: rasterio.open(chemin2))
    assert float(dem2["altitudes"].max()) == 0.0 and float(dem2["altitudes"].min()) == 0.0


def test_telecharger_deux_tuiles():
    with pytest.raises(NotImplementedError):
        D.telecharger((2.9995, 6.3, 3.1, 6.4), ouvrir=lambda u: None)


def test_aller_retour(tmp_path):
    dem = {"altitudes": np.random.rand(5, 7).astype(np.float32), "ouest": 2.1, "nord": 6.5, "pas": 0.001}
    p = tmp_path / "x" / "d.npz"
    D.enregistrer(p, dem)
    r = D.charger(p)
    assert np.array_equal(r["altitudes"], dem["altitudes"]) and r["altitudes"].dtype == np.float32
    assert r["ouest"] == 2.1 and r["nord"] == 6.5 and r["pas"] == 0.001
    assert all(type(r[k]) is float for k in ("ouest", "nord", "pas"))
    assert [f.name for f in p.parent.iterdir()] == ["d.npz"]


def test_pente_interpolee():
    frame = LocalFrame(BBOX)
    alt = D.Altitudes(_pente(frame), frame, lissage=0)
    xs = np.array([-100.0, 0.0, 37.3, 150.0])
    ys = np.array([10.0, -20.0, 0.0, 33.0])
    lon, _ = frame.to_wgs84(xs, ys)
    attendu = 2.0 * (lon - frame.lon0)
    h = alt.hauteur(xs, ys)
    assert h.dtype == np.float64 and h.shape == xs.shape
    assert np.allclose(h, attendu, atol=0.01)
    assert alt.hauteur(0.0, 0.0).shape == ()


def test_centre_de_pixel_exact():
    frame = LocalFrame(BBOX)
    dem = _pente(frame)
    dem["altitudes"][10, 20] = 42.0
    alt = D.Altitudes(dem, frame, lissage=0)
    lon = dem["ouest"] + 20.5 * dem["pas"]
    lat = dem["nord"] - 10.5 * dem["pas"]
    x, y = frame.to_local(lon, lat)
    assert float(alt.hauteur(x, y)) == pytest.approx(42.0, abs=1e-3)


def test_hors_grille_bord():
    frame = LocalFrame(BBOX)
    alt = D.Altitudes(_pente(frame), frame, lissage=0)
    assert float(alt.hauteur(1e6, 0.0)) == pytest.approx(float(alt.grille[30, -1]), abs=0.05)
    assert float(alt.hauteur(-1e6, 1e6)) == pytest.approx(float(alt.grille[0, 0]), abs=1e-6)


def test_lissage_pic():
    frame = LocalFrame(BBOX)
    g = np.zeros((40, 40), dtype=np.float32)
    g[20, 20] = 100.0
    dem = {"altitudes": g, "ouest": 2.0, "nord": 7.0, "pas": 0.0005}
    brut = D.Altitudes(dem, frame, lissage=0)
    lisse = D.Altitudes(dem, frame, lissage=1.0)
    assert lisse.stats()["max"] < brut.stats()["max"]
    assert lisse.stats()["moyenne"] == pytest.approx(brut.stats()["moyenne"], rel=0.01)


def test_plat_et_stats():
    p = D.Altitudes.plat(3.5)
    assert np.all(p.hauteur(np.zeros((2, 3)), np.ones((2, 3))) == 3.5)
    assert p.hauteur(np.zeros((2, 3)), np.ones((2, 3))).shape == (2, 3)
    assert float(D.Altitudes.plat().hauteur(1.0, 2.0)) == 0.0
    frame = LocalFrame(BBOX)
    dem = {"altitudes": np.array([[1.0, 2.0], [3.0, 6.0]], dtype=np.float32), "ouest": 2.0, "nord": 7.0, "pas": 0.001}
    assert D.Altitudes(dem, frame, lissage=0).stats() == {"min": 1.0, "max": 6.0, "moyenne": 3.0}


def test_empreinte():
    frame = LocalFrame(BBOX)
    dem = _pente(frame)
    e1 = D.Altitudes(dem, frame).empreinte()
    assert len(e1) == 16 and e1 == D.Altitudes(dem, frame).empreinte()
    dem2 = {**dem, "altitudes": dem["altitudes"].copy()}
    dem2["altitudes"][0, 0] += 5
    assert D.Altitudes(dem2, frame).empreinte() != e1


def _interdit(*a, **k):
    raise AssertionError("accès réseau interdit")


def _faux(bbox, ouvrir=None):
    return {"altitudes": np.ones((3, 3), dtype=np.float32), "ouest": 2.0, "nord": 7.0, "pas": 0.001}


def test_obtenir_cache_present(tmp_path):
    ctx = _ctx(tmp_path)
    D.enregistrer(ctx.project.cache / "dem_copernicus.npz", _faux(None))
    dem = D.obtenir(ctx, telecharger_fn=_interdit)
    assert dem["altitudes"].shape == (3, 3)


def test_obtenir_hors_ligne(tmp_path):
    ctx = _ctx(tmp_path, offline=True)
    assert D.obtenir(ctx, telecharger_fn=_interdit) is None


def test_obtenir_telecharge(tmp_path):
    ctx = _ctx(tmp_path)
    dem = D.obtenir(ctx, telecharger_fn=_faux)
    assert dem["altitudes"].shape == (3, 3)
    assert (ctx.project.cache / "dem_copernicus.npz").is_file()
    src = json.loads((ctx.project.data / "sources.json").read_text(encoding="utf-8"))
    assert [s["id"] for s in src] == ["copernicus_dem"]
    assert src[0]["zone"] == list(BBOX) and src[0]["date_collecte"]


def test_obtenir_echec_reseau(tmp_path):
    ctx = _ctx(tmp_path)

    def casse(bbox, ouvrir=None):
        raise rasterio.errors.RasterioIOError("coupé")

    with pytest.raises(RuntimeError):
        D.obtenir(ctx, telecharger_fn=casse)
    assert not (ctx.project.cache / "dem_copernicus.npz").exists()
    assert not (ctx.project.data / "sources.json").exists()


def test_obtenir_source_non_dupliquee(tmp_path):
    ctx = _ctx(tmp_path)
    D.obtenir(ctx, telecharger_fn=_faux)
    avant = (ctx.project.data / "sources.json").read_text(encoding="utf-8")
    D.obtenir(ctx, telecharger_fn=_interdit)
    assert (ctx.project.data / "sources.json").read_text(encoding="utf-8") == avant
    # source absente du registre : réenregistrée avec la date du fichier
    (ctx.project.data / "sources.json").unlink()
    D.obtenir(ctx, telecharger_fn=_interdit)
    src = json.loads((ctx.project.data / "sources.json").read_text(encoding="utf-8"))
    assert len(src) == 1 and src[0]["id"] == "copernicus_dem"
