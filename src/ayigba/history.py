"""Historique des générations : instantanés, comparaison, retour en arrière."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from .project import Project

METRIQUES = (
    "erreurs",
    "avertissements",
    "batiments",
    "routes",
    "routes_km",
    "triangles",
    "hauteurs_estimees",
    "part_accessible",
    "poches_inaccessibles",
    "elements_generes",
)

_MOTIF = re.compile(r"^(\d{3,})_(.*)$")


def _racine(project: Project) -> Path:
    return project.reports / "historique"


def _nettoyer(etiquette: str) -> str:
    propre = re.sub(r"[^A-Za-z0-9-]+", "-", etiquette or "").strip("-")
    return propre or "sans-nom"


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _empreintes(dossier: Path) -> dict[str, str]:
    return {
        p.relative_to(dossier).as_posix(): _sha256(p)
        for p in sorted(dossier.rglob("*"))
        if p.is_file()
    }


def list_snapshots(project: Project) -> list[dict]:
    """Liste les instantanés existants, triés par numéro."""
    racine = _racine(project)
    res: list[dict] = []
    if racine.is_dir():
        for d in racine.iterdir():
            m = _MOTIF.match(d.name)
            if d.is_dir() and m:
                res.append({"numero": int(m.group(1)), "etiquette": m.group(2), "dossier": d})
    return sorted(res, key=lambda s: s["numero"])


def snapshot(project: Project, etiquette: str = "") -> Path:
    """Crée un instantané de out/neutre et de reports/qualite.json."""
    source = project.out / "neutre"
    if not source.is_dir():
        raise RuntimeError(
            f"Rien à sauvegarder : le dossier {source} n'existe pas. Lancez d'abord la génération."
        )
    existants = list_snapshots(project)
    numero = (existants[-1]["numero"] if existants else 0) + 1
    etiq = _nettoyer(etiquette)
    dossier = _racine(project) / f"{numero:03d}_{etiq}"
    dossier.mkdir(parents=True)
    shutil.copytree(source, dossier / "neutre")
    qualite = project.reports / "qualite.json"
    if qualite.is_file():
        shutil.copy2(qualite, dossier / "qualite.json")
    meta = {"numero": numero, "etiquette": etiq, "empreintes": _empreintes(dossier / "neutre")}
    (dossier / "instantane.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return dossier


def load_metrics(dossier: Path | None, project: Project) -> dict:
    """Métriques à plat d'un instantané (ou de l'état courant si dossier est None)."""
    chemin = project.reports / "qualite.json" if dossier is None else Path(dossier) / "qualite.json"
    try:
        q = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        q = {}
    if not isinstance(q, dict):
        q = {}

    def taille(v):
        return len(v) if isinstance(v, (list, tuple, dict)) else v

    marcheur = q.get("marcheur") if isinstance(q.get("marcheur"), dict) else {}
    sources = q.get("elements_par_source") if isinstance(q.get("elements_par_source"), dict) else {}
    return {
        "erreurs": taille(q.get("erreurs")),
        "avertissements": taille(q.get("avertissements")),
        "batiments": q.get("batiments"),
        "routes": q.get("routes"),
        "routes_km": q.get("routes_km"),
        "triangles": q.get("triangles"),
        "hauteurs_estimees": q.get("hauteurs_estimees"),
        "part_accessible": marcheur.get("part_accessible"),
        "poches_inaccessibles": taille(marcheur.get("poches_inaccessibles")),
        "elements_generes": sources.get("genere", 0),
    }


def _nombre(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _ecart(a, b) -> str:
    if not (_nombre(a) and _nombre(b)):
        return "?"
    d = b - a
    if d == 0:
        return "="
    if isinstance(d, int):
        return f"{d:+d}"
    return f"{round(d, 4):+g}"


def _txt(v) -> str:
    return "?" if v is None else str(v)


def compare(avant: dict, apres: dict) -> str:
    """Tableau Markdown des métriques avant/après, suivi d'un verdict."""
    lignes = ["| Mesure | Avant | Après | Écart |", "|---|---|---|---|"]
    for cle in METRIQUES:
        a, b = avant.get(cle), apres.get(cle)
        lignes.append(f"| {cle} | {_txt(a)} | {_txt(b)} | {_ecart(a, b)} |")
    ea, eb = avant.get("erreurs"), apres.get("erreurs")
    if _nombre(ea) and _nombre(eb) and eb > ea:
        verdict = "Régression : le nombre d'erreurs augmente."
    else:
        verdict = "Pas de régression sur les erreurs."
    return "\n".join(lignes) + "\n\n" + verdict + "\n"


def _empreintes_de(dossier: Path) -> dict[str, str]:
    meta = json.loads((Path(dossier) / "instantane.json").read_text(encoding="utf-8"))
    return meta.get("empreintes", {})


def compare_files(dossier_a: Path, dossier_b: Path) -> dict:
    """Compare les fichiers de deux instantanés d'après leurs empreintes."""
    a, b = _empreintes_de(dossier_a), _empreintes_de(dossier_b)
    communs = set(a) & set(b)
    return {
        "identiques": sorted(n for n in communs if a[n] == b[n]),
        "differents": sorted(n for n in communs if a[n] != b[n]),
        "seulement_avant": sorted(set(a) - set(b)),
        "seulement_apres": sorted(set(b) - set(a)),
    }


def restore(project: Project, numero: int) -> Path:
    """Remet out/neutre et reports/qualite.json dans l'état d'un instantané."""
    cible = next((s for s in list_snapshots(project) if s["numero"] == numero), None)
    if cible is None:
        raise LookupError(f"Aucun instantané numéro {numero}.")
    dossier: Path = cible["dossier"]
    neutre = project.out / "neutre"
    if neutre.exists():
        snapshot(project, "avant-retour")
        shutil.rmtree(neutre)
    neutre.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dossier / "neutre", neutre)
    qualite = dossier / "qualite.json"
    if qualite.is_file():
        project.reports.mkdir(parents=True, exist_ok=True)
        shutil.copy2(qualite, project.reports / "qualite.json")
    return neutre
