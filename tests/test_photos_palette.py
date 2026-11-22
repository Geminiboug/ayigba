"""Palette tirée de photos : le ciel et la végétation sont écartés, mur et toit retrouvés, résultat déterministe."""
import numpy as np
from PIL import Image, ImageDraw

from ayigba import photos_palette as pp


def _photo(chemin):
    im = Image.new("RGB", (400, 300), (120, 170, 230))             # ciel bleu
    d = ImageDraw.Draw(im)
    d.rectangle((0, 110, 400, 300), fill=(215, 190, 150))          # mur ocre
    d.rectangle((0, 100, 400, 140), fill=(150, 60, 45))            # toit de tuile
    d.rectangle((300, 150, 400, 300), fill=(60, 140, 60))          # végétation
    im.save(chemin)


def test_ciel_et_vegetation_ecartes(tmp_path):
    f = tmp_path / "a.jpg"
    _photo(f)
    px = pp.pixels_utiles(f)
    assert len(px) > 0
    bleu = (px[:, 2] > px[:, 0] * 1.3) & (px[:, 2] > px[:, 1])
    vert = (px[:, 1] > px[:, 0] * 1.5) & (px[:, 1] > px[:, 2] * 1.5)
    assert not bleu.any() and not vert.any()


def test_mur_et_toit_retrouves(tmp_path):
    _photo(tmp_path / "a.jpg")
    res = pp.palette_du_lieu(tmp_path)
    assert res["photos_utilisees"] == 1
    mur = np.array(res["murs"][0][0])
    toit = np.array(res["toits"][0][0])
    assert np.abs(mur - np.array([215, 190, 150]) / 255).max() < 0.08
    assert np.abs(toit - np.array([150, 60, 45]) / 255).max() < 0.08


def test_deterministe_et_dossier_vide(tmp_path):
    _photo(tmp_path / "a.jpg")
    assert pp.palette_du_lieu(tmp_path) == pp.palette_du_lieu(tmp_path)
    vide = tmp_path / "vide"
    vide.mkdir()
    assert pp.palette_du_lieu(vide)["photos_utilisees"] == 0


def test_lab_aller_retour():
    rgb = np.array([[0.2, 0.5, 0.8], [0.9, 0.8, 0.6]])
    assert np.allclose(pp.lab_vers_rgb(pp.rgb_vers_lab(rgb)), rgb, atol=1e-3)
