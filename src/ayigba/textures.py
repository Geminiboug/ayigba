"""Textures de grain générées par le code (phase 2 des textures, version simple et sans licence tierce).

Pourquoi : une carte faite d'aplats de couleur paraît lisse et artificielle. Un léger grain (crépi, asphalte, sable) donne de
l'échelle et de la matière SANS changer la couleur moyenne : la texture est un gris clair qui se MULTIPLIE avec la couleur du
matériau (baseColorFactor x baseColorTexture en glTF). Les textures sont fabriquées ici par filtrage d'un bruit blanc dans
l'espace de Fourier : elles se raccordent donc parfaitement (périodiques) et sont déterministes pour une graine donnée.
Rien n'est copié depuis une photo ou une bibliothèque : aucune licence à respecter.

Limites : ce sont des motifs de grain, pas des matériaux réels (pas de briques, de tôle ondulée, de joints de pavés), et aucune
photo de terrain n'a servi à les étalonner. Elles ne portent que de la variation de luminosité.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

# nom -> (gris moyen, écart-type, fréquence de coupure relative 0..1 : petit = grain gros, grand = grain fin, taille de tuile en mètres)
TYPES = {
    "crepi":    (0.93, 0.035, 0.18, 3.0),
    "asphalte": (0.90, 0.060, 0.45, 2.0),
    "sol":      (0.92, 0.045, 0.10, 6.0),
    "beton":    (0.92, 0.040, 0.30, 2.5),
}

# couche de la carte -> type de texture (les autres couches, comme l'eau, restent des aplats)
PAR_COUCHE = {"batiments": "crepi", "chaussees": "asphalte", "trottoirs": "beton", "terrain": "sol", "berges": "sol"}


def type_pour_couche(nom: str) -> str | None:
    return PAR_COUCHE.get(nom)


def tuile_m(type_: str) -> float:
    return TYPES[type_][3]


def grain(type_: str, taille: int = 128, graine: int = 1) -> np.ndarray:
    """Image en niveaux de gris (taille x taille), valeurs entre 0 et 1, périodique."""
    moy, ecart, coupure, _ = TYPES[type_]
    rng = np.random.default_rng(graine * 7919 + sum(map(ord, type_)))
    bruit = rng.standard_normal((taille, taille))
    spectre = np.fft.fft2(bruit)
    f = np.hypot(*np.meshgrid(np.fft.fftfreq(taille), np.fft.fftfreq(taille))) * 2.0   # 0 .. ~1,4
    filtre = np.exp(-((f / max(coupure, 1e-3)) ** 2))                                   # passe-bas doux
    filtre[0, 0] = 0.0                                                                  # pas de composante moyenne
    img = np.real(np.fft.ifft2(spectre * filtre))
    img = img / (img.std() + 1e-12) * ecart + moy
    return np.clip(img, 0.0, 1.0)


def png_octets(type_: str, taille: int = 128, graine: int = 1) -> bytes:
    a = (grain(type_, taille, graine) * 255.0 + 0.5).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(a, mode="L").convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def uv_planaires(sommets: np.ndarray, normales: np.ndarray, tuile: float) -> np.ndarray:
    """Coordonnées de texture en repère LOCAL (x est, y nord, z haut) : projection sur le plan le plus face à la normale.
    Dessus et dessous : (x, y) ; murs : (x, z) ou (y, z). Un mètre de la carte vaut 1/tuile unité de texture."""
    n = np.abs(normales)
    haut = (n[:, 2] >= n[:, 0]) & (n[:, 2] >= n[:, 1])
    est = (~haut) & (n[:, 0] >= n[:, 1])
    u = np.where(haut | est, np.where(est, sommets[:, 1], sommets[:, 0]), sommets[:, 0])
    v = np.where(haut, sommets[:, 1], sommets[:, 2])
    return (np.column_stack([u, v]) / tuile).astype(np.float32)
