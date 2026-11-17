"""Création d'un projet à partir d'un nom de lieu, grâce au service Nominatim d'OpenStreetMap."""
from __future__ import annotations

import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import load_config

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ayigba/0.1 (generateur de cartes ; https://github.com/Geminiboug/ayigba)"
KM_PAR_DEGRE = 111.32
RAYON_MAX_KM = 20


def slugify(texte: str) -> str:
    """Nom de dossier sûr : minuscules, sans accents, tirets entre les mots."""
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sans_accents.lower()).strip("-")


def geocode(nom: str, opener=urllib.request.urlopen, timeout=30) -> dict:
    """Cherche un lieu ; renvoie {"lat", "lon", "nom_complet"}. Un seul appel, aucun nouvel essai."""
    url = NOMINATIM + "?" + urllib.parse.urlencode({"q": nom, "format": "jsonv2", "limit": 1})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(req, timeout=timeout) as rep:
            donnees = json.loads(rep.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Le service de géocodage a répondu par une erreur HTTP {exc.code}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Impossible de joindre le service de géocodage ({exc}). Vérifie la connexion.") from exc
    except ValueError as exc:
        raise RuntimeError("Réponse illisible du service de géocodage.") from exc
    if not donnees:
        raise LookupError(f"Lieu introuvable : {nom}")
    try:
        premier = donnees[0]
        return {
            "lat": float(premier["lat"]),
            "lon": float(premier["lon"]),
            "nom_complet": str(premier.get("display_name", nom)),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Réponse inattendue du service de géocodage.") from exc


def bbox_around(lat: float, lon: float, rayon_km: float) -> tuple:
    """Carré de côté 2 x rayon_km centré sur le point : (ouest, sud, est, nord), 5 décimales."""
    if not (0 < rayon_km <= RAYON_MAX_KM):
        raise ValueError(f"Le rayon doit être supérieur à 0 et au plus {RAYON_MAX_KM} km (reçu : {rayon_km}).")
    d_lat = rayon_km / KM_PAR_DEGRE
    d_lon = rayon_km / (KM_PAR_DEGRE * math.cos(math.radians(lat)))
    return (
        round(lon - d_lon, 5),
        round(lat - d_lat, 5),
        round(lon + d_lon, 5),
        round(lat + d_lat, 5),
    )


def _toml_texte(valeur: str) -> str:
    """Chaîne TOML entre guillemets, correctement échappée."""
    sortie = []
    for c in valeur:
        if c == "\\":
            sortie.append("\\\\")
        elif c == '"':
            sortie.append('\\"')
        elif c == "\n":
            sortie.append("\\n")
        elif c == "\r":
            sortie.append("\\r")
        elif c == "\t":
            sortie.append("\\t")
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            sortie.append(f"\\u{ord(c):04x}")
        else:
            sortie.append(c)
    return '"' + "".join(sortie) + '"'


def create_project(dossier_parent, nom: str, rayon_km: float = 1.5, graine: int = 1,
                   opener=urllib.request.urlopen) -> Path:
    """Géocode `nom`, crée dossier_parent/<slug>/config.toml et renvoie le dossier du projet."""
    dossier = Path(dossier_parent) / slugify(nom)
    fichier = dossier / "config.toml"
    if fichier.exists():
        raise FileExistsError(f"Le projet existe déjà : {fichier} n'a pas été modifié.")
    lieu = geocode(nom, opener=opener)
    ouest, sud, est, nord = bbox_around(lieu["lat"], lieu["lon"], rayon_km)
    commentaire = " ".join(lieu["nom_complet"].split())
    contenu = (
        f"# Projet créé depuis le lieu : {commentaire}\n"
        "[ville]\n"
        f"nom = {_toml_texte(nom)}\n"
        'quartier = ""\n'
        'pays = ""\n'
        "\n"
        "[zone]\n"
        "# Rectangle en degrés WGS84 : ouest, sud, est, nord.\n"
        f"bbox = [{ouest}, {sud}, {est}, {nord}]\n"
        "\n"
        "[generation]\n"
        "# Même entrée + même graine = même carte.\n"
        f"graine = {int(graine)}\n"
        'style = "defaut"\n'
        "\n"
        "[export]\n"
        '# "neutre" (glTF + GeoJSON).\n'
        'moteur = "neutre"\n'
    )
    dossier.mkdir(parents=True, exist_ok=True)
    fichier.write_text(contenu, encoding="utf-8")
    load_config(fichier)
    return dossier
