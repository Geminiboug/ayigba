"""Sources d'empreintes de bâtiments interchangeables, et leur fusion.

Aucune source libre ne couvre bien tous les pays : OpenStreetMap est complet à certains endroits et vide ailleurs, Microsoft
et Google comblent des trous, Overture fusionne plusieurs jeux. Ce module donne à toutes les sources la même forme, pour qu'on
puisse en ajouter une en écrivant UN fichier, sans toucher au pipeline.

Écrire une source :

    from ayigba.empreintes import Empreinte, SourceEmpreintes, enregistrer

    @enregistrer
    class MaSource(SourceEmpreintes):
        id = "ma_source"
        nom = "Ma source"
        licence = "CC BY 4.0"
        url_licence = "https://creativecommons.org/licenses/by/4.0/"
        attribution = "Ma source (2026), CC BY 4.0"
        url_source = "https://exemple.org"

        def collecter(self, ctx, frame, zone) -> list[Empreinte]:
            ...  # télécharge (cache dans ctx.project.cache), renvoie des polygones en repère LOCAL (mètres)

La source est ensuite activée dans config.toml : `[empreintes] sources = ["ma_source"]`. L'ordre compte : une source plus haut
dans la liste l'emporte sur les suivantes quand deux bâtiments se recouvrent. OpenStreetMap passe toujours en premier.

Règles de fusion (`fusionner`), les mêmes pour toutes les sources, jamais cachées :
- un candidat qui recouvre à plus de `recouvrement_max` de sa surface des bâtiments déjà retenus est écarté (doublon) ;
- un candidat qui en recouvre moins est DÉCOUPÉ : la partie qui chevauche est retirée (le contrôle de qualité refuse toute
  superposition de bâtiments). `fusionner` remplace alors `geom` du candidat par la partie conservée ; si ce qui reste est
  trop petit ou en morceaux dispersés, le candidat est écarté (motif « doublon ») ;
- un candidat sur une chaussée ou dans l'eau (`interdit`) est écarté ;
- surface hors de [aire_min, aire_max], géométrie invalide ou vide : écarté ;
- ordre déterministe (position), donc même entrée = même sortie.
Chaque rejet est compté par motif et journalisé par l'appelant.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import ClassVar

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .sources import register_source

AIRE_MIN_M2 = 8.0
AIRE_MAX_M2 = 5000.0
RECOUVREMENT_MAX = 0.30
INTERDIT_MAX = 0.30
TOLERANCE_M2 = 0.2          # un chevauchement plus petit que cela est du bruit de tracé : on ne découpe pas
MARGE_COUPE_M = 0.05        # marge laissée entre un candidat découpé et le bâtiment qu'il touchait


@dataclass
class Empreinte:
    """Un bâtiment candidat, en repère local (mètres). `hauteur` en mètres si la source la donne vraiment, sinon None."""
    geom: Polygon
    hauteur: float | None = None
    identifiant: str = ""
    extra: dict = field(default_factory=dict)


class SourceEmpreintes:
    """Classe de base d'une source. Les attributs de licence sont OBLIGATOIRES : ils alimentent CREDITS.md automatiquement."""
    id: ClassVar[str] = ""
    nom: ClassVar[str] = ""
    licence: ClassVar[str] = ""
    url_licence: ClassVar[str] = ""
    attribution: ClassVar[str] = ""
    url_source: ClassVar[str] = ""

    def collecter(self, ctx, frame, zone) -> list[Empreinte]:  # pragma: no cover - interface
        raise NotImplementedError

    def enregistrer_credit(self, ctx, nombre: int, date: str | None = None) -> None:
        """Inscrit la source dans data/sources.json (donc dans CREDITS.md) : à appeler par `collecter` une fois les données reçues."""
        register_source(ctx.project.data, {
            "id": self.id, "nom": self.nom, "licence": self.licence, "url_licence": self.url_licence,
            "attribution": self.attribution, "url_source": self.url_source,
            "date_collecte": date or datetime.date.today().isoformat(), "zone": list(ctx.config.bbox), "elements": int(nombre),
        })


REGISTRE: dict[str, type[SourceEmpreintes]] = {}


def enregistrer(cls: type[SourceEmpreintes]) -> type[SourceEmpreintes]:
    """Décorateur : ajoute une source au registre. Refuse une source sans identifiant ou sans licence complète."""
    manquants = [k for k in ("id", "nom", "licence", "url_licence", "attribution", "url_source") if not getattr(cls, k, "")]
    if manquants:
        raise ValueError(f"source d'empreintes {cls.__name__} incomplète, attributs manquants : {', '.join(manquants)}")
    if cls.id in REGISTRE and REGISTRE[cls.id] is not cls:
        raise ValueError(f"source d'empreintes en double : {cls.id}")
    REGISTRE[cls.id] = cls
    return cls


def disponibles() -> list[type[SourceEmpreintes]]:
    _charger_sources_integrees()
    return [REGISTRE[k] for k in sorted(REGISTRE)]


def obtenir(identifiant: str) -> SourceEmpreintes:
    _charger_sources_integrees()
    if identifiant not in REGISTRE:
        raise KeyError(f"source d'empreintes inconnue : « {identifiant} ». Disponibles : {', '.join(sorted(REGISTRE)) or 'aucune'}")
    return REGISTRE[identifiant]()


def _charger_sources_integrees() -> None:
    """Importe les modules de sources livrés avec l'outil (leur import les enregistre)."""
    import importlib
    for nom in ("ayigba.sources_empreintes.microsoft",):
        try:
            importlib.import_module(nom)
        except ModuleNotFoundError as exc:
            if exc.name is None or not nom.startswith(exc.name):
                raise  # un module de la source qui échoue à importer autre chose est une vraie erreur


def fusionner(existants: list[BaseGeometry], candidats: list[Empreinte], interdit: BaseGeometry | None = None,
              aire_min: float = AIRE_MIN_M2, aire_max: float = AIRE_MAX_M2, recouvrement_max: float = RECOUVREMENT_MAX,
              interdit_max: float = INTERDIT_MAX) -> tuple[list[int], dict[str, int]]:
    """Choisit parmi `candidats` ceux à ajouter à `existants`. Retourne (indices gardés dans l'ordre d'origine, rejets par motif).

    Un candidat retenu compte comme existant pour les suivants : deux candidats qui se recouvrent entre eux ne passent pas
    tous les deux. Le parcours suit l'ordre de position (x, puis y) pour être déterministe quel que soit l'ordre d'entrée.
    """
    rejets = {"invalide": 0, "surface": 0, "doublon": 0, "chaussee_ou_eau": 0}
    ordre = sorted(range(len(candidats)), key=lambda i: (round(candidats[i].geom.centroid.x, 3), round(candidats[i].geom.centroid.y, 3), i)
                   if not candidats[i].geom.is_empty else (0.0, 0.0, i))
    base: list[BaseGeometry] = list(existants)
    retenus = _Grille()
    gardes: list[int] = []
    arbre_base = STRtree(base) if base else None
    for i in ordre:
        g = candidats[i].geom
        if g is None or g.is_empty or not g.is_valid or g.geom_type not in ("Polygon", "MultiPolygon"):
            rejets["invalide"] += 1
            continue
        a = g.area
        if a < aire_min or a > aire_max:
            rejets["surface"] += 1
            continue
        if interdit is not None and not interdit.is_empty and g.intersection(interdit).area > interdit_max * a:
            rejets["chaussee_ou_eau"] += 1
            continue
        voisins = _voisins(g, arbre_base, base) + retenus.proches(g)
        chevauche = [h for h in voisins if g.intersects(h) and g.intersection(h).area > 1e-6]
        total = sum(g.intersection(h).area for h in chevauche)
        if total > recouvrement_max * a:
            rejets["doublon"] += 1
            continue
        if total > TOLERANCE_M2:
            reste = g.difference(unary_union(chevauche).buffer(MARGE_COUPE_M))
            parts = [p for p in (reste.geoms if hasattr(reste, "geoms") else [reste]) if p.geom_type == "Polygon" and not p.is_empty]
            if not parts:
                rejets["doublon"] += 1
                continue
            g = max(parts, key=lambda p: p.area)
            if g.area < aire_min or g.area < (1.0 - recouvrement_max) * a:
                rejets["doublon"] += 1
                continue
            candidats[i].geom = g
        gardes.append(i)
        retenus.ajouter(g)
    return sorted(gardes), rejets


def _voisins(g: BaseGeometry, arbre: STRtree | None, liste: list[BaseGeometry]) -> list[BaseGeometry]:
    if not liste or arbre is None:
        return []
    return [liste[int(j)] for j in arbre.query(g)]


class _Grille:
    """Index spatial incrémental (cases de 40 m) pour les candidats déjà retenus."""
    CASE = 40.0

    def __init__(self):
        self._cases: dict[tuple[int, int], list[BaseGeometry]] = {}

    def _cles(self, g: BaseGeometry):
        x0, y0, x1, y1 = g.bounds
        for i in range(int(x0 // self.CASE), int(x1 // self.CASE) + 1):
            for j in range(int(y0 // self.CASE), int(y1 // self.CASE) + 1):
                yield (i, j)

    def ajouter(self, g: BaseGeometry) -> None:
        for k in self._cles(g):
            self._cases.setdefault(k, []).append(g)

    def proches(self, g: BaseGeometry) -> list[BaseGeometry]:
        vus, res = set(), []
        for k in self._cles(g):
            for h in self._cases.get(k, ()):
                if id(h) not in vus:
                    vus.add(id(h))
                    res.append(h)
        return res
