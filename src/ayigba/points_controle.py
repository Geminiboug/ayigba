"""Points de contrôle pour le scanner d'objets flottants de Godot (`verif/godot/flottants.gd`).

`ayigba points-controle projects/<ville>` écrit `reports/points_controle.json` : une liste d'objets posés de la carte générée, en repère
Godot (x est, y altitude, z = -nord), avec l'altitude attendue :
  - chaque décor (arbre, poteau, lampadaire...) : y = altitude `z` du sol écrite dans decors.geojson, mode « sol » ;
  - chaque bâtiment : le point haut du toit au centre de l'emprise (si le centre est dans l'emprise), y = `sommet_max` (ou `sommet` + `faitage_m`
    pour les cartes générées avant l'ajout de `sommet_max`), mode « toit ».
Godot lance alors des rayons verticaux dans les collisions de la carte et signale tout écart supérieur à la tolérance.
Ce contrôle ne dit pas si la carte est fidèle à la réalité, seulement si ce qui est posé repose bien sur ce qui est dessous.
"""
from __future__ import annotations

import json
from pathlib import Path

from .geo import LocalFrame, read_features
from .project import Project, open_context


def construire(projet_dossier: Path) -> list[dict]:
    dossier = Path(projet_dossier).resolve()
    project = Project(dossier)
    ctx = open_context(dossier, offline=True)
    frame = LocalFrame(ctx.config.bbox)
    out = project.out / "neutre"
    if not (out / "batiments.geojson").is_file():
        raise LookupError(f"Pas de résultat dans {out} : lance d'abord « ayigba generer {projet_dossier} ».")
    points: list[dict] = []
    f = out / "decors.geojson"
    if f.is_file():
        for g, p in read_features(f):
            if g.geom_type != "Point" or p.get("z") is None:
                continue
            x, y = frame.to_local(g.x, g.y)
            points.append({"id": str(p.get("id", "")), "genre": str(p.get("type", "decor")), "x": round(float(x), 2), "y": float(p["z"]),
                           "z": round(-float(y), 2), "mode": "sol"})
    for g, p in read_features(out / "batiments.geojson"):
        if g.geom_type not in ("Polygon", "MultiPolygon") or p.get("type") == "roof":
            continue
        haut = p.get("sommet_max")
        if haut is None and p.get("sommet") is not None:
            haut = float(p["sommet"]) + float(p.get("faitage_m") or 0.0)
        if haut is None:
            continue
        c = g.centroid
        if not g.contains(c):
            continue
        x, y = frame.to_local(c.x, c.y)
        points.append({"id": str(p.get("id", "")), "genre": "toit_" + ("deux_pentes" if p.get("toit") == "deux_pentes" else "plat"),
                       "x": round(float(x), 2), "y": float(haut), "z": round(-float(y), 2), "mode": "toit"})
    return points


def ecrire(projet_dossier: Path, sortie: Path | None = None) -> Path:
    points = construire(projet_dossier)
    if not points:
        raise LookupError("Aucun objet à contrôler dans ce projet.")
    f = sortie or (Project(Path(projet_dossier).resolve()).reports / "points_controle.json")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    return f
