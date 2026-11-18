"""Source d'empreintes : Microsoft Global ML Building Footprints.

Jeu de données : https://github.com/microsoft/GlobalMLBuildingFootprints (bâtiments détectés par apprentissage automatique
sur l'imagerie Bing Maps). Licence vérifiée sur la page officielle du jeu (README, section « License ») : « CDLA Permissive 2.0 »
(https://cdla.dev/permissive-2-0/). Ce n'est PAS l'ODbL (licence d'une ancienne version du jeu) : il n'y a pas d'obligation de
partage à l'identique, mais la licence demande de conserver l'avis de licence ; l'attribution ci-dessous le fait.

Fonctionnement (format réel vérifié en téléchargeant l'index et un fichier) :
- l'index `dataset-links.csv` a les colonnes Location, QuadKey, Url, Size, UploadDate (Size est un texte : « 22.6MB ») ;
  une même tuile (QuadKey de niveau 9) peut apparaître pour plusieurs pays (ex. Benin, Togo) : on prend toutes les lignes ;
- chaque Url est un fichier `.csv.gz` qui contient en réalité du GeoJSON lignes : un Feature par ligne, polygone en lon/lat,
  propriétés `height` (mètres, -1 si inconnue) et `confidence` (0 à 1, -1 si inconnue) ;
- le fichier est lu en flux et filtré par bbox au fil de l'eau ; seul le résultat filtré est gardé dans cache/microsoft/.

Réseau : la vérification SSL n'est jamais désactivée. Limite de téléchargement par essai : 300 Mo (compressés).
Option `[empreintes.microsoft] telecharger = true` : autorise le réseau pour cette source même avec --hors-ligne.
Option `[empreintes.microsoft] index_url = "..."` : autre emplacement de l'index (l'hébergement a déjà changé deux fois).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from shapely.geometry import Polygon

from .. import empreintes
from ..empreintes import Empreinte, SourceEmpreintes

NIVEAU = 9
# Index actuel d'abord (hébergement déplacé en juillet 2026), ancien emplacement en secours.
INDEX_URLS = (
    "https://bfppub.blob.core.windows.net/%24web/2026-08-13/dataset-links.csv",
    "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv",
)
LIMITE_OCTETS = 300 * 1024 * 1024
SIMPLIFICATION_M = 0.2
USER_AGENT = "ayigba/0.1 (generateur de cartes ; https://github.com/Geminiboug/ayigba)"
TIMEOUT = 120
_MARGE_LAT = 85.05112878


# --- quadkeys (système de tuiles Bing / Web Mercator) -------------------------------------------------------------------

def tuile_de(lon: float, lat: float, niveau: int = NIVEAU) -> tuple[int, int]:
    """Indices (x, y) de la tuile de ce niveau qui contient le point ; y croît vers le sud."""
    n = 1 << niveau
    lat = max(-_MARGE_LAT, min(_MARGE_LAT, lat))
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return min(n - 1, max(0, int(math.floor(x)))), min(n - 1, max(0, int(math.floor(y))))


def quadkey_de_tuile(x: int, y: int, niveau: int = NIVEAU) -> str:
    chiffres = []
    for i in range(niveau, 0, -1):
        masque = 1 << (i - 1)
        chiffres.append(str((1 if x & masque else 0) + (2 if y & masque else 0)))
    return "".join(chiffres)


def tuile_de_quadkey(quadkey: str) -> tuple[int, int, int]:
    """(x, y, niveau) d'un quadkey."""
    x = y = 0
    niveau = len(quadkey)
    for i, c in enumerate(quadkey):
        masque = 1 << (niveau - i - 1)
        if c not in "0123":
            raise ValueError(f"quadkey invalide : {quadkey!r}")
        if c in "13":
            x |= masque
        if c in "23":
            y |= masque
    return x, y, niveau


def quadkey_de(lon: float, lat: float, niveau: int = NIVEAU) -> str:
    return quadkey_de_tuile(*tuile_de(lon, lat, niveau), niveau)


def limites_quadkey(quadkey: str) -> tuple[float, float, float, float]:
    """(ouest, sud, est, nord) de la tuile, en degrés."""
    x, y, niveau = tuile_de_quadkey(quadkey)
    n = 1 << niveau

    def lat(yy: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return x / n * 360.0 - 180.0, lat(y + 1), (x + 1) / n * 360.0 - 180.0, lat(y)


def quadkeys_pour(bbox, niveau: int = NIVEAU) -> list[str]:
    """Quadkeys (triés) des tuiles qui recoupent (ouest, sud, est, nord)."""
    ouest, sud, est, nord = bbox
    x0, y1 = tuile_de(ouest, sud, niveau)  # coin sud-ouest : y le plus grand
    x1, y0 = tuile_de(est, nord, niveau)
    return sorted(quadkey_de_tuile(x, y, niveau) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))


# --- index et fichiers ---------------------------------------------------------------------------------------------------

def taille_en_octets(texte: str) -> int:
    """« 22.6MB » -> octets (0 si illisible). Sert seulement à refuser d'avance un téléchargement trop gros."""
    t = (texte or "").strip().upper().replace(" ", "")
    for suffixe, facteur in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024), ("B", 1)):
        if t.endswith(suffixe):
            try:
                return int(float(t[: -len(suffixe)]) * facteur)
            except ValueError:
                return 0
    return 0


def lire_index(texte: str) -> list[dict]:
    """Lignes de l'index : dicts avec Location, QuadKey (texte), Url, Size. Lève ValueError si les colonnes manquent."""
    lecteur = csv.DictReader(io.StringIO(texte))
    manquantes = {"Location", "QuadKey", "Url", "Size"} - set(lecteur.fieldnames or [])
    if manquantes:
        raise ValueError(f"index Microsoft illisible : colonnes manquantes {sorted(manquantes)}")
    return [{k: (v or "").strip() for k, v in ligne.items()} for ligne in lecteur]


def fichiers_pour(index: list[dict], quadkeys: list[str]) -> list[dict]:
    voulus = set(quadkeys)
    return sorted((l for l in index if l["QuadKey"] in voulus), key=lambda l: (l["QuadKey"], l["Location"], l["Url"]))


def filtrer_flux(lignes, bbox, maximum: int | None = None) -> tuple[list[dict], int]:
    """Lit des lignes GeoJSON (texte ou octets), garde les polygones dont l'enveloppe recoupe `bbox`.

    Renvoie (éléments {"anneaux": [[(lon, lat), ...], ...], "hauteur": float | None, "confiance": float | None}, lignes illisibles).
    Un MultiPolygon est éclaté en polygones. Une hauteur <= 0 (Microsoft met -1 pour « inconnue ») devient None.
    Rien d'autre que le résultat filtré n'est gardé en mémoire."""
    ouest, sud, est, nord = bbox
    gardes: list[dict] = []
    illisibles = 0
    for brut in lignes:
        if not brut or not brut.strip():
            continue
        try:
            f = json.loads(brut)
            geom = f["geometry"]
            props = f.get("properties") or {}
            if geom["type"] == "Polygon":
                polys = [geom["coordinates"]]
            elif geom["type"] == "MultiPolygon":
                polys = geom["coordinates"]
            else:
                continue
            h = props.get("height")
            c = props.get("confidence")
            h = float(h) if h is not None and float(h) > 0 else None
            c = float(c) if c is not None and float(c) >= 0 else None
        except (ValueError, KeyError, TypeError):
            illisibles += 1
            continue
        for p in polys:
            try:
                ext = p[0]
                xs = [pt[0] for pt in ext]
                ys = [pt[1] for pt in ext]
            except (IndexError, TypeError, KeyError):
                illisibles += 1
                continue
            if max(xs) < ouest or min(xs) > est or max(ys) < sud or min(ys) > nord:
                continue
            gardes.append({"anneaux": [[(float(a), float(b)) for a, b, *_ in anneau] for anneau in p], "hauteur": h, "confiance": c})
            if maximum is not None and len(gardes) >= maximum:
                return gardes, illisibles
    return gardes, illisibles


def vers_empreintes(elements: list[dict], frame, simplification: float = SIMPLIFICATION_M) -> list[Empreinte]:
    """Convertit en polygones du repère local, simplifiés très légèrement. Géométrie vide ou invalide : ignorée ici."""
    import numpy as np
    sortie = []
    for e in elements:
        anneaux = []
        for a in e["anneaux"]:
            if len(a) < 4:
                if not anneaux:
                    break
                continue
            pts = np.asarray(a, dtype=float)
            x, y = frame.to_local(pts[:, 0], pts[:, 1])
            anneaux.append(list(zip(x.tolist(), y.tolist())))
        if not anneaux:
            continue
        g = Polygon(anneaux[0], anneaux[1:])
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.geom_type != "Polygon":
            continue
        g = g.simplify(simplification, preserve_topology=True)
        if g.is_empty:
            continue
        extra = {"confiance": e["confiance"]} if e.get("confiance") is not None else {}
        sortie.append(Empreinte(geom=g, hauteur=e["hauteur"], extra=extra))
    return sortie


def decouper_a_la_zone(cands: list[Empreinte], zone) -> list[Empreinte]:
    """Coupe les bâtiments à cheval sur le bord de la zone (le contrôle qualité refuse tout ce qui dépasse). zone=None : inchangé."""
    if zone is None or zone.is_empty:
        return cands
    sortie = []
    for c in cands:
        if zone.contains(c.geom):
            sortie.append(c)
            continue
        morceau = c.geom.intersection(zone)
        parts = [morceau] if morceau.geom_type == "Polygon" else [g for g in getattr(morceau, "geoms", []) if g.geom_type == "Polygon"]
        sortie.extend(Empreinte(geom=g, hauteur=c.hauteur, extra=c.extra) for g in parts if not g.is_empty)
    return sortie


# --- la source ----------------------------------------------------------------------------------------------------------

def _ecrire_atomique(chemin: Path, octets: bytes) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(octets)
    os.replace(tmp, chemin)


@empreintes.enregistrer
class MicrosoftEmpreintes(SourceEmpreintes):
    id = "microsoft"
    nom = "Microsoft Global ML Building Footprints"
    licence = "CDLA Permissive 2.0"
    url_licence = "https://cdla.dev/permissive-2-0/"
    attribution = ("Contient des empreintes de bâtiments Microsoft Global ML Building Footprints (Microsoft, détection sur imagerie Bing Maps), "
                   "licence CDLA Permissive 2.0")
    url_source = "https://github.com/microsoft/GlobalMLBuildingFootprints"

    def __init__(self, opener=None, sleep=time.sleep):
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep

    # -- réseau
    def _requete(self, url: str):
        return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    def _avec_reessai(self, url: str, travail):
        """Exécute `travail(reponse)` ; un échec réseau ou de certificat est retenté UNE fois, puis une erreur claire est levée.
        La vérification SSL n'est jamais désactivée."""
        derniere = None
        for essai in range(2):
            try:
                with self.opener(self._requete(url), timeout=TIMEOUT) as rep:
                    return travail(rep)
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise RuntimeError(f"Microsoft : erreur HTTP {exc.code} pour {url}. Si l'index a changé de place, "
                                       "donne le nouveau dans [empreintes.microsoft] index_url et supprime cache/microsoft/.") from exc
                derniere = exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, ssl.SSLError, EOFError, OSError) as exc:
                derniere = exc
            if essai == 0:
                self.sleep(2)
        raison = getattr(derniere, "reason", derniere)
        if isinstance(raison, ssl.SSLCertVerificationError) or isinstance(derniere, ssl.SSLCertVerificationError):
            raise RuntimeError(f"Microsoft : le certificat SSL de {url} n'a pas pu être vérifié, même après un second essai ({raison}). "
                               "La vérification n'est jamais désactivée : corrige l'heure et les certificats de la machine, ou réessaie plus tard.") from derniere
        raise RuntimeError(f"Microsoft : téléchargement impossible après deux essais pour {url} (dernière erreur : {raison}).") from derniere

    def _index(self, ctx, reseau: bool) -> list[dict]:
        cache = ctx.project.cache / "microsoft" / "dataset-links.csv"
        if cache.is_file():
            return lire_index(cache.read_text(encoding="utf-8"))
        if not reseau:
            raise RuntimeError("Mode hors ligne : l'index Microsoft n'est pas en cache. Relance sans --hors-ligne, ou ajoute "
                               "[empreintes.microsoft] telecharger = true dans config.toml pour autoriser le réseau pour cette source seulement.")
        urls = [str(u) for u in [ctx.config.option("empreintes", "microsoft", {}).get("index_url")] if u] or list(INDEX_URLS)
        derniere = None
        for url in urls:
            try:
                octets = self._avec_reessai(url, lambda r: r.read(64 * 1024 * 1024))
                texte = octets.decode("utf-8")
                index = lire_index(texte)
            except (RuntimeError, ValueError, UnicodeDecodeError) as exc:
                derniere = exc
                continue
            _ecrire_atomique(cache, texte.encode("utf-8"))
            return index
        raise RuntimeError(f"Microsoft : index introuvable ({derniere})")

    def _fichier_filtre(self, ctx, ligne: dict, bbox, reseau: bool, budget: list[int]) -> list[dict]:
        """Éléments filtrés d'un fichier, depuis le cache ou par téléchargement en flux. `budget` : octets restants [un seul élément]."""
        cle = hashlib.sha256(json.dumps([list(bbox), ligne["Url"]], sort_keys=True).encode("utf-8")).hexdigest()[:24]
        fichier = ctx.project.cache / "microsoft" / f"filtre_{ligne['QuadKey']}_{cle}.json.gz"
        if fichier.is_file():
            try:
                return json.loads(gzip.decompress(fichier.read_bytes()).decode("utf-8"))["elements"]
            except (OSError, ValueError, KeyError):
                fichier.unlink(missing_ok=True)  # cache corrompu : on retélécharge si c'est permis
        if not reseau:
            raise RuntimeError("Mode hors ligne : aucune donnée Microsoft en cache pour cette zone. Relance sans --hors-ligne, ou ajoute "
                               "[empreintes.microsoft] telecharger = true dans config.toml pour autoriser le réseau pour cette source seulement.")
        declare = taille_en_octets(ligne.get("Size", ""))
        if declare > budget[0]:
            raise RuntimeError(f"Microsoft : le fichier {ligne['Location']}/{ligne['QuadKey']} ({ligne['Size']}) dépasse la limite de "
                               f"téléchargement de {LIMITE_OCTETS // (1024 * 1024)} Mo par essai.")

        def lire(rep):
            compte = _Compteur(rep, budget[0])
            with gzip.GzipFile(fileobj=compte) as gz:
                elements, illisibles = filtrer_flux(io.TextIOWrapper(gz, encoding="utf-8"), bbox)
            return elements, illisibles, compte.lus
        elements, illisibles, lus = self._avec_reessai(ligne["Url"], lire)
        budget[0] -= lus
        corps = json.dumps({"url": ligne["Url"], "bbox": list(bbox), "lignes_illisibles": illisibles, "elements": elements},
                           separators=(",", ":")).encode("utf-8")
        _ecrire_atomique(fichier, gzip.compress(corps))
        return elements

    def collecter(self, ctx, frame, zone) -> list[Empreinte]:
        bbox = tuple(ctx.config.bbox)
        autorise = bool(ctx.config.option("empreintes", "microsoft", {}).get("telecharger", False))
        reseau = autorise or not ctx.offline
        quadkeys = quadkeys_pour(bbox)
        index = self._index(ctx, reseau)
        lignes = fichiers_pour(index, quadkeys)
        if not lignes:
            raise RuntimeError(f"Microsoft : aucune tuile de l'index ne couvre la zone (quadkeys cherchés : {', '.join(quadkeys)}). "
                               "Le jeu ne couvre peut-être pas cette région.")
        budget = [LIMITE_OCTETS]
        elements: list[dict] = []
        for ligne in lignes:
            elements.extend(self._fichier_filtre(ctx, ligne, bbox, reseau, budget))
        cands = decouper_a_la_zone(vers_empreintes(elements, frame), zone)
        self.enregistrer_credit(ctx, len(cands))
        return cands


class _Compteur:
    """Enveloppe de lecture qui compte les octets reçus et s'arrête au-delà de la limite."""

    def __init__(self, rep, limite: int):
        self._rep, self._limite, self.lus = rep, limite, 0

    def read(self, n: int = -1) -> bytes:
        data = self._rep.read(n)
        self.lus += len(data)
        if self.lus > self._limite:
            raise RuntimeError(f"Microsoft : limite de téléchargement de {LIMITE_OCTETS // (1024 * 1024)} Mo par essai dépassée, arrêt.")
        return data
