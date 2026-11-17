"""Enchaînement des étapes, avec reprise : une étape déjà faite avec la même entrée n'est pas refaite.

collecte -> nettoyage -> relief -> secours -> generation -> tests -> optimisation -> export

Le secours passe avant la génération des maillages : les éléments générés suivent ainsi le même chemin que les données réelles.

Chaque étape est un module de ayigba.stages qui expose `run(ctx) -> dict` (résumé chiffré).
Une étape terminée écrit work/<étape>/_fait.json ; ce fichier contient l'empreinte de la configuration
et celle de l'étape précédente. Si l'une change, l'étape et toutes les suivantes sont refaites.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import time
from pathlib import Path

from .project import Context

# nom de l'étape (français, utilisé en ligne de commande) -> module
STAGES: list[tuple[str, str]] = [
    ("collecte", "ayigba.stages.collect"),
    ("nettoyage", "ayigba.stages.clean"),
    ("relief", "ayigba.stages.relief"),
    ("secours", "ayigba.stages.fallback"),
    ("generation", "ayigba.stages.generate"),
    ("tests", "ayigba.stages.validate"),
    ("optimisation", "ayigba.stages.optimize"),
    ("export", "ayigba.stages.export"),
]
STAGE_NAMES = [name for name, _ in STAGES]


class StageError(RuntimeError):
    """Une étape a échoué : le message dit laquelle et pourquoi."""


def _code_digest(module_name: str) -> str:
    """Empreinte du code : si le code de l'étape ou d'un module commun change, l'étape est refaite (et les suivantes aussi).
    Les modules communs (geo, mesh, gltf...) comptent pour toutes les étapes : mieux vaut refaire trop que pas assez."""
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        spec = None
    if spec is None or not spec.origin or not spec.origin.endswith(".py"):
        return ""
    h = hashlib.sha256()
    common = sorted(p for p in Path(__file__).parent.glob("*.py") if p.name != "cli.py")
    for p in [*common, Path(spec.origin)]:
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _marker(ctx: Context, stage: str):
    return ctx.project.stage_dir(stage) / "_fait.json"


def _read_marker(ctx: Context, stage: str) -> dict | None:
    p = _marker(ctx, stage)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None  # étape interrompue pendant l'écriture : à refaire


def run_pipeline(ctx: Context, until: str | None = None, only: str | None = None, force: bool = False, echo=print) -> dict[str, dict]:
    """Exécute les étapes dans l'ordre. `until` : s'arrêter après cette étape. `only` : une seule étape.
    `force` : refaire même si déjà fait. Renvoie le résumé de chaque étape exécutée ou reprise."""
    for name in (until, only):
        if name is not None and name not in STAGE_NAMES:
            raise StageError(f"Étape inconnue : {name}. Étapes : {', '.join(STAGE_NAMES)}")
    results: dict[str, dict] = {}
    upstream = ctx.config.digest()
    for name, module_name in STAGES:
        marker = _read_marker(ctx, name)
        expected = hashlib.sha256((upstream + name + _code_digest(module_name)).encode()).hexdigest()[:16]
        selected = only is None or only == name
        if selected and not force and marker and marker.get("empreinte") == expected:
            echo(f"[{name}] déjà fait, repris tel quel")
            results[name] = marker.get("resume", {})
        elif selected:
            echo(f"[{name}] en cours...")
            t0 = time.monotonic()
            ctx.journal.start_stage(name)
            try:
                summary = importlib.import_module(module_name).run(ctx) or {}
            except Exception as exc:
                ctx.journal.flush()
                raise StageError(f"Étape « {name} » en échec : {exc}") from exc
            ctx.journal.flush()
            _marker(ctx, name).write_text(json.dumps({"empreinte": expected, "resume": summary}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            echo(f"[{name}] terminé en {time.monotonic() - t0:.1f} s : {json.dumps(summary, ensure_ascii=False)}")
            results[name] = summary
        elif marker is None:
            raise StageError(f"L'étape « {only} » a besoin de « {name} », qui n'a pas encore été faite.")
        upstream = expected
        if until == name or only == name:
            break
    return results
