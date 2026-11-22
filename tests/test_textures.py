"""Textures de grain : périodiques, déterministes, sans effet par défaut, glTF cohérent quand elles sont activées."""
import json
import struct

import numpy as np

from ayigba import textures as tx
from ayigba.gltf import write_glb


def _doc(path):
    b = path.read_bytes()
    longueur, _ = struct.unpack("<I4s", b[12:20])
    return json.loads(b[20:20 + longueur]), b


def _couches():
    sol = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]], [[10, 0, 0], [10, 10, 0], [0, 10, 0]]], dtype=np.float64)
    mur = np.array([[[0, 0, 0], [10, 0, 0], [10, 0, 5]], [[0, 0, 0], [10, 0, 5], [0, 0, 5]]], dtype=np.float64)
    c = np.array([[0.8, 0.7, 0.6]] * 2)
    return [("terrain", sol, c), ("batiments", mur, c), ("eau", sol + [20, 0, 0], c)]


def test_grain_periodique_et_deterministe():
    a = tx.grain("crepi", 64, graine=3)
    assert np.array_equal(a, tx.grain("crepi", 64, graine=3))
    assert not np.array_equal(a, tx.grain("crepi", 64, graine=4))
    assert abs(a.mean() - tx.TYPES["crepi"][0]) < 0.01
    # raccord : la différence entre bords opposés est du même ordre que celle de deux pixels voisins
    bord = np.abs(a[0] - a[-1]).mean()
    voisin = np.abs(a[0] - a[1]).mean()
    assert bord < 2.5 * voisin + 0.01


def test_par_defaut_aucune_texture(tmp_path):
    f = tmp_path / "a.glb"
    write_glb(f, _couches())
    doc, _ = _doc(f)
    assert "images" not in doc and "textures" not in doc
    assert all("TEXCOORD_0" not in p["attributes"] for m in doc["meshes"] for p in m["primitives"])


def test_textures_actives(tmp_path):
    f = tmp_path / "t.glb"
    write_glb(f, _couches(), textures=True)
    doc, _ = _doc(f)
    assert len(doc["images"]) == 2                       # crépi (bâtiments) et sol (terrain) ; l'eau reste un aplat
    par_nom = {m["name"]: m for m in doc["meshes"]}
    assert "TEXCOORD_0" in par_nom["terrain"]["primitives"][0]["attributes"]
    assert "TEXCOORD_0" in par_nom["batiments"]["primitives"][0]["attributes"]
    assert "TEXCOORD_0" not in par_nom["eau"]["primitives"][0]["attributes"]
    for acc in doc["accessors"]:
        assert acc["count"] > 0


def test_uv_planaires():
    n = np.array([[0, 0, 1.0], [1.0, 0, 0], [0, 1.0, 0]])
    s = np.array([[6.0, 12.0, 3.0]] * 3)
    uv = tx.uv_planaires(s, n, 3.0)
    assert np.allclose(uv[0], [2.0, 4.0])      # dessus : (x, y)
    assert np.allclose(uv[1], [4.0, 1.0])      # mur orienté est-ouest : (y, z)
    assert np.allclose(uv[2], [2.0, 1.0])      # mur orienté nord-sud : (x, z)


def test_sortie_identique_deux_fois(tmp_path):
    a, b = tmp_path / "a.glb", tmp_path / "b.glb"
    write_glb(a, _couches(), textures=True, graine=5)
    write_glb(b, _couches(), textures=True, graine=5)
    assert a.read_bytes() == b.read_bytes()
