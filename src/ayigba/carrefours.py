"""Carrefours : détection des croisements, arrondi des coins de rue et passages piétons peints.

Fonctions générales : aucune règle propre à un pays ou à une ville. Tout est réglable dans `[carrefours]` de config.toml.

Un carrefour est un point où au moins trois « bras » de rues revêtues se rejoignent (une rue qui traverse compte pour deux
bras, une rue qui s'arrête contre une autre pour un). Les ponts, tunnels, chemins piétons et rues non revêtues ne comptent pas.

- `arrondir` : les coins rentrants entre deux rues (angle vif d'un croisement) sont comblés par un congé de quelques mètres,
  seulement près d'un carrefour et seulement pour de petites surfaces : l'espace entre deux chaussées parallèles
  (terre-plein, îlot) n'est jamais comblé.
- `passages` : bandes de peinture (zèbre) en travers des rues importantes, à l'entrée de chaque bras du carrefour.
  Une bande n'est gardée que si elle est entièrement sur la chaussée (jamais de bout de peinture sur un trottoir).
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.strtree import STRtree
from shapely.ops import unary_union

GRANDES_CLASSES = ("trunk", "primary", "secondary", "tertiary")
MERGE_M = 1.5            # deux croisements plus proches que cela sont un seul carrefour
BRAS_MIN_M = 1.0         # un tronçon plus court que cela ne compte pas comme bras
SONDE_M = 3.0            # distance de lecture de la direction d'un bras


@dataclass
class Bras:
    ligne: int                      # indice de la rue dans la liste `routes` donnée à `noeuds`
    direction: tuple[float, float]  # vecteur unitaire du carrefour vers l'extérieur
    longueur: float                 # longueur disponible dans cette direction (m)


@dataclass
class Carrefour:
    point: Point
    bras: list[Bras] = field(default_factory=list)


def _eligible(props: dict) -> bool:
    return (props.get("revetement") == "pave" and not props.get("tunnel") and not props.get("pont")
            and not props.get("pieton") and not props.get("rond_point"))


def noeuds(routes: list[tuple[LineString, dict]]) -> list[Carrefour]:
    """Carrefours (au moins trois bras) formés par les rues revêtues éligibles."""
    origine = [i for i, (g, p) in enumerate(routes) if g.geom_type == "LineString" and not g.is_empty and _eligible(p)]
    if len(origine) < 2:
        return []
    geoms = [routes[i][0] for i in origine]
    arbre = STRtree(geoms)
    candidats: list[Point] = []
    for i, g in enumerate(geoms):
        for j in arbre.query(g):
            j = int(j)
            if j <= i:
                continue
            inter = g.intersection(geoms[j])
            if inter.is_empty:
                continue
            pts = [inter] if inter.geom_type == "Point" else list(inter.geoms) if inter.geom_type == "MultiPoint" else []
            for p in pts:
                if p.geom_type == "Point":
                    candidats.append(p)
    # regroupe les points proches
    centres: list[list[Point]] = []
    for p in sorted(candidats, key=lambda q: (round(q.x, 1), round(q.y, 1))):
        for grp in centres:
            if grp[0].distance(p) <= MERGE_M:
                grp.append(p)
                break
        else:
            centres.append([p])
    res: list[Carrefour] = []
    arbre_pts = STRtree(geoms)
    for grp in centres:
        c = Point(sum(q.x for q in grp) / len(grp), sum(q.y for q in grp) / len(grp))
        bras: list[Bras] = []
        for k in arbre_pts.query(c.buffer(MERGE_M + 0.5)):
            k = int(k)
            g = geoms[k]
            if g.distance(c) > MERGE_M + 0.5:
                continue
            s = g.project(c)
            for sens, dispo in ((-1, s), (1, g.length - s)):
                if dispo < BRAS_MIN_M:
                    continue
                # direction = tangente de la rue au point le plus proche du carrefour (et non le vecteur vers un point
                # sondé plus loin : pour deux rues parallèles voisines, ce vecteur serait oblique)
                p0 = g.interpolate(s)
                q = g.interpolate(s + sens * min(SONDE_M, dispo))
                dx, dy = q.x - p0.x, q.y - p0.y
                n = math.hypot(dx, dy)
                if n < 1e-6:
                    continue
                bras.append(Bras(origine[k], (dx / n, dy / n), dispo))
        # deux bras presque colinéaires et superposés (rue dédoublée) ne comptent qu'une fois
        uniques: list[Bras] = []
        for b in bras:
            if not any(b.direction[0] * u.direction[0] + b.direction[1] * u.direction[1] > 0.985 for u in uniques):
                uniques.append(b)
        if len(uniques) >= 3:
            res.append(Carrefour(c, uniques))
    return res


def _a_un_bord_libre(piece: Polygon, chaussee_preparee, minimum_m: float = 0.5, pas_m: float = 0.25) -> bool:
    """Vrai si la pièce a un bord qui ne longe pas la chaussée : c'est un congé de coin. Une pièce dont tout le bord longe la
    chaussée est un îlot entouré de chaussée (terre-plein, îlot de carrefour) : on ne le comble pas.

    On échantillonne le contour tous les `pas_m` et on compte les points hors de la chaussée (déjà élargie de 1 mm et préparée :
    le test est indexé, donc rapide même sur un réseau de rues de ville entière). Une version qui recalculait un tampon de tout
    le réseau pour chaque pièce prenait 35 minutes sur un quartier dense.
    """
    anneau = piece.exterior
    n = max(int(anneau.length / pas_m), 4)
    points = shapely.line_interpolate_point(anneau, np.linspace(0.0, anneau.length, n, endpoint=False))
    hors = int((~shapely.contains(chaussee_preparee, points)).sum())
    return hors * (anneau.length / n) >= minimum_m


def arrondir(chaussee: object, carrefours: list[Carrefour], rayon_m: float = 4.0, distance_m: float = 16.0, aire_max_m2: float = 80.0):
    """Surface à AJOUTER à la chaussée pour arrondir les coins rentrants près des carrefours (None s'il n'y en a pas).

    Fermeture morphologique (élargir puis rétrécir de `rayon_m`) : elle comble les coins vifs. On ne garde que les petites
    pièces proches d'un carrefour ; l'espace entre deux chaussées parallèles est donc laissé tel quel.
    """
    if chaussee is None or chaussee.is_empty or not carrefours or rayon_m <= 0:
        return None
    ferme = chaussee.buffer(rayon_m, join_style="round").buffer(-rayon_m, join_style="round")
    ajout = ferme.difference(chaussee)
    if ajout.is_empty:
        return None
    zone = unary_union([c.point.buffer(distance_m) for c in carrefours])
    chaussee_preparee = chaussee.buffer(1e-3)
    shapely.prepare(chaussee_preparee)
    pieces = [p for p in (ajout.geoms if hasattr(ajout, "geoms") else [ajout])
              if p.geom_type == "Polygon" and p.area <= aire_max_m2 and p.area > 0.05 and p.intersects(zone)
              and _a_un_bord_libre(p, chaussee_preparee)]
    return unary_union(pieces) if pieces else None


def passages(carrefours: list[Carrefour], routes: list[tuple[LineString, dict]], chaussee: object,
             classes=GRANDES_CLASSES, largeur_min_m: float = 5.0, bande_m: float = 0.5, pas_m: float = 1.0,
             longueur_m: float = 3.0, recul_m: float = 1.5, marge_m: float = 0.8):
    """Bandes de peinture (zèbre) à l'entrée de chaque bras d'une grande rue. Retourne une géométrie ou None.

    Pour un bras de largeur w, de direction u : le passage est centré à (largeur des rues du carrefour / 2 + recul_m) du
    centre du carrefour ; les bandes sont parallèles à la rue (longueur_m), espacées de pas_m en travers, et laissent
    marge_m de chaque côté. Une bande qui sortirait de la chaussée est abandonnée (jamais de peinture sur un trottoir).
    """
    if not carrefours or chaussee is None or chaussee.is_empty:
        return None
    bandes: list[Polygon] = []
    sure = chaussee.buffer(-0.05)
    for cf in carrefours:
        largeurs = [float(routes[b.ligne][1].get("largeur", 0.0)) for b in cf.bras if b.ligne < len(routes)]
        if not largeurs:
            continue
        demi = max(largeurs) / 2.0 + recul_m
        for b in cf.bras:
            g, p = routes[b.ligne]
            w = float(p.get("largeur", 0.0))
            if p.get("classe") not in classes or w < largeur_min_m:
                continue
            if b.longueur < demi + longueur_m / 2.0 + 1.5:
                continue
            ux, uy = b.direction
            nx, ny = -uy, ux
            cx, cy = cf.point.x + ux * demi, cf.point.y + uy * demi
            n_bandes = int((w - 2 * marge_m) // pas_m) + 1
            if n_bandes < 2:
                continue
            debut = -((n_bandes - 1) * pas_m) / 2.0
            nouvelles = []
            for k in range(n_bandes):
                t = debut + k * pas_m
                mx, my = cx + nx * t, cy + ny * t
                hl, hw = longueur_m / 2.0, bande_m / 2.0
                poly = Polygon([(mx - ux * hl - nx * hw, my - uy * hl - ny * hw), (mx + ux * hl - nx * hw, my + uy * hl - ny * hw),
                                (mx + ux * hl + nx * hw, my + uy * hl + ny * hw), (mx - ux * hl + nx * hw, my - uy * hl + ny * hw)])
                if sure.contains(poly):
                    nouvelles.append(poly)
            if len(nouvelles) >= max(2, n_bandes // 2):
                bandes.extend(nouvelles)
    if not bandes:
        return None
    res = unary_union(bandes)
    return res if not res.is_empty else None
