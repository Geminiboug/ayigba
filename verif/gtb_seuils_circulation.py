"""Contrôle de non-régression de la circulation de GTB : lit la sortie de `tests/banc_circulation.gd` du jeu (démo, 300 s) et la compare
aux seuils fixés avec la session du jeu le 24/11/2026.

Usage : python3 verif/gtb_seuils_circulation.py sortie1.txt [sortie2.txt ...]
Code de sortie 0 si tous les seuils sont respectés, 1 sinon.

Seuils (session du jeu) : chevauchements = 0 ; immobiles = 0 ; passages au rouge <= 12 (mesure approximative, la zone « dilemme » en compte une
partie légitimement ; au-delà de 12 = régression) ; sauts à moins de 150 m du joueur <= 45 (recyclage normal des véhicules, pas des sauts visibles) ;
klaxons <= 3 par minute ; freinages brusques <= 5 % des mesures (stable vers 3,5 à 4 % ; ne pas viser 0).
"""
import re
import sys
from pathlib import Path

SEUILS = {"chevauchements": 0, "immobiles": 0, "rouge": 12, "sauts": 45, "klaxons_par_min": 3.0, "freinages_pct": 5.0}


def lire(texte: str) -> dict:
    t = texte.replace("\x00", "")
    m = re.search(r"RESULTAT banc_circulation : chevauchements=(\d+).*?immobiles=(\d+) freinages=(\d+)/(\d+) sauts_pres=(\d+)", t)
    if not m:
        raise ValueError("ligne RESULTAT banc_circulation introuvable (le banc a-t-il tourné jusqu'au bout ?)")
    r = re.search(r"passés? au rouge[^:]*: (\d+)", t) or re.search(r"passes au rouge[^:]*: (\d+)", t)
    k = re.search(r"klaxons de la circulation : \d+ en [\d.]+ s simul[^(]*\(([\d.]+) par minute\)", t)
    if not r or not k:
        raise ValueError("lignes « passés au rouge » ou « klaxons » introuvables")
    ch, im, fr, tot, sa = (int(x) for x in m.groups())
    return {"chevauchements": ch, "immobiles": im, "rouge": int(r.group(1)), "sauts": sa, "klaxons_par_min": float(k.group(1)),
            "freinages_pct": round(100.0 * fr / max(tot, 1), 2)}


def verifier(mesures: dict) -> list[str]:
    pb = []
    for cle, seuil in SEUILS.items():
        v = mesures[cle]
        if v > seuil:
            pb.append(f"{cle} = {v} (seuil {seuil})")
    return pb


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    code = 0
    for f in argv:
        try:
            mesures = lire(Path(f).read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError) as e:
            print(f"{f} : {e}")
            code = 1
            continue
        pb = verifier(mesures)
        print(f"{f} : {mesures} -> {'OK' if not pb else 'REGRESSION : ' + '; '.join(pb)}")
        if pb:
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
