"""Tests du filtre de fragments douteux (ayigba.detection.filtrer_fragments et son usage dans l'étape secours), sans réseau."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).parent))
from test_detection import PAS, donnees_25d, projet  # noqa: E402
from test_pipeline_synthetique import lancer  # noqa: E402
from test_detection import props  # noqa: E402

from ayigba.detection import filtrer_fragments  # noqa: E402

GRAND = box(0, 0, 20, 10)  # 200 m2, bâtiment connu


# ---------- A. fonction pure ----------

def test_fragment_colle_a_un_grand_batiment_retire():
    frag = box(21, 0, 25, 4)  # 16 m2, haut (3 m) mais à 1 m du grand
    gardes, retires = filtrer_fragments([(frag, 3.0)], [GRAND])
    assert retires == [0] and gardes == []


def test_fragment_bas_isole_retire():
    frag = box(100, 100, 104, 104)  # 16 m2, 1,5 m, loin de tout
    gardes, retires = filtrer_fragments([(frag, 1.5)], [GRAND])
    assert retires == [0]


def test_petit_kiosque_isole_haut_garde():
    kiosque = box(100, 100, 104, 104)  # 16 m2, 3,5 m, isolé
    gardes, retires = filtrer_fragments([(kiosque, 3.5)], [GRAND])
    assert gardes == [0] and retires == []


def test_grand_batiment_bas_garde():
    grand_bas = box(100, 100, 110, 110)  # 100 m2, 1 m, et collé à un autre
    gardes, retires = filtrer_fragments([(grand_bas, 1.0)], [box(110, 100, 130, 120)])
    assert gardes == [0] and retires == []


def test_hauteur_inconnue_ne_declenche_pas_le_critere_de_hauteur():
    gardes, retires = filtrer_fragments([(box(100, 100, 104, 104), None)], [GRAND])
    assert gardes == [0]


def test_voisin_detecte_plus_grand_compte_mais_pas_un_plus_petit():
    petit, moyen = box(0, 0, 3, 3), box(4, 0, 8, 4)  # 9 m2 et 16 m2, 1 m d'écart, hauteurs normales
    gardes, retires = filtrer_fragments([(petit, 3.0), (moyen, 3.0)], [])
    assert retires == [0] and gardes == [1]  # le petit est collé à un plus grand ; le moyen n'a pas de plus grand voisin


def test_seuils_changes():
    frag = box(21, 0, 25, 4)  # 16 m2 collé
    assert filtrer_fragments([(frag, 3.0)], [GRAND], surface_m2=10.0)[1] == []
    assert filtrer_fragments([(frag, 3.0)], [GRAND], voisin_m=0.5)[1] == []
    assert filtrer_fragments([(frag, 3.0)], [GRAND], voisin_m=1.5)[1] == [0]
    iso = box(100, 100, 104, 104)
    assert filtrer_fragments([(iso, 2.0)], [GRAND], hauteur_m=1.5)[1] == []
    assert filtrer_fragments([(iso, 2.0)], [GRAND], hauteur_m=2.4)[1] == [0]


# ---------- B. pipeline ----------

FRAG = (-90, -50, -86, -46)    # 16 m2 avant lissage, isolé, loin des routes
BASE_HAUTEUR = 1.5


def donnees_fragment(hauteur):
    d = donnees_25d()
    xa, ya, xb, yb = FRAG
    j0, j1 = int(round((xa + 400) / PAS)), int(round((xb + 400) / PAS))
    i0, i1 = int(round((400 - yb) / PAS)), int(round((400 - ya) / PAS))
    d["presence"][i0:i1, j0:j1] = 1.0
    d["hauteur"][i0:i1, j0:j1] = hauteur
    return d


def detections(d):
    return [p for p in props(d, "secours") if p.get("source") == "google_25d"]


def decisions(d):
    f = d / "logs" / "decisions.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_pipeline_fragment_bas_retire_et_journalise(tmp_path):
    d = projet(tmp_path, donnees=donnees_fragment(BASE_HAUTEUR))
    lancer(d)
    assert len(detections(d)) == 1  # seule la grande tache reste
    lignes = [l for l in decisions(d) if l.get("action") == "supprime" and "fragment" in json.dumps(l, ensure_ascii=False)]
    assert lignes and lignes[0]["details"]["nombre"] == 1 and lignes[0]["details"]["surface_m2"] == 20.0


def test_pipeline_kiosque_haut_isole_garde(tmp_path):
    d = projet(tmp_path, donnees=donnees_fragment(3.5))
    lancer(d)
    assert len(detections(d)) == 2


def test_pipeline_option_desactivee(tmp_path):
    d = projet(tmp_path, donnees=donnees_fragment(BASE_HAUTEUR), extra="\n[batiments25d]\nfragments_actif = false\n")
    lancer(d)
    assert len(detections(d)) == 2


def test_pipeline_seuils_par_config(tmp_path):
    d = projet(tmp_path, donnees=donnees_fragment(BASE_HAUTEUR), extra="\n[batiments25d]\nfragment_surface_m2 = 10.0\n")
    lancer(d)
    assert len(detections(d)) == 2
    d2 = projet(tmp_path, "autre/ville-test", donnees=donnees_fragment(2.0), extra="\n[batiments25d]\nfragment_hauteur_m = 1.5\n")
    lancer(d2)
    assert len(detections(d2)) == 2
