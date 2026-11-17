"""Fichier CREDITS.md : sources et licences des données utilisées par un projet."""
from __future__ import annotations

from pathlib import Path


def build_credits(sources: list[dict], titre: str, nb_generes: int | None = None) -> str:
    """Produit le texte Markdown des crédits. Strictement déterministe : pas de date du jour,
    sources triées par « id »."""
    triees = sorted(sources, key=lambda s: str(s.get("id", "")))
    L: list[str] = []
    L.append(f"# Sources et licences : {titre}")
    L.append("")
    L.append("Ce fichier est produit automatiquement par ayigba à partir du registre des sources du projet.")
    L.append("")
    L.append("## Données utilisées")
    L.append("")
    if not triees:
        L.append("Aucune source extérieure enregistrée.")
        L.append("")
    for s in triees:
        L.append(f"### {s.get('nom', s.get('id', ''))}")
        L.append("")
        L.append(f"- Licence : [{s.get('licence', '')}]({s.get('url_licence', '')})")
        L.append(f"- Mention à afficher : {s.get('attribution', '')}")
        L.append(f"- Source : {s.get('url_source', '')}")
        L.append(f"- Date de collecte : {s.get('date_collecte', '')}")
        if s.get("zone"):
            L.append(f"- Zone : {s['zone']}")
        if s.get("elements"):
            L.append(f"- Éléments : {s['elements']}")
        if s.get("note"):
            L.append(f"- Note : {s['note']}")
        L.append("")
    if any(str(s.get("licence", "")).startswith("ODbL") for s in triees):
        L.append("## Rappel ODbL")
        L.append("")
        L.append(
            "La mention des contributeurs est obligatoire partout où la carte est montrée "
            "(écran de crédits du jeu, page de téléchargement). "
            "Si une base de données dérivée est publiée, elle doit l'être sous ODbL (partage à l'identique)."
        )
        L.append("")
    L.append("## Éléments générés par l'outil")
    L.append("")
    L.append(
        "Les éléments marqués `source = genere` ne viennent d'aucune source extérieure : "
        "ils sont produits par ayigba pour combler les zones sans données."
    )
    if nb_generes is not None:
        L.append("")
        L.append(f"Nombre d'éléments générés : {nb_generes}.")
    L.append("")
    L.append("## Limites")
    L.append("")
    L.append(
        "Ce fichier n'est pas un avis juridique. Relire les conditions de chaque source "
        "avant une sortie commerciale."
    )
    return "\n".join(L) + "\n"


def write_credits(ctx, out_dir, nb_generes: int | None = None) -> Path:
    """Écrit out_dir/CREDITS.md à partir du registre des sources du projet."""
    from .sources import read_sources

    sources = read_sources(ctx.project.data)
    cfg = ctx.config
    titre = f"{cfg.city}, {cfg.district}" if cfg.district else cfg.city
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    chemin = out / "CREDITS.md"
    chemin.write_text(build_credits(sources, titre, nb_generes), encoding="utf-8")
    return chemin
