"""Relance les contrôles automatiques de GTB après un lot de changements du jeu et n'affiche QUE les régressions (protocole « lot terminé »
convenu avec la session du jeu le 24/11/2026). Voir docs/CONTROLES_GTB.md.

Usage (depuis WSL ou Linux avec accès à powershell.exe) :
    python3 verif/gtb/lot_termine.py            # rapide : compilation, circulation, flottants, passants, toits, feux, fps (environ 15 min)
    python3 verif/gtb/lot_termine.py --complet  # ajoute l'audit de la chaussée (5 min) et le sol de toute la démo (15 min)
    python3 verif/gtb/lot_termine.py --fps-base # (re)écrit la base de référence des images par seconde à partir d'une mesure

Les lanceurs .ps1 (verif/gtb/) doivent être copiés dans C:\\gtb_local ; ils prennent le verrou de fenêtre C:\\gtb_local\\verrou_fenetre et les
sorties sont lues dans C:\\gtb_local (monté en /mnt/c/gtb_local). Un seul lot à la fois. Code de sortie 0 : aucune régression ; 1 : au moins une.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

W = Path("/mnt/c/gtb_local")
ICI = Path(__file__).resolve().parent
BASE_FPS = ICI / "base_fps.json"
SEUIL_FPS = 0.15   # pas plus de 15 % de millisecondes d'image en plus qu'à la dernière mesure de référence


def lancer(ps1: str, timeout: int) -> None:
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f"C:\\gtb_local\\{ps1}"], timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def lire(nom: str) -> str:
    f = W / nom
    return f.read_bytes().decode("utf-8", errors="replace").replace("\x00", "") if f.exists() else ""


def c_compile() -> list[str]:
    lancer("ay_gtb_compile.ps1", 300)
    t = lire("ay_gtb_compile.txt")
    return [] if "RESULTAT test_compile_scripts : OK" in t else ["compilation : " + (re.findall(r"ECHEC compilation : .*", t)[:5] or ["résultat absent"]).__str__()]


def c_circulation() -> list[str]:
    lancer("ay_gtb_circ.ps1", 2400)
    sys.path.insert(0, str(ICI.parent))
    import gtb_seuils_circulation as s
    pb = []
    for i in (1, 2):
        try:
            pb += [f"circulation position {i} : {x}" for x in s.verifier(s.lire(lire(f"ay_gtb_circ_{i}.txt")))]
        except ValueError as e:
            pb.append(f"circulation position {i} : {e}")
    return pb


def c_flottants() -> list[str]:
    lancer("ay_gtb_scan.ps1", 900)
    t = lire("ay_gtb_scan.txt")
    m = re.search(r"(\d+) défaut\(s\) au-delà", t)
    if not m:
        return ["flottants : résultat absent (verrou occupé ou erreur de script)"]
    return [] if int(m.group(1)) == 0 else [f"flottants : {m.group(1)} écart(s), voir C:\\gtb_local\\gtb_flottants.json"]


def c_pietons() -> list[str]:
    lancer("ay_gtb_pietons.ps1", 900)
    t = lire("ay_gtb_pietons.txt")
    m = re.search(r"par genre : (\{.*\})", t)
    if not m:
        return ["passants : résultat absent (verrou occupé ou erreur de script)"]
    g = json.loads(m.group(1))
    graves = {k: v for k, v in g.items() if k != "effleurement"}
    return [] if not graves else [f"passants : {graves}, voir C:\\gtb_local\\gtb_pietons.json"]


def c_toits() -> list[str]:
    lancer("ay_gtb_toits.ps1", 900)
    t = lire("ay_gtb_toits.txt")
    m = re.search(r"(\d+) toit\(s\).*?(\d+) défaut\(s\)", t)
    if not m or int(m.group(1)) == 0:
        return ["toits : résultat absent ou aucun toit contrôlé"]
    return [] if int(m.group(2)) == 0 else [f"toits : {m.group(2)} défaut(s), voir C:\\gtb_local\\gtb_toits.json"]


def c_feux() -> list[str]:
    lancer("ay_gtb_feux.ps1", 900)
    t = lire("ay_gtb_feux.txt")
    return [] if "RESULTAT test_feux_sens : OK" in t else ["feux : test_feux_sens non OK ou absent"]


def mesure_fps() -> dict:
    lancer("ay_gtb_fps.ps1", 1200)
    t = lire("ay_gtb_fps.txt")
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"BENCH (\w+) tout ms=([\d.]+)", t)}


def c_fps() -> list[str]:
    mes = mesure_fps()
    if len(mes) < 3:
        return ["fps : mesure incomplète (verrou occupé ou erreur)"]
    if not BASE_FPS.exists():
        return ["fps : pas de base de référence (lancer avec --fps-base)"]
    base = json.loads(BASE_FPS.read_text(encoding="utf-8"))["ms"]
    return [f"fps : {k} {mes[k]:.1f} ms contre {base[k]:.1f} ms de référence (+{(mes[k] / base[k] - 1) * 100:.0f} %, seuil {SEUIL_FPS * 100:.0f} %)"
            for k in base if k in mes and mes[k] > base[k] * (1 + SEUIL_FPS)]


def c_audit() -> list[str]:
    lancer("ay_gtb_audit.ps1", 1500)
    t = lire("ay_gtb_audit.txt")
    m = re.search(r"RESULTAT audit_chaussee : objets=(\d+) sans_sol=(\d+)", t)
    if not m:
        return ["chaussée : résultat absent"]
    pb = []
    if int(m.group(2)) > 0:
        pb.append(f"chaussée : {m.group(2)} point(s) sans sol")
    if int(m.group(1)) > 1:   # 1 = la limite de carte, normal
        pb.append(f"chaussée : {m.group(1)} objet(s) sur la chaussée (1 attendu : la limite de carte)")
    return pb


def c_sol() -> list[str]:
    lancer("ay_gtb_sol.ps1", 1800)
    t = lire("ay_gtb_sol.txt")
    m = re.search(r"(\d+) trous", t)
    if not m:
        return ["sol : résultat absent"]
    return [] if int(m.group(1)) == 0 else [f"sol : {m.group(1)} point(s) sans sol, voir C:\\gtb_local\\gtb_sol.json"]


def main(argv: list[str]) -> int:
    if "--fps-base" in argv:
        mes = mesure_fps()
        BASE_FPS.write_text(json.dumps({"ms": mes, "note": "mesure du jour, démo, 1280x720, vues aerogare/ararat/plage ; seuil +15 %"}, indent=1), encoding="utf-8")
        print("base fps écrite :", mes)
        return 0
    etapes = [("compilation", c_compile), ("circulation", c_circulation), ("flottants", c_flottants), ("passants", c_pietons),
              ("toits", c_toits), ("feux", c_feux), ("fps", c_fps)]
    if "--complet" in argv:
        etapes += [("chaussée", c_audit), ("sol", c_sol)]
    regressions: list[str] = []
    for nom, f in etapes:
        print(f"[{nom}] en cours...", flush=True)
        try:
            regressions += f()
        except Exception as e:   # noqa: BLE001 : un contrôle en panne est signalé, il n'arrête pas les autres
            regressions.append(f"{nom} : contrôle en panne ({type(e).__name__}: {e})")
    print()
    if regressions:
        print("RÉGRESSIONS :")
        for r in regressions:
            print(" -", r)
        return 1
    print("Aucune régression.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
