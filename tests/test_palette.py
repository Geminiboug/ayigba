"""Limite de la palette par couche : Godot perd en silence les surfaces au-delà de 256 par maillage."""
import json
import struct

import numpy as np

from ayigba.gltf import MAX_COLORS, limit_palette, write_glb


def _doc(path):
    b = path.read_bytes()
    longueur, _ = struct.unpack("<I4s", b[12:20])
    return json.loads(b[20:20 + longueur])


def test_palette_deja_petite_inchangee():
    col = np.array([[0.1, 0.2, 0.3]] * 5 + [[0.9, 0.8, 0.7]] * 5)
    assert np.allclose(limit_palette(col), np.round(col, 4))


def test_palette_reduite_au_maximum():
    rng = np.random.default_rng(5)
    col = rng.uniform(0.3, 0.7, size=(5000, 3))      # des milliers de teintes presque identiques
    out = limit_palette(col)
    assert len(np.unique(out, axis=0)) <= MAX_COLORS
    assert np.abs(out - col).max() < 0.26             # la couleur reste reconnaissable


def test_palette_deterministe():
    rng = np.random.default_rng(1)
    col = rng.uniform(0, 1, size=(2000, 3))
    assert np.array_equal(limit_palette(col), limit_palette(col.copy()))


def test_glb_couche_a_milliers_de_teintes_reste_sous_256_surfaces(tmp_path):
    rng = np.random.default_rng(2)
    n = 1500
    tris = np.zeros((n, 3, 3))
    tris[:, 1, 0] = 1.0
    tris[:, 2, 1] = 1.0
    tris[:, :, 0] += np.arange(n)[:, None] * 2.0
    col = rng.uniform(0.4, 0.6, size=(n, 3))
    stats = write_glb(tmp_path / "t.glb", [("decors", tris, col)])
    assert stats["decors"] == n                      # aucun triangle perdu
    prims = _doc(tmp_path / "t.glb")["meshes"][0]["primitives"]
    assert 1 <= len(prims) <= MAX_COLORS < 256
