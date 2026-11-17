"""Registre des sources de données d'un projet : data/sources.json.

Chaque étape qui apporte une donnée extérieure enregistre sa source ici. L'export en tire le fichier CREDITS.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("id", "nom", "licence", "url_licence", "attribution", "url_source", "date_collecte")


def sources_path(data_dir: Path) -> Path:
    return Path(data_dir) / "sources.json"


def read_sources(data_dir: Path) -> list[dict]:
    p = sources_path(data_dir)
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def register_source(data_dir: Path, source: dict) -> None:
    """Ajoute ou remplace (même « id ») une source. Champs obligatoires : voir REQUIRED.
    date_collecte : « AAAA-MM-JJ ». Champs libres en plus : « zone », « note », « elements »."""
    missing = [k for k in REQUIRED if not source.get(k)]
    if missing:
        raise ValueError(f"source incomplète, champs manquants : {', '.join(missing)}")
    items = [s for s in read_sources(data_dir) if s.get("id") != source["id"]]
    items.append(source)
    items.sort(key=lambda s: s["id"])
    p = sources_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
