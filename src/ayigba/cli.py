"""Ligne de commande d'ayigba.

  ayigba creer "Ouidah, Bénin" --rayon-km 1.5     crée un projet à partir d'un nom de lieu
  ayigba generer projects/ouidah-benin             exécute le pipeline
  ayigba instantane projects/ouidah-benin          garde une copie du résultat
  ayigba comparer projects/ouidah-benin            compare le résultat courant au dernier instantané
  ayigba restaurer projects/ouidah-benin 1         revient à un instantané
  ayigba controler-detections projects/ouidah-benin   indices de suspicion sur les bâtiments détectés par IA
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import geocode, history
from .config import ConfigError
from .pipeline import STAGE_NAMES, StageError, run_pipeline
from .project import Project, open_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ayigba", description="Génère une carte 3D à partir d'un vrai lieu.")
    sub = parser.add_subparsers(dest="commande", required=True)

    new = sub.add_parser("creer", help="crée un projet à partir d'un nom de lieu (demande les coordonnées à OpenStreetMap)")
    new.add_argument("lieu", help="nom du lieu, par exemple « Ouidah, Bénin »")
    new.add_argument("--rayon-km", type=float, default=1.5, help="demi-côté de la zone, en kilomètres (défaut : 1,5)")
    new.add_argument("--graine", type=int, default=1)
    new.add_argument("--dossier", type=Path, default=Path("projects"), help="dossier qui reçoit le projet (défaut : projects)")

    gen = sub.add_parser("generer", help="exécute le pipeline sur un projet (dossier contenant config.toml)")
    gen.add_argument("projet", type=Path)
    gen.add_argument("--jusqua", choices=STAGE_NAMES, help="s'arrêter après cette étape")
    gen.add_argument("--etape", choices=STAGE_NAMES, help="n'exécuter que cette étape")
    gen.add_argument("--forcer", action="store_true", help="refaire les étapes même si elles sont déjà faites")
    gen.add_argument("--hors-ligne", action="store_true", help="n'utiliser que le cache local, aucun téléchargement")

    snap = sub.add_parser("instantane", help="garde une copie du résultat courant (pour comparer ou revenir en arrière)")
    snap.add_argument("projet", type=Path)
    snap.add_argument("--nom", default="", help="étiquette de l'instantané")

    cmp_ = sub.add_parser("comparer", help="compare deux instantanés, ou le résultat courant au dernier instantané")
    cmp_.add_argument("projet", type=Path)
    cmp_.add_argument("avant", type=int, nargs="?", help="numéro de l'instantané de départ (défaut : le dernier)")
    cmp_.add_argument("apres", type=int, nargs="?", help="numéro de l'instantané d'arrivée (défaut : le résultat courant)")

    back = sub.add_parser("restaurer", help="remet en place le résultat d'un instantané")
    back.add_argument("projet", type=Path)
    back.add_argument("numero", type=int)

    ctl = sub.add_parser("controler-detections", help="indices de suspicion sur les bâtiments détectés par IA (sans réseau, pas une vérité terrain)")
    ctl.add_argument("projet", type=Path)
    ctl.add_argument("--sans-images", action="store_true", help="ne pas produire la planche et les vignettes PNG")
    ctl.add_argument("--exclure-score", type=int, metavar="X",
                     help="écrit dans config.toml les identifiants de score >= X à exclure à la prochaine génération (rien n'est exclu sans cette option)")

    sub.add_parser("sources", help="liste les sources d'empreintes de bâtiments disponibles, avec leur licence")
    sub.add_parser("etapes", help="liste les étapes du pipeline")
    args = parser.parse_args(argv)

    try:
        if args.commande == "etapes":
            print(" -> ".join(STAGE_NAMES))
        elif args.commande == "sources":
            from . import empreintes
            print("Sources d'empreintes disponibles (à activer dans config.toml : [empreintes] sources = [\"id\", ...]) :")
            print("  osm            OpenStreetMap, toujours utilisée (ODbL 1.0)")
            print("  google_25d     Google Open Buildings 2.5D, détection des bâtiments absents d'OSM : [batiments25d] detecter (CC BY 4.0)")
            for c in empreintes.disponibles():
                print(f"  {c.id:<14} {c.nom} ({c.licence}) : {c.url_source}")
        elif args.commande == "creer":
            folder = geocode.create_project(args.dossier, args.lieu, rayon_km=args.rayon_km, graine=args.graine)
            print(f"Projet créé : {folder}\nVérifie la zone dans {folder / 'config.toml'}, puis lance : ayigba generer {folder}")
        elif args.commande == "generer":
            ctx = open_context(args.projet, offline=args.hors_ligne)
            results = run_pipeline(ctx, until=args.jusqua, only=args.etape, force=args.forcer)
            if results.get("tests", {}).get("erreurs"):
                print(f"Attention : le rapport de qualité contient {results['tests']['erreurs']} erreur(s). Voir {ctx.project.reports / 'qualite.md'}", file=sys.stderr)
                return 2
        elif args.commande == "controler-detections":
            from . import controle
            rap = controle.controler(Project(args.projet.resolve()), sans_images=args.sans_images, exclure_score=args.exclure_score)
            print(rap["_texte"])
            racine = Path(args.projet)
            print(f"\nRapport : {racine / 'reports' / 'controle_detections.json'}")
            if rap["_images"]:
                print(f"Planche : {rap['_images']}")
            if args.exclure_score is not None:
                if rap["_exclus_total"] is None:
                    print(f"Aucun bâtiment de score >= {args.exclure_score} : config.toml inchangé.")
                else:
                    print(f"{rap['_exclus_nouveaux']} identifiant(s) ajouté(s) à [batiments25d] exclure dans {racine / 'config.toml'} "
                          f"({rap['_exclus_total']} au total). Relance « ayigba generer {racine} » pour les retirer ; le nombre sera journalisé.")
        else:
            project = Project(args.projet.resolve())
            if args.commande == "instantane":
                print(f"Instantané créé : {history.snapshot(project, args.nom)}")
            elif args.commande == "restaurer":
                print(f"Résultat restauré depuis : {history.restore(project, args.numero)}")
            else:
                snaps = {s["numero"]: s["dossier"] for s in history.list_snapshots(project)}
                if not snaps:
                    raise LookupError("Aucun instantané : lance d'abord « ayigba instantane ».")
                first = args.avant if args.avant is not None else max(snaps)
                for n in (first, args.apres):
                    if n is not None and n not in snaps:
                        raise LookupError(f"Instantané {n} introuvable. Existants : {sorted(snaps)}")
                after_dir = snaps[args.apres] if args.apres is not None else None
                print(f"Avant : instantané {first}. Après : " + (f"instantané {args.apres}" if args.apres is not None else "résultat courant") + ".\n")
                print(history.compare(history.load_metrics(snaps[first], project), history.load_metrics(after_dir, project)))
    except (ConfigError, StageError, LookupError, FileExistsError, RuntimeError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
