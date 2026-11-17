"""Petits décors urbains très légers (arbres, poteaux, étals...) pour une ville d'Afrique de l'Ouest.

Chaque décor renvoie une liste de morceaux (triangles, couleur) : triangles est un tableau (T, 3, 3)
en mètres, posé sur z = 0 et centré sur l'origine en x, y ; couleur est un tuple (r, v, b) sRGB entre 0 et 1.
"""
from __future__ import annotations

import math
import random

import numpy as np
from shapely.affinity import rotate
from shapely.geometry import Polygon

from .mesh import MeshBuilder

Morceau = tuple[np.ndarray, tuple[float, float, float]]


def _teinte(rng: random.Random, base, ecart: float = 0.04) -> tuple[float, float, float]:
    """Couleur de base légèrement variée, bornée entre 0 et 1."""
    return tuple(min(1.0, max(0.0, c + rng.uniform(-ecart, ecart))) for c in base)


def _box(cx, cy, z0, z1, lx, ly, angle=0.0) -> np.ndarray:
    """Boîte fermée par le dessus et les côtés (10 triangles), tournée de `angle` radians autour de z."""
    poly = Polygon([(cx - lx / 2, cy - ly / 2), (cx + lx / 2, cy - ly / 2),
                    (cx + lx / 2, cy + ly / 2), (cx - lx / 2, cy + ly / 2)])
    if angle:
        poly = rotate(poly, angle, origin=(cx, cy), use_radians=True)
    b = MeshBuilder("boite")
    b.add_prism(poly, z0, z1, (0, 0, 0), (0, 0, 0))
    return b.triangles


def _polygone_regulier(cx, cy, rayon, cotes) -> list[tuple[float, float]]:
    return [(cx + rayon * math.cos(2 * math.pi * i / cotes), cy + rayon * math.sin(2 * math.pi * i / cotes))
            for i in range(cotes)]


def _prism(cx, cy, z0, z1, rayon, cotes, haut: bool = True) -> np.ndarray:
    """Prisme régulier à `cotes` faces (tronc, poteau), fermé par le dessus si `haut`."""
    poly = Polygon(_polygone_regulier(cx, cy, rayon, cotes))
    b = MeshBuilder("prisme")
    if haut:
        b.add_prism(poly, z0, z1, (0, 0, 0), (0, 0, 0))
    else:
        b.add_walls(poly, z0, z1, (0, 0, 0))
    return b.triangles


def _cone(cx, cy, z0, z1, rayon, cotes) -> np.ndarray:
    """Cône à base régulière (côtés seulement, normales vers l'extérieur)."""
    pts = _polygone_regulier(cx, cy, rayon, cotes)
    sommet = (cx, cy, z1)
    tris = [[(*pts[i], z0), (*pts[(i + 1) % cotes], z0), sommet] for i in range(cotes)]
    return np.asarray(tris, dtype=np.float64)


def _lame(angle, longueur, largeur, z, pente: float = 0.0) -> np.ndarray:
    """Palme plate en losquange allongé partant de l'origine (4 triangles, dessus et dessous)."""
    c, s = math.cos(angle), math.sin(angle)

    def p(u, v, dz=0.0):
        return (u * c - v * s, u * s + v * c, z + dz)

    base = p(0.0, 0.0)
    gauche = p(longueur * 0.4, largeur / 2, longueur * 0.4 * pente)
    droite = p(longueur * 0.4, -largeur / 2, longueur * 0.4 * pente)
    pointe = p(longueur, 0.0, longueur * pente)
    dessus = [[base, droite, gauche], [droite, pointe, gauche]]
    dessous = [[base, gauche, droite], [droite, gauche, pointe]]
    return np.asarray(dessus + dessous, dtype=np.float64)


def place(morceaux, x, y, angle=0.0):
    """Morceaux tournés de `angle` autour de z puis déplacés en (x, y)."""
    c, s = math.cos(angle), math.sin(angle)
    sortie = []
    for tris, couleur in morceaux:
        t = np.array(tris, dtype=np.float64)
        px, py = t[..., 0].copy(), t[..., 1].copy()
        t[..., 0] = px * c - py * s + x
        t[..., 1] = px * s + py * c + y
        sortie.append((t, couleur))
    return sortie


def arbre(rng: random.Random) -> list[Morceau]:
    """Arbre : tronc brun et houppier fait de deux cônes empilés (29 triangles)."""
    h_tronc = rng.uniform(2.0, 3.5)
    r_tronc = rng.uniform(0.15, 0.25)
    r_cime = rng.uniform(1.8, 3.0)
    h_total = rng.uniform(5.0, 8.0)
    h_total = max(h_total, h_tronc + 2.0)
    mi = h_tronc + (h_total - h_tronc) * 0.5
    vert = _teinte(rng, (0.18, 0.42, 0.16), 0.05)
    vert_haut = _teinte(rng, (0.22, 0.48, 0.18), 0.05)
    return [
        (_prism(0, 0, 0.0, h_tronc + 0.3, r_tronc, 5), _teinte(rng, (0.33, 0.22, 0.13))),
        (_cone(0, 0, h_tronc, mi + 0.8, r_cime, 8), vert),
        (_cone(0, 0, mi, h_total, r_cime * 0.65, 8), vert_haut),
    ]


def palmier(rng: random.Random) -> list[Morceau]:
    """Palmier : tronc fin et 5 à 6 palmes rayonnant au sommet (30 triangles au plus)."""
    haut = rng.uniform(6.0, 9.0)
    r = rng.uniform(0.12, 0.18)
    morceaux = [(_prism(0, 0, 0.0, haut, r, 4), _teinte(rng, (0.45, 0.35, 0.24)))]
    n = rng.choice([5, 6])
    depart = rng.uniform(0, 2 * math.pi)
    vert = _teinte(rng, (0.20, 0.45, 0.17), 0.05)
    for i in range(n):
        a = depart + 2 * math.pi * i / n + rng.uniform(-0.15, 0.15)
        morceaux.append((_lame(a, 2.5, 0.5, haut, pente=-0.15), vert))
    return morceaux


def poteau_electrique(rng: random.Random) -> list[Morceau]:
    """Poteau béton de section carrée et traverse horizontale (20 triangles)."""
    h = rng.uniform(8.0, 9.0)
    gris = _teinte(rng, (0.58, 0.58, 0.56))
    return [
        (_box(0, 0, 0.0, h, 0.25, 0.25), gris),
        (_box(0, 0, h - 0.6, h - 0.45, 1.6, 0.1), _teinte(rng, (0.35, 0.28, 0.2))),
    ]


def lampadaire(rng: random.Random) -> list[Morceau]:
    """Lampadaire : mât, bras et tête (30 triangles)."""
    gris = _teinte(rng, (0.28, 0.29, 0.30))
    return [
        (_prism(0, 0, 0.0, 7.0, 0.08, 4), gris),
        (_box(0.6, 0, 6.9, 7.0, 1.2, 0.08), gris),
        (_box(1.2, 0, 6.8, 6.95, 0.5, 0.25), _teinte(rng, (0.85, 0.82, 0.65))),
    ]


def etal(rng: random.Random) -> list[Morceau]:
    """Étal : plateau de bois, quatre montants à 2,1 m et toit de tôle (48 triangles)."""
    bois = _teinte(rng, (0.50, 0.34, 0.20))
    tole = _teinte(rng, rng.choice([(0.55, 0.57, 0.58), (0.50, 0.28, 0.16), (0.40, 0.50, 0.58)]))
    morceaux = [
        (_box(0, 0, 0.75, 0.8, 1.8, 0.9), bois),
        (_box(0, 0, 2.1, 2.15, 2.2, 1.3), tole),
    ]
    for sx in (-0.85, 0.85):
        for sy in (-0.4, 0.4):
            morceaux.append((_prism(sx, sy, 0.0, 2.1, 0.04, 3), bois))
    return morceaux


def panneau(rng: random.Random) -> list[Morceau]:
    """Panneau : poteau fin et plaque en haut (20 triangles)."""
    plaque = rng.choice([(0.92, 0.90, 0.82), (0.93, 0.78, 0.15), (0.15, 0.35, 0.70)])
    return [
        (_prism(0, 0, 0.0, 2.2, 0.04, 4), _teinte(rng, (0.35, 0.35, 0.37))),
        (_box(0, 0.06, 1.6, 2.2, 0.6, 0.05), _teinte(rng, plaque, 0.02)),
    ]


def tas_dechets(rng: random.Random) -> list[Morceau]:
    """Tas de déchets : 3 à 4 petits volumes bas de teintes ternes (28 triangles au plus)."""
    morceaux = []
    for _ in range(rng.randint(3, 4)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.0, 0.5)
        h = rng.uniform(0.2, 0.6)
        r = rng.uniform(0.12, 0.28)
        gris = rng.uniform(0.25, 0.5)
        couleur = _teinte(rng, (gris + 0.05, gris, gris - 0.05), 0.03)
        morceaux.append((_prism(d * math.cos(a), d * math.sin(a), 0.0, h, r, 3), couleur))
    return morceaux


CATALOGUE = {
    "arbre": arbre,
    "palmier": palmier,
    "poteau_electrique": poteau_electrique,
    "lampadaire": lampadaire,
    "etal": etal,
    "panneau": panneau,
    "tas_dechets": tas_dechets,
}

_EMPRISES = {
    "arbre": 2.5, "palmier": 2.0, "poteau_electrique": 0.9, "lampadaire": 0.7,
    "etal": 1.4, "panneau": 0.4, "tas_dechets": 0.9,
}


def emprise(nom: str) -> float:
    """Rayon au sol approximatif (mètres), pour éviter les collisions au placement."""
    return _EMPRISES[nom]
