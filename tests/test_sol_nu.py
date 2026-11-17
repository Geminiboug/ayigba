"""Sol nu : la hauteur des toits est retirée du modèle de surface."""
import numpy as np
from pyproj import Transformer

from ayigba.sol_nu import corriger

PAS = 1.0 / 3600.0   # pixel Copernicus, environ 30 m


def _cas(hauteur_bat, presence):
    dem = {"altitudes": np.full((6, 6), 10.0, dtype=np.float32), "ouest": 2.380, "nord": 6.360, "pas": PAS}
    x0, y0 = Transformer.from_crs(4326, 32631, always_xy=True).transform(2.3795, 6.3605)
    g = int(300 / 2.0)
    bat = {"hauteur": np.full((g, g), hauteur_bat, dtype=np.float32), "presence": np.full((g, g), presence, dtype=np.float32),
           "x0": x0, "y0": y0, "pas": 2.0, "epsg": 32631}
    return dem, bat


def test_quartier_couvert_de_toits_abaisse_le_sol():
    dem, bat = _cas(6.0, 0.5)      # moitié de la surface sous des toits de 6 m : la surface vue est relevée de 3 m
    out, st = corriger(dem, bat)
    assert np.allclose(out["altitudes"], 7.0, atol=0.01)
    assert st["correction_max_m"] == 3.0


def test_sans_batiment_rien_ne_change():
    dem, bat = _cas(0.0, 0.0)
    out, st = corriger(dem, bat)
    assert np.array_equal(out["altitudes"], dem["altitudes"])
    assert st["pixels_corriges"] == 0


def test_hors_des_donnees_batiments_rien_ne_change():
    dem, bat = _cas(8.0, 1.0)
    bat["x0"] += 100_000.0           # grille des bâtiments ailleurs
    out, st = corriger(dem, bat)
    assert np.array_equal(out["altitudes"], dem["altitudes"])
    assert st["pixels_hors_donnees"] == 36


def test_garde_fou_jamais_sous_le_terrain_bas_des_environs():
    dem, bat = _cas(80.0, 1.0)      # détection absurde : 80 m de toits partout
    dem["altitudes"][0, 0] = 9.0    # le point le plus bas des environs
    out, st = corriger(dem, bat)
    assert out["altitudes"].min() >= 9.0 - 4.0 - 1e-6     # jamais plus de 4 m sous le terrain bas des environs
    assert st["correction_max_m"] <= 8.0
    assert st["pixels_bornes"] > 0


def test_la_plage_ne_passe_pas_sous_la_mer():
    dem, bat = _cas(6.0, 1.0)
    dem["altitudes"][:] = 1.0        # bord de mer à 1 m, couvert de toits
    out, _ = corriger(dem, bat)
    assert out["altitudes"].min() >= 0.5 - 1e-6


def test_le_dem_original_n_est_pas_modifie():
    dem, bat = _cas(6.0, 1.0)
    avant = dem["altitudes"].copy()
    corriger(dem, bat)
    assert np.array_equal(dem["altitudes"], avant)
