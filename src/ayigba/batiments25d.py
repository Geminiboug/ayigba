"""Hauteurs de bâtiments : Google Open Buildings 2.5D Temporal (tuiles GeoTIFF de 0,5 m en projection UTM).

On lit seulement les bandes 2 (hauteur en mètres) et 3 (présence de bâtiment entre 0 et 1), réduites au pas `PAS`
par moyenne, grâce aux aperçus internes des tuiles (lecture à distance rapide).
"""
from __future__ import annotations

import datetime
import json
import math
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
import rasterio.windows
import shapely
from pyproj import Transformer
from rasterio.enums import Resampling

from .sources import read_sources, register_source

ANNEE = 2023
PAS = 2.0
MARGE = 20.0

BUCKET = "open-buildings-temporal-data"
LISTE_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
MANIFESTE_URL = f"https://storage.googleapis.com/{BUCKET}/"
USER_AGENT = "ayigba/0.1 (generateur de cartes ; https://github.com/Geminiboug/ayigba)"

SOURCE = {
    "id": "google_open_buildings_25d",
    "nom": "Google Open Buildings 2.5D Temporal",
    "licence": "CC BY 4.0",
    "url_licence": "https://creativecommons.org/licenses/by/4.0/",
    "attribution": "Google Open Buildings 2.5D Temporal Dataset (2023), licence CC BY 4.0",
    "url_source": "https://sites.research.google/gr/open-buildings/temporal",
}


def _get_json(url: str):
    """Télécharge et décode un JSON (User-Agent explicite, délai de 60 s)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def lister_manifestes(epsg: int, annee: int = ANNEE, get=_get_json) -> list[str]:
    """Noms des manifestes de l'EPSG et de l'année donnés (toutes les pages de la liste), triés."""
    motif = f"_EPSG_{epsg}_{annee}_"
    noms: set[str] = set()
    jeton = None
    while True:
        url = f"{LISTE_URL}?prefix=v1/manifests/&maxResults=1000&fields=items(name),nextPageToken"
        if jeton:
            url += "&pageToken=" + urllib.parse.quote(jeton, safe="")
        page = get(url) or {}
        for it in page.get("items", []):
            nom = it.get("name", "")
            if motif in nom:
                noms.add(nom)
        jeton = page.get("nextPageToken")
        if not jeton:
            break
    return sorted(noms)


def _url_tuile(prefixe: str, uri: str) -> str:
    url = prefixe + uri
    if url.startswith("gs://"):
        url = "https://storage.googleapis.com/" + url[len("gs://"):]
    return url


def tuiles_pour(bbox_utm, manifestes_json) -> list[dict]:
    """Tuiles des manifestes qui intersectent bbox_utm (xmin, ymin, xmax, ymax) : [{"url", "emprise"}], triées, sans doublon."""
    bx0, by0, bx1, by1 = bbox_utm
    trouvees: dict[str, tuple] = {}
    for man in manifestes_json:
        prefixe = man.get("uriPrefix", "")
        for ts in man.get("tilesets", []):
            for src in ts.get("sources", []):
                at = src["affineTransform"]
                dim = src["dimensions"]
                xa = at["translateX"]
                xb = xa + at["scaleX"] * dim["width"]
                ya = at["translateY"]
                yb = ya + at["scaleY"] * dim["height"]
                emprise = (min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb))
                if emprise[0] >= bx1 or emprise[2] <= bx0 or emprise[1] >= by1 or emprise[3] <= by0:
                    continue
                for uri in src.get("uris", []):
                    trouvees[_url_tuile(prefixe, uri)] = emprise
    return [{"url": u, "emprise": trouvees[u]} for u in sorted(trouvees)]


def telecharger(bbox, epsg: int, ouvrir=rasterio.open, get=_get_json, pas: float = PAS) -> dict:
    """Hauteurs et présence de bâtiments sur une grille régulière de pas `pas` couvrant la zone (ouest, sud, est, nord)."""
    ouest, sud, est, nord = bbox
    tr = Transformer.from_crs(4326, int(epsg), always_xy=True)
    xs, ys = tr.transform([ouest, est, ouest, est], [sud, sud, nord, nord])
    bb = (min(xs) - MARGE, min(ys) - MARGE, max(xs) + MARGE, max(ys) + MARGE)
    try:
        manifestes = [get(MANIFESTE_URL + n) for n in lister_manifestes(epsg, get=get)]
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Lecture des manifestes Open Buildings 2.5D impossible : {e}") from e
    tuiles = tuiles_pour(bb, manifestes)
    if not tuiles:
        raise LookupError("aucune donnée Open Buildings 2.5D pour cette zone")

    x0, y0 = bb[0], bb[3]
    nc = max(1, int(math.ceil((bb[2] - bb[0]) / pas)))
    nl = max(1, int(math.ceil((bb[3] - bb[1]) / pas)))
    hauteur = np.zeros((nl, nc), dtype=np.float32)
    presence = np.zeros((nl, nc), dtype=np.float32)
    for t in tuiles:
        ex0, ey0, ex1, ey1 = t["emprise"]
        j0 = max(0, int(math.floor((ex0 - x0) / pas)))
        j1 = min(nc, int(math.ceil((ex1 - x0) / pas)))
        i0 = max(0, int(math.floor((y0 - ey1) / pas)))
        i1 = min(nl, int(math.ceil((y0 - ey0) / pas)))
        if j1 <= j0 or i1 <= i0:
            continue
        try:
            with ouvrir("/vsicurl/" + t["url"]) as ds:
                fen = rasterio.windows.from_bounds(
                    x0 + j0 * pas, y0 - i1 * pas, x0 + j1 * pas, y0 - i0 * pas, transform=ds.transform)
                lu = ds.read([2, 3], window=fen, out_shape=(2, i1 - i0, j1 - j0),
                             resampling=Resampling.average, boundless=True, fill_value=0)
        except (OSError, rasterio.errors.RasterioError) as e:
            raise RuntimeError(f"Lecture d'une tuile Open Buildings 2.5D impossible : {e}") from e
        lu = np.nan_to_num(lu.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
        np.maximum(hauteur[i0:i1, j0:j1], lu[0], out=hauteur[i0:i1, j0:j1])
        np.maximum(presence[i0:i1, j0:j1], lu[1], out=presence[i0:i1, j0:j1])
    return {"hauteur": hauteur, "presence": presence, "x0": float(x0), "y0": float(y0),
            "pas": float(pas), "epsg": int(epsg)}


def enregistrer(chemin, d: dict) -> None:
    """Écriture atomique en .npz."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(
                f,
                hauteur=np.asarray(d["hauteur"], dtype=np.float32),
                presence=np.asarray(d["presence"], dtype=np.float32),
                x0=np.float64(d["x0"]), y0=np.float64(d["y0"]), pas=np.float64(d["pas"]),
                epsg=np.int64(d["epsg"]),
            )
        os.replace(tmp, chemin)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def charger(chemin) -> dict:
    with np.load(Path(chemin)) as z:
        return {
            "hauteur": np.asarray(z["hauteur"], dtype=np.float32),
            "presence": np.asarray(z["presence"], dtype=np.float32),
            "x0": float(z["x0"]), "y0": float(z["y0"]), "pas": float(z["pas"]), "epsg": int(z["epsg"]),
        }


class Hauteurs:
    """Accès aux hauteurs de bâtiments en coordonnées UTM."""

    def __init__(self, d: dict):
        self.hauteur = np.asarray(d["hauteur"], dtype=np.float32)
        self.presence = np.asarray(d["presence"], dtype=np.float32)
        self.x0 = float(d["x0"])
        self.y0 = float(d["y0"])
        self.pas = float(d["pas"])

    def echantillon(self, x_utm, y_utm):
        """(hauteur, présence) au pixel le plus proche ; 0 et 0 hors grille."""
        x = np.asarray(x_utm, dtype=np.float64)
        y = np.asarray(y_utm, dtype=np.float64)
        j = np.floor((x - self.x0) / self.pas).astype(int)
        i = np.floor((self.y0 - y) / self.pas).astype(int)
        n, m = self.hauteur.shape
        ok = (i >= 0) & (i < n) & (j >= 0) & (j < m)
        ic = np.clip(i, 0, n - 1)
        jc = np.clip(j, 0, m - 1)
        return np.where(ok, self.hauteur[ic, jc], 0.0), np.where(ok, self.presence[ic, jc], 0.0)

    def pour_emprise(self, polygone_utm):
        """Médiane des hauteurs des pixels (centre dans le polygone, présence >= 0,5) ; None s'il y en a moins de 2."""
        n, m = self.hauteur.shape
        xmin, ymin, xmax, ymax = polygone_utm.bounds
        j0 = max(0, int(math.floor((xmin - self.x0) / self.pas)))
        j1 = min(m, int(math.ceil((xmax - self.x0) / self.pas)))
        i0 = max(0, int(math.floor((self.y0 - ymax) / self.pas)))
        i1 = min(n, int(math.ceil((self.y0 - ymin) / self.pas)))
        if j1 <= j0 or i1 <= i0:
            return None
        cx = self.x0 + (np.arange(j0, j1) + 0.5) * self.pas
        cy = self.y0 - (np.arange(i0, i1) + 0.5) * self.pas
        gx, gy = np.meshgrid(cx, cy)
        dedans = shapely.contains_xy(polygone_utm, gx, gy)
        garde = dedans & (self.presence[i0:i1, j0:j1] >= 0.5)
        if int(garde.sum()) < 2:
            return None
        return float(np.median(self.hauteur[i0:i1, j0:j1][garde]))

    def couverture(self) -> float:
        """Part des pixels de la grille avec présence >= 0,5."""
        return float((self.presence >= 0.5).mean())


def obtenir(ctx, epsg: int, ouvrir=rasterio.open, get=_get_json, telecharger_fn=telecharger) -> dict | None:
    """Données de la zone avec cache dans le projet. None si hors ligne sans cache ou sans donnée pour la zone."""
    fichier = ctx.project.cache / "batiments25d.npz"
    data = ctx.project.data
    zone = list(ctx.config.bbox)
    if fichier.is_file():
        d = charger(fichier)
        if not any(s.get("id") == SOURCE["id"] for s in read_sources(data)):
            date = datetime.date.fromtimestamp(fichier.stat().st_mtime).isoformat()
            register_source(data, {**SOURCE, "date_collecte": date, "zone": zone})
        return d
    if ctx.offline:
        return None
    try:
        d = telecharger_fn(ctx.config.bbox, epsg, ouvrir=ouvrir, get=get)
    except LookupError:
        return None
    except (OSError, RuntimeError, rasterio.errors.RasterioError) as e:
        raise RuntimeError(
            f"Téléchargement des bâtiments Open Buildings 2.5D impossible (réseau ou service indisponible) : {e}") from e
    enregistrer(fichier, d)
    register_source(data, {**SOURCE, "date_collecte": datetime.date.today().isoformat(), "zone": zone})
    return d
