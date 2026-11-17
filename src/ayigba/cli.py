"""Ligne de commande : ayigba generer <dossier du projet>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError
from .pipeline import STAGE_NAMES, StageError, run_pipeline
from .project import open_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ayigba", description="Génère une carte 3D à partir d'un vrai lieu.")
    sub = parser.add_subparsers(dest="commande", required=True)
    gen = sub.add_parser("generer", help="exécute le pipeline sur un projet (dossier contenant config.toml)")
    gen.add_argument("projet", type=Path)
    gen.add_argument("--jusqua", choices=STAGE_NAMES, help="s'arrêter après cette étape")
    gen.add_argument("--etape", choices=STAGE_NAMES, help="n'exécuter que cette étape")
    gen.add_argument("--forcer", action="store_true", help="refaire les étapes même si elles sont déjà faites")
    gen.add_argument("--hors-ligne", action="store_true", help="n'utiliser que le cache local, aucun téléchargement")
    sub.add_parser("etapes", help="liste les étapes du pipeline")
    args = parser.parse_args(argv)

    if args.commande == "etapes":
        print(" -> ".join(STAGE_NAMES))
        return 0
    try:
        ctx = open_context(args.projet, offline=args.hors_ligne)
        run_pipeline(ctx, until=args.jusqua, only=args.etape, force=args.forcer)
    except (ConfigError, StageError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
