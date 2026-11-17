"""Tests du géocodage et de la création de projet (aucun accès réseau)."""
import json
import urllib.error

import pytest

from ayigba.config import load_config
from ayigba.geocode import bbox_around, create_project, geocode, slugify


class FausseReponse:
    def __init__(self, donnees):
        self._octets = json.dumps(donnees).encode("utf-8")

    def read(self):
        return self._octets

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FauxOpener:
    def __init__(self, donnees=None, erreur=None):
        self.donnees = donnees
        self.erreur = erreur
        self.appels = []

    def __call__(self, req, timeout=None):
        self.appels.append((req, timeout))
        if self.erreur:
            raise self.erreur
        return FausseReponse(self.donnees)


COTONOU = [{"lat": "6.36", "lon": "2.42", "display_name": "Cotonou, Littoral, Bénin"}]


def test_slugify():
    assert slugify("Porto-Novo, Bénin") == "porto-novo-benin"
    assert slugify("  Côte   d'Ivoire !! ") == "cote-d-ivoire"
    assert slugify("Cotonou") == "cotonou"


def test_geocode_url_et_user_agent():
    op = FauxOpener(COTONOU)
    res = geocode("Porto-Novo, Bénin", opener=op)
    assert res == {"lat": 6.36, "lon": 2.42, "nom_complet": "Cotonou, Littoral, Bénin"}
    assert len(op.appels) == 1
    req = op.appels[0][0]
    assert req.full_url == (
        "https://nominatim.openstreetmap.org/search?q=Porto-Novo%2C+B%C3%A9nin&format=jsonv2&limit=1"
    )
    assert req.get_header("User-agent") == "ayigba/0.1 (generateur de cartes ; https://github.com/Geminiboug/ayigba)"


def test_geocode_reponse_vide():
    with pytest.raises(LookupError, match="Lieu introuvable : Nulle part"):
        geocode("Nulle part", opener=FauxOpener([]))


def test_geocode_erreur_reseau():
    op = FauxOpener(erreur=urllib.error.URLError("coupé"))
    with pytest.raises(RuntimeError, match="Impossible de joindre"):
        geocode("Cotonou", opener=op)
    assert len(op.appels) == 1


def test_bbox_cotonou():
    ouest, sud, est, nord = bbox_around(6.36, 2.42, 1.5)
    assert nord - sud == pytest.approx(0.02695, abs=1e-4)
    assert est - ouest == pytest.approx(0.02712, abs=1e-4)
    assert (ouest + est) / 2 == pytest.approx(2.42, abs=1e-5)
    assert (sud + nord) / 2 == pytest.approx(6.36, abs=1e-5)


@pytest.mark.parametrize("rayon", [0, -1, 20.1])
def test_bbox_rayon_invalide(rayon):
    with pytest.raises(ValueError):
        bbox_around(6.36, 2.42, rayon)


def test_create_project(tmp_path):
    dossier = create_project(tmp_path, "Cotonou, Bénin", rayon_km=1.5, graine=42, opener=FauxOpener(COTONOU))
    assert dossier == tmp_path / "cotonou-benin"
    cfg = load_config(dossier / "config.toml")
    assert cfg.bbox == bbox_around(6.36, 2.42, 1.5)
    assert cfg.seed == 42
    assert cfg.city == "Cotonou, Bénin"
    assert cfg.engine == "neutre"


def test_create_project_nom_avec_guillemet(tmp_path):
    dossier = create_project(tmp_path, 'Rue "Test" \\ ici', opener=FauxOpener(COTONOU))
    assert load_config(dossier / "config.toml").city == 'Rue "Test" \\ ici'


def test_create_project_existant(tmp_path):
    dossier = create_project(tmp_path, "Cotonou", opener=FauxOpener(COTONOU))
    fichier = dossier / "config.toml"
    avant = fichier.read_bytes()
    with pytest.raises(FileExistsError, match="existe déjà"):
        create_project(tmp_path, "Cotonou", graine=99, opener=FauxOpener(COTONOU))
    assert fichier.read_bytes() == avant
