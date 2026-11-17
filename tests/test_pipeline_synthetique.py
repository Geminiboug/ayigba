"""Tests de bout en bout du pipeline sur une petite ville synthétique, sans réseau."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from shapely.geometry import shape

from ayigba import pipeline
from ayigba.geo import LocalFrame
from ayigba.pipeline import StageError, run_pipeline
from ayigba.project import open_context
from ayigba.stages import collect

BBOX = (2.3800, 6.3500, 2.3840, 6.3530)
FRAME = LocalFrame(BBOX)

CONFIG = """[ville]
nom = "Testville"
quartier = "Centre"

[zone]
bbox = [2.3800, 6.3500, 2.3840, 6.3530]

[generation]
graine = {graine}
"""


# ---------- aides ----------

def ll(x: float, y: float) -> dict:
    lon, lat = FRAME.to_wgs84(x, y)
    return {"lat": float(lat), "lon": float(lon)}


class Ville:
    """Construit la liste d'éléments Overpass à partir de mètres locaux."""

    def __init__(self):
        self.elements: list[dict] = []
        self._id = 1000

    def _nouvel_id(self) -> int:
        self._id += 1
        return self._id

    def route(self, points, highway="residential", ident=None) -> int:
        ident = ident or self._nouvel_id()
        self.elements.append({"type": "way", "id": ident, "tags": {"highway": highway},
                              "geometry": [ll(x, y) for x, y in points]})
        return ident

    def polygone(self, points, tags, ident=None) -> int:
        ident = ident or self._nouvel_id()
        pts = list(points)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        self.elements.append({"type": "way", "id": ident, "tags": dict(tags),
                              "geometry": [ll(x, y) for x, y in pts]})
        return ident

    def rect(self, cx, cy, w, h, tags=None, ident=None) -> int:
        tags = {"building": "yes", **(tags or {})}
        pts = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
        return self.polygone(pts, tags, ident)

    def noeud(self, x, y, tags, ident=None) -> int:
        ident = ident or self._nouvel_id()
        p = ll(x, y)
        self.elements.append({"type": "node", "id": ident, "lat": p["lat"], "lon": p["lon"], "tags": tags})
        return ident


def ville_de_base() -> Ville:
    v = Ville()
    v.route([(-150, 0), (0, 0), (150, 0)], ident=1)
    v.route([(0, -100), (0, 0), (0, 100)], ident=2)
    v.rect(-110, 45, 12, 10, ident=11)
    v.rect(-50, 45, 12, 10, {"building:levels": "2"}, ident=12)
    v.rect(-50, -45, 12, 10, {"height": "9"}, ident=13)
    v.rect(30, -50, 12, 10, ident=14)
    v.rect(100, -40, 12, 10, ident=15)
    v.rect(110, -70, 12, 10, ident=16)
    v.noeud(-30, -40, {"amenity": "school", "name": "Ecole Test"}, ident=21)
    return v


def ecrire_projet(dossier: Path, ville: Ville | None, graine: int = 42, cache: bool = True) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "config.toml").write_text(CONFIG.format(graine=graine), encoding="utf-8")
    if cache:
        (dossier / "cache").mkdir(exist_ok=True)
        (dossier / "cache" / "osm_overpass.json").write_text(
            json.dumps({"elements": ville.elements}), encoding="utf-8")
        sha = hashlib.sha256(collect.build_query(BBOX).encode("utf-8")).hexdigest()
        (dossier / "cache" / "osm_overpass.meta.json").write_text(json.dumps({
            "requete_sha256": sha, "date_collecte": "2026-01-01",
            "point_acces": "cache", "elements": len(ville.elements)}), encoding="utf-8")
    return dossier


def lancer(dossier: Path, echo=None):
    ctx = open_context(dossier, offline=True)
    return run_pipeline(ctx, echo=echo or (lambda *_: None))


def construire(tmp_path: Path, ville: Ville, nom="ville-test", graine=42) -> Path:
    dossier = ecrire_projet(tmp_path / nom, ville, graine)
    lancer(dossier)
    return dossier


def geojson(chemin: Path) -> list[dict]:
    return json.loads(chemin.read_text(encoding="utf-8"))["features"]


def decisions(dossier: Path) -> list[dict]:
    return [json.loads(l) for l in (dossier / "logs" / "decisions.jsonl").read_text(encoding="utf-8").splitlines() if l]


def qualite(dossier: Path) -> dict:
    return json.loads((dossier / "reports" / "qualite.json").read_text(encoding="utf-8"))


def ids_de(dossier: Path, osm_id: int) -> str:
    return f"/{osm_id}"


def decision_pour(dossier: Path, osm_id: int, action: str) -> list[dict]:
    return [d for d in decisions(dossier) if d["action"] == action and d["objet"].endswith(f"/{osm_id}")]


def ids_batiments(dossier: Path) -> set[str]:
    return {f["properties"]["id"] for f in geojson(dossier / "work" / "generation" / "buildings.geojson")}


# ---------- tests ----------

def test_pipeline_complet_sur_ville_de_base(tmp_path):
    d = construire(tmp_path, ville_de_base())
    assert qualite(d)["erreurs"] == []
    neutre = d / "out" / "neutre"
    for nom in ("carte.glb", "routes.geojson", "batiments.geojson", "points_interet.geojson", "manifeste.json", "CREDITS.md"):
        assert (neutre / nom).is_file(), nom
    assert (neutre / "carte.glb").read_bytes()[:4] == b"glTF"
    assert "OpenStreetMap" in (neutre / "CREDITS.md").read_text(encoding="utf-8")


def test_reproductibilite_et_effet_de_la_graine(tmp_path):
    a = construire(tmp_path, ville_de_base(), "a/ville-test")
    b = construire(tmp_path, ville_de_base(), "b/ville-test")
    c = construire(tmp_path, ville_de_base(), "c/ville-test", graine=43)
    glb = lambda p: (p / "out" / "neutre" / "carte.glb").read_bytes()
    assert glb(a) == glb(b)
    assert glb(a) != glb(c)


def test_hauteurs_osm_et_generees(tmp_path):
    d = construire(tmp_path, ville_de_base())
    par_id = {f["properties"]["id"].split("/")[-1]: f["properties"]
              for f in geojson(d / "work" / "generation" / "buildings.geojson")}
    assert par_id["12"]["hauteur"] == 6.5 and par_id["12"]["hauteur_source"] == "osm"
    assert par_id["13"]["hauteur"] == 9.0 and par_id["13"]["hauteur_source"] == "osm"
    for k in ("11", "14", "15", "16"):
        assert par_id[k]["hauteur_source"] == "genere"
        assert 2.5 <= par_id[k]["hauteur"] <= 13


def test_bout_de_route_recolle(tmp_path):
    v = ville_de_base()
    v.route([(60, 80), (60, 1.2)], ident=3)
    d = construire(tmp_path, v)
    recolles = [x for x in decision_pour(d, 3, "corrige") if "recollé" in x["raison"]]
    assert recolles
    routes = geojson(d / "work" / "nettoyage" / "roads.geojson")
    assert routes and all(f["properties"]["reseau"] == "principal" for f in routes)


def test_reseau_isole_signale(tmp_path):
    v = ville_de_base()
    v.route([(100, 60), (140, 60)], ident=4)
    d = construire(tmp_path, v)
    routes = geojson(d / "work" / "nettoyage" / "roads.geojson")
    reseaux = [f["properties"]["reseau"] for f in routes if f["properties"]["id"].endswith("/4")]
    assert reseaux == ["isole"]
    # l'étape de secours la relie au réseau principal par un lien généré (60 m en ligne droite, sans obstacle)
    apres = geojson(d / "work" / "secours" / "roads.geojson")
    assert all(f["properties"]["reseau"] != "isole" for f in apres)
    liens = [f for f in apres if f["properties"]["source"] == "genere"]
    assert len(liens) == 1 and liens[0]["properties"]["id"].startswith("genere/acces-")
    assert qualite(d)["erreurs"] == []


def test_route_isolee_sans_acces_retiree(tmp_path):
    # à 70 m du réseau, au-delà de la longueur maximale d'un lien (60 m) : la route isolée est retirée
    v = ville_de_base()
    v.route([(100, 70), (140, 70)], ident=4)
    d0 = construire(tmp_path / "a", v)
    assert any(f["properties"]["source"] == "genere" for f in geojson(d0 / "work" / "secours" / "roads.geojson")) is False
    assert decision_pour(d0, 4, "supprime")


def test_batiment_sur_la_route_supprime(tmp_path):
    v = ville_de_base()
    v.rect(-80, 0, 10, 10, ident=30)
    d = construire(tmp_path, v)
    assert decision_pour(d, 30, "supprime")
    assert not any(i.endswith("/30") for i in ids_batiments(d))
    assert qualite(d)["erreurs"] == []


def test_doublon_de_batiment(tmp_path):
    v = ville_de_base()
    v.rect(-110, -45, 12, 10, ident=40)
    v.rect(-110, -45, 12, 10, ident=41)
    d = construire(tmp_path, v)
    restants = [i for i in ids_batiments(d) if i.endswith("/40") or i.endswith("/41")]
    assert len(restants) == 1
    sup = [x for x in decisions(d) if x["action"] == "supprime" and "doublon" in x["raison"]]
    assert len(sup) == 1


def test_batiment_minuscule_supprime(tmp_path):
    v = ville_de_base()
    v.rect(-110, -45, 1, 1, ident=50)
    d = construire(tmp_path, v)
    assert decision_pour(d, 50, "supprime")
    assert not any(i.endswith("/50") for i in ids_batiments(d))


def test_eau_et_couverture_du_sol(tmp_path):
    v = ville_de_base()
    v.rect(-100, -80, 40, 30, {"natural": "water"}, ident=60)
    # rect ajoute building=yes : on le retire pour ne garder que l'eau
    v.elements[-1]["tags"] = {"natural": "water"}
    d = construire(tmp_path, v)
    assert qualite(d)["erreurs"] == []
    sol = geojson(d / "work" / "generation" / "sol.geojson")
    assert any(f["properties"]["genre"] == "eau" for f in sol)
    total = sum(shape(f["geometry"]).area for f in sol)
    assert abs(total - FRAME.zone_polygon().area) <= 1.0


def test_hors_ligne_sans_cache(tmp_path):
    d = ecrire_projet(tmp_path / "ville-test", None, cache=False)
    with pytest.raises(StageError):
        lancer(d)


def test_reprise_ne_refait_rien(tmp_path):
    d = construire(tmp_path, ville_de_base())
    messages: list[str] = []
    lancer(d, echo=lambda m, *_: messages.append(str(m)))
    assert messages
    assert all("déjà fait" in m for m in messages)


def test_toits_desactives_donne_zero_toit_a_deux_pentes(tmp_path):
    dossier = ecrire_projet(tmp_path / "sans-toits", ville_de_base())
    cfg = dossier / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[toits]\nactif = false\n", encoding="utf-8")
    resultats = lancer(dossier)
    assert "toits_deux_pentes" in resultats["generation"]
    assert resultats["generation"]["toits_deux_pentes"] == 0
