"""Modèle numérique d'altitude : Copernicus DEM GLO-30 (30 m), cache et altitude en tout point du repère local.

Une zone à cheval sur 2 ou 4 tuiles de 1 degré est assemblée en une seule grille régulière (même pas exigé).
"""
from __future__ import annotations

import datetime
import hashlib
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
import rasterio.windows

from .geo import LocalFrame
from .sources import read_sources, register_source

TUILE_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
    "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif"
)

SOURCE = {
    "id": "copernicus_dem",
    "nom": "Copernicus DEM GLO-30",
    "licence": "Licence Copernicus (libre, usage commercial autorisé avec mention)",
    "url_licence": "https://dataspace.copernicus.eu/terms-and-conditions",
    "attribution": (
        "Contient des données Copernicus (modèle numérique de surface GLO-30), © DLR e.V. 2010-2014 et "
        "© Airbus Defence and Space GmbH 2014-2018, fournies par l'Union européenne et l'ESA dans le cadre de Copernicus"
    ),
    "url_source": "https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model",
}

MARGE_TUILES = 0.002
MARGE_FENETRE = 0.003


def tuile_url(lat: float, lon: float) -> str:
    """URL de la tuile de 1 degré qui contient le point."""
    lat0 = math.floor(lat)
    lon0 = math.floor(lon)
    return TUILE_URL.format(ns="N" if lat0 >= 0 else "S", lat=abs(lat0), ew="E" if lon0 >= 0 else "W", lon=abs(lon0))


def tuiles_pour(bbox) -> list[tuple[int, int]]:
    """Coins sud-ouest (lat0, lon0) entiers des tuiles couvrant (ouest, sud, est, nord), avec une petite marge."""
    ouest, sud, est, nord = bbox
    lats = range(math.floor(sud - MARGE_TUILES), math.floor(nord + MARGE_TUILES) + 1)
    lons = range(math.floor(ouest - MARGE_TUILES), math.floor(est + MARGE_TUILES) + 1)
    return sorted((la, lo) for la in lats for lo in lons)


def telecharger(bbox, ouvrir=rasterio.open) -> dict:
    """Lit la fenêtre de la zone dans chaque tuile couverte et les assemble en une grille régulière.

    Toutes les tuiles doivent avoir le même pas (sinon RuntimeError). Au recouvrement, la première tuile (ordre trié)
    l'emporte ; les pixels non couverts valent 0.0."""
    ouest, sud, est, nord = bbox
    morceaux = []  # (tableau, ouest, nord, pas)
    for lat0, lon0 in tuiles_pour(bbox):
        with ouvrir(tuile_url(lat0, lon0)) as ds:
            fen = rasterio.windows.from_bounds(
                ouest - MARGE_FENETRE, sud - MARGE_FENETRE, est + MARGE_FENETRE, nord + MARGE_FENETRE,
                transform=ds.transform,
            )
            fen = fen.round_offsets(op="floor").round_lengths(op="ceil")
            if len(tuiles_pour(bbox)) > 1:
                try:
                    fen = fen.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
                except rasterio.errors.WindowError:
                    continue
            tableau = ds.read(1, window=fen).astype(np.float32)
            transform = rasterio.windows.transform(fen, ds.transform)
            nodata = ds.nodata
        masque = ~np.isfinite(tableau)
        if nodata is not None and np.isfinite(nodata):
            masque |= tableau == np.float32(nodata)
        tableau[masque] = 0.0
        morceaux.append((tableau, float(transform.c), float(transform.f), float(transform.a)))
    if not morceaux:
        raise RuntimeError("aucune tuile ne couvre la zone")
    pas = morceaux[0][3]
    for _, _, _, p in morceaux:
        if not math.isclose(p, pas, rel_tol=1e-9):
            raise RuntimeError(f"pas différents entre tuiles ({pas} et {p}) : assemblage impossible")
    if len(morceaux) == 1:
        t, o, n, p = morceaux[0]
        return {"altitudes": t, "ouest": o, "nord": n, "pas": p}
    o_grille = min(m[1] for m in morceaux)
    n_grille = max(m[2] for m in morceaux)
    cols = max(int(round((m[1] - o_grille) / pas)) + m[0].shape[1] for m in morceaux)
    lignes = max(int(round((n_grille - m[2]) / pas)) + m[0].shape[0] for m in morceaux)
    grille = np.zeros((lignes, cols), dtype=np.float32)
    rempli = np.zeros((lignes, cols), dtype=bool)
    for t, o, n, _ in morceaux:
        c = int(round((o - o_grille) / pas))
        r = int(round((n_grille - n) / pas))
        h, w = t.shape
        libre = ~rempli[r:r + h, c:c + w]
        grille[r:r + h, c:c + w][libre] = t[libre]
        rempli[r:r + h, c:c + w] = True
    return {"altitudes": grille, "ouest": o_grille, "nord": n_grille, "pas": pas}


def enregistrer(chemin, dem: dict) -> None:
    """Écriture atomique d'un dem en .npz."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(
                f,
                altitudes=np.asarray(dem["altitudes"], dtype=np.float32),
                ouest=np.float64(dem["ouest"]),
                nord=np.float64(dem["nord"]),
                pas=np.float64(dem["pas"]),
            )
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def charger(chemin) -> dict:
    with np.load(Path(chemin)) as z:
        return {
            "altitudes": np.asarray(z["altitudes"], dtype=np.float32),
            "ouest": float(z["ouest"]),
            "nord": float(z["nord"]),
            "pas": float(z["pas"]),
        }


def _flou(grille: np.ndarray, sigma: float) -> np.ndarray:
    """Flou gaussien séparable, bords répliqués."""
    rayon = int(round(3 * sigma))
    if sigma <= 0 or rayon < 1:
        return grille
    k = np.exp(-0.5 * (np.arange(-rayon, rayon + 1) / sigma) ** 2)
    k /= k.sum()
    out = grille
    for axe in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axe] = (rayon, rayon)
        p = np.pad(out, pad, mode="edge")
        n = out.shape[axe]
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            acc += w * (p[i:i + n, :] if axe == 0 else p[:, i:i + n])
        out = acc
    return out


def _enveloppe_basse(grille: np.ndarray, rayon: int) -> np.ndarray:
    """Minimum local sur une fenêtre carrée de (2 x rayon + 1) pixels, bords répliqués.
    Le modèle Copernicus est un modèle de SURFACE : il monte sur les bâtiments et les arbres. Garder l'enveloppe basse
    retire ces bosses (un quartier dense n'est pas une colline), au prix d'un abaissement léger du vrai relief."""
    if rayon < 1:
        return grille
    n, m = grille.shape
    p = np.pad(grille, rayon, mode="edge")
    out = np.full_like(grille, np.inf)
    for di in range(2 * rayon + 1):
        for dj in range(2 * rayon + 1):
            out = np.minimum(out, p[di:di + n, dj:dj + m])
    return out


class Altitudes:
    """Altitude en tout point du repère local, par interpolation bilinéaire d'une grille lissée.

    enveloppe : rayon (en pixels) de l'enveloppe basse appliquée avant le lissage ; 0 = modèle brut."""

    def __init__(self, dem: dict, frame: LocalFrame, lissage: float = 1.0, enveloppe: int = 0):
        self.frame = frame
        self.enveloppe = int(enveloppe)
        self.lissage = float(lissage)
        self.ouest = float(dem["ouest"])
        self.nord = float(dem["nord"])
        self.pas = float(dem["pas"])
        grille = _enveloppe_basse(np.asarray(dem["altitudes"], dtype=np.float64), self.enveloppe)
        self.grille = _flou(grille, self.lissage) if self.lissage > 0 else grille

    @classmethod
    def plat(cls, hauteur: float = 0.0) -> "_Plat":
        return _Plat(hauteur)

    def hauteur(self, x, y) -> np.ndarray:
        lon, lat = self.frame.to_wgs84(x, y)
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        n, m = self.grille.shape
        fi = np.clip((self.nord - lat) / self.pas - 0.5, 0.0, n - 1.0)
        fj = np.clip((lon - self.ouest) / self.pas - 0.5, 0.0, m - 1.0)
        i0 = np.minimum(np.floor(fi).astype(int), max(n - 2, 0))
        j0 = np.minimum(np.floor(fj).astype(int), max(m - 2, 0))
        i1 = np.minimum(i0 + 1, n - 1)
        j1 = np.minimum(j0 + 1, m - 1)
        di = fi - i0
        dj = fj - j0
        g = self.grille
        haut = g[i0, j0] * (1 - dj) + g[i0, j1] * dj
        bas = g[i1, j0] * (1 - dj) + g[i1, j1] * dj
        return np.asarray(haut * (1 - di) + bas * di, dtype=np.float64)

    def stats(self) -> dict:
        return {
            "min": round(float(self.grille.min()), 2),
            "max": round(float(self.grille.max()), 2),
            "moyenne": round(float(self.grille.mean()), 2),
        }

    def empreinte(self) -> str:
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.grille, dtype=np.float64).tobytes())
        h.update(repr((self.grille.shape, self.ouest, self.nord, self.pas, self.lissage, self.enveloppe)).encode())
        return h.hexdigest()[:16]


class _Plat:
    """Même interface qu'Altitudes, hauteur constante."""

    def __init__(self, hauteur: float = 0.0):
        self._h = float(hauteur)

    def hauteur(self, x, y) -> np.ndarray:
        return np.full(np.shape(np.asarray(x, dtype=np.float64)), self._h, dtype=np.float64)

    def stats(self) -> dict:
        return {"min": round(self._h, 2), "max": round(self._h, 2), "moyenne": round(self._h, 2)}

    def empreinte(self) -> str:
        return hashlib.sha256(f"plat:{self._h!r}".encode()).hexdigest()[:16]


def obtenir(ctx, ouvrir=rasterio.open, telecharger_fn=telecharger) -> dict | None:
    """Dem de la zone, avec cache dans le projet. None si hors ligne et sans cache."""
    fichier = ctx.project.cache / "dem_copernicus.npz"
    data = ctx.project.data
    zone = list(ctx.config.bbox)
    if fichier.is_file():
        dem = charger(fichier)
        if not any(s.get("id") == SOURCE["id"] for s in read_sources(data)):
            date = datetime.date.fromtimestamp(fichier.stat().st_mtime).isoformat()
            register_source(data, {**SOURCE, "date_collecte": date, "zone": zone})
        return dem
    if ctx.offline:
        return None
    try:
        dem = telecharger_fn(ctx.config.bbox, ouvrir=ouvrir)
    except (OSError, RuntimeError, rasterio.errors.RasterioIOError) as e:
        raise RuntimeError(f"Téléchargement du relief Copernicus impossible (réseau ou service indisponible) : {e}") from e
    enregistrer(fichier, dem)
    register_source(data, {**SOURCE, "date_collecte": datetime.date.today().isoformat(), "zone": zone})
    return dem
