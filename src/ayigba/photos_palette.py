"""Palette de couleurs tirée de photos de référence (phase 3 des textures, version simple).

Pourquoi : les données libres ne donnent pas la couleur des murs et des toits (voir style.py). Des photos de rue du lieu
permettent de PROPOSER une palette plus fidèle que le préréglage régional. Ce module ne décide rien : il écrit une
suggestion (`[style] murs` et `toits`) que l'on relit avant de la copier dans config.toml.

Méthode, volontairement simple et honnête :
- chaque photo est réduite (256 px), puis on écarte ce qui n'est pas façade ou toit : ciel (bleu clair ou blanc dans le tiers
  haut), végétation (teinte verte saturée), ombres très sombres, pixels presque blancs brûlés, personnes et véhicules ne sont
  PAS détectés (limite) ;
- les pixels restants sont regroupés par k-moyennes dans l'espace Lab (distance proche de la perception) ;
- sur toutes les photos d'un lieu, les groupes proches sont fusionnés et pondérés par leur part de pixels ;
- les murs sont les couleurs claires à moyennes (luminance >= 0,45), les toits les couleurs plus sombres (< 0,45) ou rouges
  de tuile et de tôle rouillée. C'est une règle de luminance, pas une segmentation : une façade sombre devient un « toit ».
Aucune photo n'est copiée ni redistribuée par ce module : seules des couleurs (nombres) sortent.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from PIL import Image

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _srgb_vers_lineaire(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lineaire_vers_srgb(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055)


_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_BLANC = np.array([0.95047, 1.0, 1.08883])


def rgb_vers_lab(rgb: np.ndarray) -> np.ndarray:
    xyz = (_srgb_vers_lineaire(rgb) @ _M.T) / _BLANC
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def lab_vers_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[:, 0] + 16) / 116
    f = np.stack([fy + lab[:, 1] / 500, fy, fy - lab[:, 2] / 200], axis=1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _BLANC
    return np.clip(_lineaire_vers_srgb(xyz @ np.linalg.inv(_M).T), 0.0, 1.0)


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def pixels_utiles(chemin: Path, taille: int = 256) -> np.ndarray:
    """Pixels RGB (0..1) d'une photo, sans ciel, végétation, ombres profondes ni zones brûlées. Tableau (n, 3)."""
    im = Image.open(chemin).convert("RGB")
    im.thumbnail((taille, taille))
    a = np.asarray(im, dtype=np.float64) / 255.0
    h = a.shape[0]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    lum = _luminance(a)
    haut = np.zeros(a.shape[:2], bool)
    haut[: max(1, h // 3)] = True
    ciel = haut & (((b >= r) & (b >= g * 0.95) & (lum > 0.45)) | ((sat < 0.12) & (lum > 0.80)))   # bleu clair ou blanc haut
    vert = (g > r * 1.05) & (g > b * 1.08) & (sat > 0.18)
    sombre = lum < 0.10
    brule = (mn > 0.96)
    ok = ~(ciel | vert | sombre | brule)
    return a[ok]


def kmoyennes(lab: np.ndarray, k: int, graine: int = 1, iterations: int = 25) -> tuple[np.ndarray, np.ndarray]:
    """Centres (k, 3) et parts (k,) ; déterministe."""
    if len(lab) == 0:
        return np.zeros((0, 3)), np.zeros(0)
    rng = np.random.default_rng(graine)
    k = min(k, len(lab))
    centres = lab[rng.choice(len(lab), size=k, replace=False)]
    for _ in range(iterations):
        d = ((lab[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        etiq = d.argmin(axis=1)
        neuf = np.array([lab[etiq == i].mean(axis=0) if np.any(etiq == i) else centres[i] for i in range(k)])
        if np.allclose(neuf, centres, atol=0.05):
            centres = neuf
            break
        centres = neuf
    etiq = ((lab[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    parts = np.bincount(etiq, minlength=k) / len(lab)
    return centres, parts


def couleurs_photo(chemin: Path, k: int = 6) -> list[tuple[tuple[float, float, float], float]]:
    px = pixels_utiles(chemin)
    if len(px) < 200:
        return []
    if len(px) > 20000:
        px = px[np.random.default_rng(1).choice(len(px), 20000, replace=False)]
    centres, parts = kmoyennes(rgb_vers_lab(px), k)
    rgb = lab_vers_rgb(centres)
    return [(tuple(float(x) for x in rgb[i]), float(parts[i])) for i in range(len(centres))]


def fusionner(couleurs: list[tuple[tuple[float, float, float], float]], n: int, seuil_lab: float = 9.0) -> list[tuple[tuple[float, float, float], float]]:
    """Fusionne les couleurs proches (distance Lab < seuil), garde les n plus pesantes."""
    if not couleurs:
        return []
    rgb = np.array([c for c, _ in couleurs])
    poids = np.array([p for _, p in couleurs])
    lab = rgb_vers_lab(rgb)
    ordre = np.argsort(-poids)
    groupes: list[list[int]] = []
    for i in ordre:
        for gr in groupes:
            if np.linalg.norm(lab[i] - lab[gr[0]]) < seuil_lab:
                gr.append(i)
                break
        else:
            groupes.append([i])
    sortie = []
    for gr in groupes:
        w = poids[gr]
        moy = (rgb[gr] * w[:, None]).sum(axis=0) / w.sum()
        sortie.append((tuple(float(x) for x in moy), float(w.sum())))
    sortie.sort(key=lambda t: -t[1])
    return sortie[:n]


def palette_du_lieu(dossier: Path, n_murs: int = 7, n_toits: int = 5) -> dict:
    """Palette suggérée pour les photos d'un dossier (récursif). Retourne murs, toits, nombre de photos et limites."""
    photos = sorted(p for p in Path(dossier).rglob("*") if p.suffix.lower() in EXTENSIONS)
    toutes: list[tuple[tuple[float, float, float], float]] = []
    utilisees = 0
    for p in photos:
        try:
            c = couleurs_photo(p)
        except Exception:
            continue
        if c:
            utilisees += 1
            toutes.extend(c)
    murs_c = [(c, w) for c, w in toutes if _luminance(np.array(c)) >= 0.45]
    toits_c = [(c, w) for c, w in toutes if _luminance(np.array(c)) < 0.45]
    return {
        "photos": len(photos), "photos_utilisees": utilisees,
        "murs": fusionner(murs_c, n_murs), "toits": fusionner(toits_c, n_toits),
    }


def hex_couleur(c: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, x)) * 255)):02x}" for x in c)


def ecrire_suggestion(res: dict, lieu: str, chemin: Path) -> None:
    lignes = [
        f"# Palette SUGGÉRÉE d'après {res['photos_utilisees']} photo(s) sur {res['photos']} ({lieu}).",
        "# À relire avant de copier dans config.toml : règle de luminance, pas de segmentation (voir photos_palette.py).",
        "[style]",
        "murs = [" + ", ".join(f'"{hex_couleur(c)}"' for c, _ in res["murs"]) + "]",
        "toits = [" + ", ".join(f'"{hex_couleur(c)}"' for c, _ in res["toits"]) + "]",
        "",
    ]
    Path(chemin).write_text("\n".join(lignes), encoding="utf-8")


def lire_index(dossier: Path) -> list[dict]:
    f = Path(dossier) / "INDEX.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
