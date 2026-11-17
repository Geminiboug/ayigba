"""Étape « relief » : obtenir le modèle numérique d'altitude de la zone (Copernicus GLO-30, 30 m), avec cache.

Sorties : work/relief/info.json (statistiques) ; le modèle lui-même reste dans cache/dem_copernicus.npz.
Sans modèle (hors ligne et pas de cache, ou option désactivée) la carte reste plate : c'est écrit dans le journal et le rapport.
Options de config.toml : [relief] actif (vrai par défaut), lissage (pixels, 1.0 par défaut), enveloppe (pixels, 1 par défaut :
enveloppe basse locale qui retire les bosses dues aux bâtiments et aux arbres, 0 pour garder le modèle brut).
"""
from __future__ import annotations

import json

import numpy as np
import shapely
from pyproj import Transformer

from .. import batiments25d, dem, sol_nu
from ..geo import LocalFrame

STAGE = "relief"


def batiments(ctx):
    """Données Google Open Buildings 2.5D du projet (dict de batiments25d), ou None si absentes ou désactivées."""
    path = ctx.project.cache / "batiments25d.npz"
    if bool(ctx.config.option("batiments25d", "actif", True)) and path.is_file():
        return batiments25d.charger(path)
    return None


def vers_local(frame: LocalFrame, epsg: int):
    """Fonction (x, y) dans l'EPSG des données 2.5D -> (x, y) locaux."""
    if int(epsg) == frame.epsg:
        return lambda x, y: (np.asarray(x) - frame._e0, np.asarray(y) - frame._n0)
    t = Transformer.from_crs(int(epsg), 4326, always_xy=True)
    return lambda x, y: frame.to_local(*t.transform(x, y))


def vers_donnees(frame: LocalFrame, epsg: int):
    """Fonction géométrie locale -> géométrie dans l'EPSG des données 2.5D."""
    if int(epsg) == frame.epsg:
        return lambda g: shapely.transform(g, lambda c: c + np.array([frame._e0, frame._n0]))
    t = Transformer.from_crs(4326, int(epsg), always_xy=True)
    return lambda g: shapely.transform(g, lambda c: np.column_stack(t.transform(*frame.to_wgs84(c[:, 0], c[:, 1]))))


def altitudes(ctx, frame: LocalFrame):
    """Fonction d'altitude du projet : le modèle en cache (sol nu si les données 2.5D sont là), ou un sol plat à zéro."""
    path = ctx.project.cache / "dem_copernicus.npz"
    if bool(ctx.config.option("relief", "actif", True)) and path.is_file():
        model = dem.charger(path)
        bat = batiments(ctx)
        if bat is not None and bool(ctx.config.option("relief", "sol_nu", True)):
            model, _ = sol_nu.corriger(model, bat)
        return dem.Altitudes(model, frame, lissage=float(ctx.config.option("relief", "lissage", 1.0)),
                             enveloppe=int(ctx.config.option("relief", "enveloppe", 1)))
    return dem.Altitudes.plat(0.0)


def run(ctx) -> dict:
    out = ctx.project.stage_dir(STAGE)
    frame = LocalFrame(ctx.config.bbox)
    if not bool(ctx.config.option("relief", "actif", True)):
        ctx.journal.record("info", "relief", "relief désactivé dans la configuration ([relief] actif = false) : terrain plat")
        info = {"relief": "desactive"}
    else:
        if bool(ctx.config.option("batiments25d", "actif", True)):
            try:
                bat = batiments25d.obtenir(ctx, frame.epsg)
            except RuntimeError as exc:
                bat = None
                ctx.journal.record("signale", "batiments25d", f"données Open Buildings 2.5D indisponibles : {exc}")
            if bat is None:
                ctx.journal.record("info", "batiments25d", "pas de données Open Buildings 2.5D (hors ligne sans cache, ou zone non couverte)")
        model = dem.obtenir(ctx)
        if model is None:
            ctx.journal.record("info", "relief", "aucun modèle d'altitude en cache et mode hors ligne : terrain plat. Relance une fois sans --hors-ligne pour le télécharger.")
            info = {"relief": "plat", "raison": "pas de modèle d'altitude en cache"}
        else:
            alt = altitudes(ctx, frame)
            bat = batiments(ctx)
            correction = sol_nu.corriger(model, bat)[1] if bat is not None and bool(ctx.config.option("relief", "sol_nu", True)) else None
            if correction:
                ctx.journal.record("corrige", "relief", f"sol nu : hauteur des toits retirée du modèle de surface sur {correction['pixels_corriges']} pixel(s), "
                                   f"jusqu'à {correction['correction_max_m']} m (données Open Buildings 2.5D)")
            info = {"sol_nu": correction, "batiments25d_couverture": round(batiments25d.Hauteurs(bat).couverture(), 4) if bat is not None else None,"relief": "copernicus_glo30", "resolution_m": 30, "altitudes_m": alt.stats(), "empreinte": alt.empreinte(),
                    "lissage_pixels": float(ctx.config.option("relief", "lissage", 1.0)),
                    "enveloppe_basse_pixels": int(ctx.config.option("relief", "enveloppe", 1))}
            ctx.journal.record("info", "relief", f"modèle d'altitude chargé : de {info['altitudes_m']['min']} à {info['altitudes_m']['max']} m, "
                               f"moyenne {info['altitudes_m']['moyenne']} m (résolution de 30 m)")
    (out / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return info
