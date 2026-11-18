"""Tests de l'interface commune des sources d'empreintes (ayigba.empreintes) : registre, fusion, crédits. Sans réseau."""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).parent))
from test_pipeline_synthetique import ecrire_projet, lancer, ville_de_base  # noqa: E402

from ayigba import empreintes  # noqa: E402
from ayigba.credits import build_credits  # noqa: E402
from ayigba.empreintes import Empreinte, SourceEmpreintes, disponibles, enregistrer, fusionner, obtenir  # noqa: E402
from ayigba.sources import read_sources  # noqa: E402


@pytest.fixture
def registre(monkeypatch):
    """Registre isolé : les sources livrées sont chargées d'abord (sinon leur import unique se perdrait avec la copie)."""
    empreintes._charger_sources_integrees()
    monkeypatch.setattr(empreintes, "REGISTRE", dict(empreintes.REGISTRE))
    return empreintes.REGISTRE


def classe(**attrs):
    base = dict(id="t1", nom="Test", licence="CC BY 4.0", url_licence="https://exemple.org/licence",
                attribution="Test (2026)", url_source="https://exemple.org")
    base.update(attrs)
    return type("Source" + str(base.get("id", "")), (SourceEmpreintes,), base)


def cand(geom, **kw):
    return Empreinte(geom=geom, **kw)


# ---------- 1) enregistrer ----------

@pytest.mark.parametrize("manquant", ["id", "nom", "licence", "url_licence", "attribution", "url_source"])
def test_enregistrer_refuse_attribut_manquant(registre, manquant):
    with pytest.raises(ValueError) as exc:
        enregistrer(classe(**{manquant: ""}))
    assert manquant in str(exc.value)


def test_enregistrer_refuse_plusieurs_manquants_et_les_cite_tous(registre):
    with pytest.raises(ValueError) as exc:
        enregistrer(classe(licence="", url_licence="", attribution=""))
    for k in ("licence", "url_licence", "attribution"):
        assert k in str(exc.value)


def test_enregistrer_refuse_classe_sans_id(registre):
    cls = type("SansId", (SourceEmpreintes,), dict(nom="N", licence="L", url_licence="u", attribution="a", url_source="s"))
    with pytest.raises(ValueError, match="id"):
        enregistrer(cls)


def test_enregistrer_refuse_id_en_double(registre):
    enregistrer(classe(id="dup"))
    with pytest.raises(ValueError, match="dup"):
        enregistrer(classe(id="dup"))


def test_enregistrer_accepte_classe_complete_et_reenregistrement_identique(registre):
    cls = enregistrer(classe(id="complete"))
    assert registre["complete"] is cls
    assert enregistrer(cls) is cls  # même classe : pas une erreur


def test_registre_restaure_entre_les_tests():
    assert "complete" not in empreintes.REGISTRE and "dup" not in empreintes.REGISTRE


# ---------- 2) obtenir / disponibles ----------

def test_obtenir_inconnu_liste_les_sources(registre):
    enregistrer(classe(id="zeta"))
    enregistrer(classe(id="alpha"))
    with pytest.raises(KeyError) as exc:
        obtenir("n_existe_pas")
    msg = str(exc.value)
    assert "n_existe_pas" in msg and "alpha" in msg and "zeta" in msg


def test_obtenir_renvoie_une_instance(registre):
    enregistrer(classe(id="inst"))
    assert isinstance(obtenir("inst"), SourceEmpreintes)
    assert obtenir("inst").id == "inst"


def test_disponibles_triees_par_id(registre):
    for i in ("m", "b", "z", "a"):
        enregistrer(classe(id=i))
    ids = [c.id for c in disponibles()]
    assert ids == sorted(ids)
    assert {"a", "b", "m", "z"} <= set(ids)


# ---------- 3) fusionner ----------

def test_candidat_identique_est_un_doublon():
    existant = box(0, 0, 10, 10)
    gardes, rejets = fusionner([existant], [cand(box(0, 0, 10, 10))])
    assert gardes == [] and rejets["doublon"] == 1


def test_recouvrement_20_pour_cent_garde_40_pour_cent_doublon():
    existant = box(0, 0, 10, 10)
    gardes, rejets = fusionner([existant], [cand(box(8, 0, 18, 10))])  # 20 m2 sur 100
    assert gardes == [0] and rejets["doublon"] == 0
    gardes, rejets = fusionner([existant], [cand(box(6, 0, 16, 10))])  # 40 m2 sur 100
    assert gardes == [] and rejets["doublon"] == 1


def test_seuil_de_recouvrement_parametrable():
    existant = box(0, 0, 10, 10)
    gardes, _ = fusionner([existant], [cand(box(6, 0, 16, 10))], recouvrement_max=0.5)
    assert gardes == [0]


def test_deux_candidats_qui_se_recouvrent_un_seul_garde_quel_que_soit_l_ordre():
    geoms = [box(0, 0, 10, 10), box(5, 0, 15, 10), box(100, 100, 110, 110)]
    attendu = None
    for graine in range(8):
        ordre = list(range(len(geoms)))
        random.Random(graine).shuffle(ordre)
        cands = [cand(geoms[k]) for k in ordre]
        gardes, rejets = fusionner([], cands)
        wkts = {cands[i].geom.wkt for i in gardes}
        assert len(gardes) == 2 and rejets["doublon"] == 1
        if attendu is None:
            attendu = wkts
        assert wkts == attendu
    assert box(0, 0, 10, 10).wkt in attendu and box(5, 0, 15, 10).wkt not in attendu


def test_determinisme_sur_chaine_de_recouvrements():
    geoms = [box(i * 6, 0, i * 6 + 10, 10) for i in range(8)]  # chaque bâtiment mord 4 m2 sur 10 du suivant
    attendu = None
    for graine in range(10):
        ordre = list(range(len(geoms)))
        random.Random(graine).shuffle(ordre)
        cands = [cand(geoms[k]) for k in ordre]
        gardes, _ = fusionner([], cands)
        wkts = {cands[i].geom.wkt for i in gardes}
        attendu = attendu or wkts
        assert wkts == attendu


def test_interdit_au_dela_et_en_deca_du_seuil():
    c = cand(box(0, 0, 10, 10))
    gardes, rejets = fusionner([], [c], interdit=box(0, 0, 10, 4))  # 40 %
    assert gardes == [] and rejets["chaussee_ou_eau"] == 1
    gardes, rejets = fusionner([], [c], interdit=box(0, 0, 10, 2))  # 20 %
    assert gardes == [0] and rejets["chaussee_ou_eau"] == 0


def test_surfaces_hors_limites():
    cands = [cand(box(0, 0, 2, 3)), cand(box(50, 0, 150, 60)), cand(box(300, 0, 303, 3))]  # 6 m2, 6000 m2, 9 m2
    gardes, rejets = fusionner([], cands)
    assert gardes == [2] and rejets["surface"] == 2


def test_geometrie_vide_ou_invalide():
    papillon = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert not papillon.is_valid
    gardes, rejets = fusionner([], [cand(Polygon()), cand(papillon)])
    assert gardes == [] and rejets["invalide"] == 2


def test_indices_dans_l_ordre_d_origine_et_compteurs_coherents():
    cands = [cand(box(500, 0, 510, 10)),          # 0 ok
             cand(Polygon()),                       # 1 invalide
             cand(box(0, 0, 10, 10)),               # 2 ok
             cand(box(0, 0, 10, 10)),               # 3 doublon du 2
             cand(box(200, 0, 201, 1)),             # 4 surface
             cand(box(300, 0, 310, 10)),            # 5 sur interdit
             cand(box(100, 0, 110, 10))]            # 6 ok
    gardes, rejets = fusionner([], cands, interdit=box(300, 0, 310, 10))
    assert gardes == [0, 2, 6] and gardes == sorted(gardes)
    assert rejets == {"invalide": 1, "surface": 1, "doublon": 1, "chaussee_ou_eau": 1}
    assert sum(rejets.values()) + len(gardes) == len(cands)


def test_listes_vides():
    assert fusionner([], []) == ([], {"invalide": 0, "surface": 0, "doublon": 0, "chaussee_ou_eau": 0})
    assert fusionner([box(0, 0, 10, 10)], [])[0] == []
    gardes, rejets = fusionner([], [cand(box(0, 0, 10, 10))])
    assert gardes == [0] and sum(rejets.values()) == 0


# ---------- 4) enregistrer_credit ----------

def test_enregistrer_credit_ecrit_sources_json_et_credits(tmp_path):
    src = classe(id="credit", nom="Source Crédit", attribution="Mention crédit 2026")()
    ctx = SimpleNamespace(project=SimpleNamespace(data=tmp_path), config=SimpleNamespace(bbox=(2.3, 6.3, 2.4, 6.4)))
    src.enregistrer_credit(ctx, 12, date="2026-01-02")
    brut = json.loads((tmp_path / "sources.json").read_text(encoding="utf-8"))
    assert len(brut) == 1
    e = brut[0]
    assert e["id"] == "credit" and e["licence"] == "CC BY 4.0" and e["elements"] == 12
    assert e["date_collecte"] == "2026-01-02" and e["zone"] == [2.3, 6.3, 2.4, 6.4]
    texte = build_credits(read_sources(tmp_path), "Titre")
    assert "Mention crédit 2026" in texte and "CC BY 4.0" in texte


# ---------- 5) performance ----------

def test_performance_3000_contre_3000():
    def grille(decalage):
        return [box(x * 10 + decalage, y * 10 + decalage, x * 10 + decalage + 4, y * 10 + decalage + 4)
                for x in range(60) for y in range(50)]  # 3000 rectangles, zone 600 x 500 m
    existants = grille(0.0)
    cands = [cand(g) for g in grille(5.0)]
    assert len(existants) == len(cands) == 3000
    t0 = time.perf_counter()
    gardes, rejets = fusionner(existants, cands)
    duree = time.perf_counter() - t0
    assert len(gardes) == 3000 and sum(rejets.values()) == 0
    assert duree < 5.0, f"{duree:.2f} s"


# ---------- 6) intégration dans l'étape secours ----------

def test_integration_source_supplementaire_dans_le_secours(tmp_path, registre):
    appels = []

    class Fausse(SourceEmpreintes):
        id = "fausse"
        nom = "Fausse source"
        licence = "CC BY 4.0"
        url_licence = "https://exemple.org/licence"
        attribution = "Fausse source (2026), CC BY 4.0"
        url_source = "https://exemple.org/fausse"

        def collecter(self, ctx, frame, zone):
            appels.append(1)
            self.enregistrer_credit(ctx, 3, date="2026-01-01")
            return [Empreinte(geom=box(-116, 40, -104, 50)),   # recouvre exactement le bâtiment OSM 11
                    Empreinte(geom=box(54, 55, 66, 65)),
                    Empreinte(geom=box(-106, -75, -94, -65))]

    enregistrer(Fausse)
    dossier = ecrire_projet(tmp_path / "ville-fausse", ville_de_base())
    cfg = dossier / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + '\n[empreintes]\nsources = ["fausse"]\n', encoding="utf-8")
    resultats = lancer(dossier)
    assert appels
    assert resultats["secours"]["sources_supplementaires"] == {"fausse": 2}
    sources = json.loads((dossier / "data" / "sources.json").read_text(encoding="utf-8"))
    assert any(s["id"] == "fausse" for s in sources)
    credits = (dossier / "out" / "neutre" / "CREDITS.md").read_text(encoding="utf-8")
    assert "Fausse source (2026), CC BY 4.0" in credits
