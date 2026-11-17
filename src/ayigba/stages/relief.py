"""Étape « relief » : obtenir le modèle numérique d'altitude de la zone (Copernicus GLO-30, 30 m), avec cache.

Sorties : work/relief/info.json (statistiques) ; le modèle lui-même reste dans cache/dem_copernicus.npz.
Sans modèle (hors ligne et pas de cache, ou option désactivée) la carte reste plate : c'est écrit dans le journal et le rapport.
Options de config.toml : [relief] actif (vrai par défaut), lissage (pixels, 1.0 par défaut), enveloppe (pixels, 1 par défaut :
enveloppe basse locale qui retire les bosses dues aux bâtiments et aux arbres, 0 pour garder le modèle brut).
"""
from __future__ import annotations

import json

from .. import dem
from ..geo import LocalFrame

STAGE = "relief"


def altitudes(ctx, frame: LocalFrame):
    """Fonction d'altitude du projet : le modèle en cache, ou un sol plat à zéro."""
    path = ctx.project.cache / "dem_copernicus.npz"
    if bool(ctx.config.option("relief", "actif", True)) and path.is_file():
        return dem.Altitudes(dem.charger(path), frame, lissage=float(ctx.config.option("relief", "lissage", 1.0)),
                             enveloppe=int(ctx.config.option("relief", "enveloppe", 1)))
    return dem.Altitudes.plat(0.0)


def run(ctx) -> dict:
    out = ctx.project.stage_dir(STAGE)
    frame = LocalFrame(ctx.config.bbox)
    if not bool(ctx.config.option("relief", "actif", True)):
        ctx.journal.record("info", "relief", "relief désactivé dans la configuration ([relief] actif = false) : terrain plat")
        info = {"relief": "desactive"}
    else:
        model = dem.obtenir(ctx)
        if model is None:
            ctx.journal.record("info", "relief", "aucun modèle d'altitude en cache et mode hors ligne : terrain plat. Relance une fois sans --hors-ligne pour le télécharger.")
            info = {"relief": "plat", "raison": "pas de modèle d'altitude en cache"}
        else:
            alt = altitudes(ctx, frame)
            info = {"relief": "copernicus_glo30", "resolution_m": 30, "altitudes_m": alt.stats(), "empreinte": alt.empreinte(),
                    "lissage_pixels": float(ctx.config.option("relief", "lissage", 1.0)),
                    "enveloppe_basse_pixels": int(ctx.config.option("relief", "enveloppe", 1))}
            ctx.journal.record("info", "relief", f"modèle d'altitude chargé : de {info['altitudes_m']['min']} à {info['altitudes_m']['max']} m, "
                               f"moyenne {info['altitudes_m']['moyenne']} m (résolution de 30 m)")
    (out / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return info
