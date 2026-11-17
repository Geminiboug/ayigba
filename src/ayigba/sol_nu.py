"""Sol nu : retirer du modèle de surface Copernicus la hauteur des bâtiments mesurée par Google Open Buildings 2.5D.

Le modèle Copernicus (radar, 30 m) mesure le dessus des choses. Sur un pixel de 30 m, il voit à peu près
« sol + part couverte de toits x hauteur des toits ». On estime donc le sol nu par :
    sol = surface - moyenne, sur le pixel, de (présence x hauteur) des bâtiments.
C'est une approximation (le radar ne fait pas exactement une moyenne), mais elle retire l'essentiel du biais des
quartiers denses, que l'enveloppe basse seule ne pouvait pas distinguer d'une colline.
Les arbres ne sont pas dans Open Buildings : l'enveloppe basse (dem.Altitudes) reste utile après cette correction.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer


CORRECTION_MAX = 8.0
NIVEAU_MER_MIN = 0.5      # une terre au-dessus de 0,5 m ne peut pas être abaissée en dessous
PLANCHER_SOUS_MIN = 4.0   # le sol nu ne descend pas à plus de 4 m sous le terrain le plus bas des environs (200 m)


def _min_local(a: np.ndarray, rayon: int) -> np.ndarray:
    n, m = a.shape
    p = np.pad(a, rayon, mode="edge")
    out = np.full_like(a, np.inf)
    for di in range(2 * rayon + 1):
        for dj in range(2 * rayon + 1):
            out = np.minimum(out, p[di:di + n, dj:dj + m])
    return out


def _integrale(a: np.ndarray) -> np.ndarray:
    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1))
    s[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
    return s


def corriger(dem: dict, bat: dict, demi_cote_m: float | None = None) -> tuple[dict, dict]:
    """Renvoie (dem corrigé, statistiques). dem : dict de ayigba.dem ; bat : dict de ayigba.batiments25d.
    demi_cote_m : demi-côté de la fenêtre de moyenne (par défaut la moitié d'un pixel du modèle, environ 15 m)."""
    alt = np.asarray(dem["altitudes"], dtype=np.float64)
    n, m = alt.shape
    pas_deg = float(dem["pas"])
    if demi_cote_m is None:
        demi_cote_m = pas_deg * 111_320.0 / 2.0
    excedent = np.asarray(bat["presence"], dtype=np.float64) * np.asarray(bat["hauteur"], dtype=np.float64)
    excedent = np.nan_to_num(np.clip(excedent, 0.0, 200.0))
    s = _integrale(excedent)
    gl, gc = excedent.shape
    p = float(bat["pas"])

    lon = float(dem["ouest"]) + (np.arange(m) + 0.5) * pas_deg
    lat = float(dem["nord"]) - (np.arange(n) + 0.5) * pas_deg
    lon2, lat2 = np.meshgrid(lon, lat)
    x, y = Transformer.from_crs(4326, int(bat["epsg"]), always_xy=True).transform(lon2, lat2)
    # fenêtre en indices de la grille des bâtiments (lignes du nord vers le sud)
    c0 = np.clip(np.floor((x - demi_cote_m - float(bat["x0"])) / p).astype(int), 0, gc)
    c1 = np.clip(np.ceil((x + demi_cote_m - float(bat["x0"])) / p).astype(int), 0, gc)
    r0 = np.clip(np.floor((float(bat["y0"]) - (y + demi_cote_m)) / p).astype(int), 0, gl)
    r1 = np.clip(np.ceil((float(bat["y0"]) - (y - demi_cote_m)) / p).astype(int), 0, gl)
    aire = (r1 - r0) * (c1 - c0)
    somme = s[r1, c1] - s[r0, c1] - s[r1, c0] + s[r0, c0]
    couvert = aire > 0
    moyenne = np.where(couvert, somme / np.maximum(aire, 1), 0.0)
    # garde-fou : la correction ne peut pas enfoncer le sol sous le terrain bas des environs (fenêtre de 7 x 7 pixels,
    # environ 200 m). Sans lui, une mauvaise détection (grand toit, hangar) creusait des trous de plusieurs dizaines de mètres.
    # la correction est aussi plafonnée à 8 m (bien au-dessus de ce que des toits de quartier produisent en moyenne sur 30 m)
    plancher = _min_local(alt, 3) - PLANCHER_SOUS_MIN
    sol = np.maximum(alt - np.minimum(moyenne, CORRECTION_MAX), np.minimum(alt, plancher))
    # la terre ne passe jamais sous le niveau de la mer à cause de la correction (sinon la plage se retrouve sous l'eau)
    sol = np.maximum(sol, np.minimum(alt, NIVEAU_MER_MIN))
    out = dict(dem)
    out["altitudes"] = sol.astype(np.float32)
    applique = alt - sol
    stats = {"pixels_corriges": int((applique > 0.05).sum()), "pixels_total": int(n * m),
             "correction_max_m": round(float(applique.max()), 2), "correction_moyenne_m": round(float(applique[couvert].mean()), 2) if couvert.any() else 0.0,
             "pixels_bornes": int(((alt - moyenne) < sol - 1e-9).sum()),
             "pixels_hors_donnees": int((~couvert).sum())}
    return out, stats
