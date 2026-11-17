"""Étape de collecte : télécharge les données OpenStreetMap de la zone (API Overpass), avec cache local."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..sources import register_source

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "ayigba/0.1 (generateur de cartes ; https://github.com/Geminiboug/ayigba)"
ATTENTES = (5, 15, 45)
CODES_REESSAI = (429, 502, 503, 504)


def build_query(bbox) -> str:
    """Requête Overpass pour la zone (ouest, sud, est, nord). Texte stable : il est haché pour le cache."""
    ouest, sud, est, nord = bbox
    b = f"{sud:.6f},{ouest:.6f},{nord:.6f},{est:.6f}"
    lignes = [
        "[out:json][timeout:180];",
        "(",
        f'  way["highway"]({b}); way["building"]({b}); relation["building"]({b});',
        f'  way["natural"]({b}); relation["natural"="water"]({b});',
        f'  way["waterway"]({b}); way["landuse"]({b}); relation["landuse"]({b});',
        f'  way["leisure"]({b}); way["aeroway"]({b}); way["amenity"]({b}); way["barrier"]({b});',
        f'  node["amenity"]({b}); node["shop"]({b}); node["tourism"]({b}); node["man_made"]({b}); node["power"]({b});',
        f'  node["natural"="tree"]({b}); node["highway"~"^(traffic_signals|crossing|bus_stop)$"]({b});',
        ");",
        "out tags geom;",
    ]
    return "\n".join(lignes)


def fetch(query, endpoints=ENDPOINTS, opener=urllib.request.urlopen, sleep=time.sleep, timeout=240):
    """Envoie la requête à chaque point d'accès à tour de rôle ; renvoie (octets, url qui a répondu)."""
    corps = ("data=" + urllib.parse.urlencode({"q": query})[2:]).encode("ascii")
    dernier = "aucune réponse"
    for url in endpoints:
        for essai in range(3):
            req = urllib.request.Request(url, data=corps, method="POST", headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            })
            try:
                with opener(req, timeout=timeout) as rep:
                    return rep.read(), url
            except urllib.error.HTTPError as exc:
                if exc.code not in CODES_REESSAI:
                    dernier = f"{url} : erreur HTTP {exc.code}"
                    break
                dernier = f"{url} : erreur HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError) as exc:
                dernier = f"{url} : {exc}"
            if essai < 2:
                sleep(ATTENTES[essai])
    raise RuntimeError(f"Téléchargement OpenStreetMap impossible après plusieurs essais (dernière erreur : {dernier}). Vérifie la connexion puis relance.")


def _ecrire_atomique(chemin: Path, octets: bytes) -> None:
    tmp = chemin.with_name(chemin.name + ".tmp")
    tmp.write_bytes(octets)
    os.replace(tmp, chemin)


def run(ctx) -> dict:
    cache = ctx.project.cache
    f_data = cache / "osm_overpass.json"
    f_meta = cache / "osm_overpass.meta.json"
    requete = build_query(ctx.config.bbox)
    empreinte = hashlib.sha256(requete.encode("utf-8")).hexdigest()

    meta = None
    if f_data.is_file() and f_meta.is_file():
        try:
            m = json.loads(f_meta.read_text(encoding="utf-8"))
            if m.get("requete_sha256") == empreinte:
                meta = m
        except ValueError:
            meta = None

    if meta is not None:
        elements = json.loads(f_data.read_text(encoding="utf-8"))["elements"]
        depuis_cache = True
    else:
        if ctx.offline:
            raise RuntimeError("Mode hors ligne : aucune donnée en cache pour cette zone. Relance une fois sans --hors-ligne.")
        octets, point = fetch(requete)
        try:
            elements = json.loads(octets.decode("utf-8")).get("elements")
        except (ValueError, AttributeError) as exc:
            raise RuntimeError("Réponse Overpass illisible (JSON invalide).") from exc
        if not isinstance(elements, list) or not elements:
            raise RuntimeError("Overpass n'a renvoyé aucun élément pour cette zone : vérifie la bbox ou réessaie plus tard.")
        cache.mkdir(parents=True, exist_ok=True)
        _ecrire_atomique(f_data, octets)
        meta = {
            "requete_sha256": empreinte,
            "date_collecte": datetime.date.today().isoformat(),
            "point_acces": point,
            "elements": len(elements),
        }
        _ecrire_atomique(f_meta, json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))
        depuis_cache = False

    n = len(elements)
    register_source(ctx.project.data, {
        "id": "osm",
        "nom": "OpenStreetMap",
        "licence": "ODbL 1.0",
        "url_licence": "https://opendatacommons.org/licenses/odbl/1-0/",
        "attribution": "© les contributeurs d'OpenStreetMap",
        "url_source": "https://www.openstreetmap.org/copyright",
        "date_collecte": meta["date_collecte"],
        "zone": list(ctx.config.bbox),
        "elements": n,
    })
    origine = "repris du cache" if depuis_cache else "téléchargé"
    ctx.journal.record("info", "osm", f"Données OpenStreetMap {origine} : {n} éléments.")
    compte = {"node": 0, "way": 0, "relation": 0}
    for e in elements:
        t = e.get("type")
        if t in compte:
            compte[t] += 1
    return {"elements": n, "noeuds": compte["node"], "chemins": compte["way"],
            "relations": compte["relation"], "depuis_cache": depuis_cache}
