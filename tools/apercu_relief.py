"""Aperçu du relief d'un projet : carte d'altitude vue du dessus, avec l'eau, les routes et les bâtiments.

  .venv/bin/python tools/apercu_relief.py projects/ouidah-benin [sortie.png]

Les altitudes sont celles du maillage du sol (terrain, chaussées, trottoirs), donc ce qu'un moteur affichera vraiment.
Demande matplotlib (outil de développement, pas du pipeline) : .venv/bin/pip install matplotlib
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LightSource, LinearSegmentedColormap  # noqa: E402

from ayigba.geo import read_features  # noqa: E402
from ayigba.mesh import load_mesh  # noqa: E402


def main(projet: Path, sortie: Path) -> None:
    gen = projet / "work" / "generation"
    tris = np.concatenate([load_mesh(gen / f"{n}.npz")[0] for n in ("terrain", "chaussees", "trottoirs")])
    # grille d'altitude par moyenne des sommets de chaque triangle (suffisant pour un aperçu)
    x = tris[:, :, 0].reshape(-1)
    y = tris[:, :, 1].reshape(-1)
    z = tris[:, :, 2].reshape(-1)
    pas = 6.0
    nx, ny = int((x.max() - x.min()) / pas) + 1, int((y.max() - y.min()) / pas) + 1
    i = ((x - x.min()) / pas).astype(int)
    j = ((y - y.min()) / pas).astype(int)
    somme = np.zeros((ny, nx))
    nb = np.zeros((ny, nx))
    np.add.at(somme, (j, i), z)
    np.add.at(nb, (j, i), 1)
    grille = np.where(nb > 0, somme / np.maximum(nb, 1), np.nan)
    # trous éventuels : remplis par la moyenne des voisines (quelques passes)
    for _ in range(6):
        manque = np.isnan(grille)
        if not manque.any():
            break
        p = np.pad(grille, 1, constant_values=np.nan)
        voisins = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        grille = np.where(manque, np.nanmean(voisins, axis=0), grille)

    couleurs = LinearSegmentedColormap.from_list("alt", ["#2f6f4f", "#b9c97a", "#e8d9a0", "#c08a4f", "#8a5a3a", "#f4efe6"])
    lo, hi = np.nanmin(grille), np.nanmax(grille)
    ls = LightSource(azdeg=315, altdeg=40)
    rgb = ls.shade(np.nan_to_num(grille, nan=lo), cmap=couleurs, vert_exag=12.0, dx=pas, dy=pas, blend_mode="soft", vmin=lo, vmax=hi)
    fig, ax = plt.subplots(figsize=(11, 11 * ny / nx + 0.8), dpi=110)
    ax.imshow(rgb, origin="lower", extent=(x.min(), x.max(), y.min(), y.max()), interpolation="bilinear")
    eau = read_features(gen / "sol.geojson")
    for g, p in eau:
        if p["genre"] == "eau":
            for q in (g.geoms if hasattr(g, "geoms") else [g]):
                ax.fill(*q.exterior.xy, color="#2c7fb8", alpha=0.9, lw=0)
    bat = [np.asarray(g.exterior.coords) for g, _ in read_features(gen / "buildings.geojson") if g.geom_type == "Polygon"]
    ax.add_collection(PolyCollection(bat, facecolors="#33333355", edgecolors="none"))
    sm = plt.cm.ScalarMappable(cmap=couleurs, norm=plt.Normalize(lo, hi))
    cb = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("altitude du sol (m)")
    ax.set_title(f"Relief de {projet.name} : de {lo:.1f} à {hi:.1f} m (modèle Copernicus 30 m, lissé)", fontsize=11)
    ax.set_xlabel("est (m)")
    ax.set_ylabel("nord (m)")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(sortie)
    print("écrit", sortie, f"altitudes {lo:.1f} à {hi:.1f} m")


if __name__ == "__main__":
    p = Path(sys.argv[1])
    main(p, Path(sys.argv[2]) if len(sys.argv) > 2 else p / "reports" / "apercu_relief.png")
