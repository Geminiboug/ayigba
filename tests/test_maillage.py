"""Tests du maillage (mesh.py) et de l'export glTF (gltf.py)."""
import json
import struct

import numpy as np
import pytest
from shapely.geometry import Polygon

from ayigba import gltf
from ayigba.mesh import MeshBuilder, load_mesh, rng_for, triangulate

CARRE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
TROU = Polygon([(4, 4), (6, 4), (6, 6), (4, 6)])


def aires_signees(tris):
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    return 0.5 * ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def normales(tris):
    return np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])


# 1. rng_for
def test_rng_meme_graine_meme_cle():
    a = [rng_for(42, "x").random() for _ in range(1)]
    b = [rng_for(42, "x").random() for _ in range(1)]
    assert a == b
    r1, r2 = rng_for(42, "x"), rng_for(42, "x")
    assert [r1.random() for _ in range(10)] == [r2.random() for _ in range(10)]


def test_rng_cle_differente():
    assert rng_for(42, "x").random() != rng_for(42, "y").random()


def test_rng_graine_differente():
    assert rng_for(1, "x").random() != rng_for(2, "x").random()


# 2. triangulate
def test_triangulate_carre():
    t = triangulate(CARRE)
    assert len(t) == 2
    ai = aires_signees(t)
    assert ai.sum() == pytest.approx(100)
    assert (ai > 0).all()


def test_triangulate_carre_avec_trou():
    t = triangulate(Polygon(CARRE.exterior.coords, [TROU.exterior.coords]))
    ai = aires_signees(t)
    assert ai.sum() == pytest.approx(96)
    assert (ai > 0).all()


def test_triangulate_sens_horaire():
    horaire = Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])
    ai = aires_signees(triangulate(horaire))
    assert (ai > 0).all()
    assert ai.sum() == pytest.approx(100)


def test_triangulate_polygone_en_L():
    ell = Polygon([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
    ai = aires_signees(triangulate(ell))
    assert ai.sum() == pytest.approx(ell.area)
    assert ai.sum() == pytest.approx(64)
    assert (ai > 0).all()


# 3. add_flat
def test_add_flat_altitude_et_normale():
    m = MeshBuilder("sol")
    m.add_flat(CARRE, 2.5, (1, 0, 0))
    t = m.triangles
    assert len(t) == 2
    assert np.allclose(t[:, :, 2], 2.5)
    assert (normales(t)[:, 2] > 0).all()
    assert len(m.colors) == 2


# 4. add_walls
def test_add_walls_carre():
    m = MeshBuilder("murs")
    m.add_walls(CARRE, 0, 3, (0.5, 0.5, 0.5))
    t = m.triangles
    assert len(t) == 8
    n = normales(t)
    assert 0.5 * np.linalg.norm(n, axis=1).sum() == pytest.approx(120)
    assert np.allclose(n[:, 2], 0)
    centre = np.array([5.0, 5.0, 0.0])
    cg = t.mean(axis=1)
    for ni, ci in zip(n, cg):
        v = ci - np.array([centre[0], centre[1], ci[2]])
        assert np.dot(ni, v) > 0


def test_add_walls_trou_vers_l_interieur_du_trou():
    m = MeshBuilder("murs")
    m.add_walls(Polygon(CARRE.exterior.coords, [TROU.exterior.coords]), 0, 3, (1, 1, 1))
    t = m.triangles
    assert len(t) == 16
    n = normales(t)
    cg = t.mean(axis=1)
    centre = np.array([5.0, 5.0])
    dans_trou = [i for i in range(len(t)) if 4 - 1e-9 <= cg[i, 0] <= 6 + 1e-9 and 4 - 1e-9 <= cg[i, 1] <= 6 + 1e-9]
    assert len(dans_trou) == 8
    for i in range(len(t)):
        v = cg[i, :2] - centre
        d = np.dot(n[i, :2], v)
        if i in dans_trou:
            assert d < 0  # vers le centre du trou, loin de la matiere
        else:
            assert d > 0


# 5. add_prism
def test_add_prism_murs_et_toit():
    m = MeshBuilder("bat")
    m.add_prism(CARRE, 0, 3, (0.5, 0.5, 0.5), (0.9, 0.1, 0.1))
    t = m.triangles
    assert len(t) == 10
    toit = t[np.all(t[:, :, 2] == 3, axis=1)]
    assert len(toit) == 2
    assert (normales(toit)[:, 2] > 0).all()
    assert np.allclose(m.colors[-2:], np.float32([0.9, 0.1, 0.1]))
    assert np.allclose(m.colors[:8], np.float32([0.5, 0.5, 0.5]))


# 6. save / load
def test_save_puis_load(tmp_path):
    m = MeshBuilder("bat")
    m.add_prism(CARRE, 0, 3.3, (0.5, 0.4, 0.3), (0.9, 0.1, 0.1))
    chemin = tmp_path / "bat.npz"
    n = m.save(chemin)
    assert n == len(m.triangles)
    t, c = load_mesh(chemin)
    assert t.shape == m.triangles.shape
    assert np.allclose(t, m.triangles, atol=1e-4)
    assert np.allclose(c, m.colors)


# 7. check_name
@pytest.mark.parametrize("nom", ["mur_col", "sol-col", "X_COLONLY"])
def test_check_name_refuse(nom):
    with pytest.raises(ValueError):
        gltf.check_name(nom)


@pytest.mark.parametrize("nom", ["batiments", "colline"])
def test_check_name_accepte(nom):
    gltf.check_name(nom)


# 8. write_glb
def lire_glb(chemin):
    data = chemin.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    ljson, tjson = struct.unpack_from("<I4s", data, 12)
    doc = json.loads(data[20:20 + ljson].decode("utf-8"))
    off = 20 + ljson
    lbin, tbin = struct.unpack_from("<I4s", data, off)
    binaire = data[off + 8:off + 8 + lbin]
    return data, magic, version, total, ljson, tjson, lbin, tbin, doc, binaire


def lire_prim(doc, binaire, prim):
    """Renvoie (positions, normales, indices) d'une primitive."""
    def lire(acc_i, dtype, n):
        a = doc["accessors"][acc_i]
        v = doc["bufferViews"][a["bufferView"]]
        return np.frombuffer(binaire, dtype=dtype, count=a["count"] * n, offset=v["byteOffset"])
    pos = lire(prim["attributes"]["POSITION"], "<f4", 3).reshape(-1, 3)
    nor = lire(prim["attributes"]["NORMAL"], "<f4", 3).reshape(-1, 3)
    return pos, nor, lire(prim["indices"], "<u4", 1)


def test_write_glb_structure_et_axes(tmp_path):
    chemin = tmp_path / "t.glb"
    tris = np.array([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]], dtype=float)
    stats = gltf.write_glb(chemin, [("couche", tris, np.array([[1.0, 0.5, 0.25]])), ("vide", np.zeros((0, 3, 3)), np.zeros((0, 3)))])
    data, magic, version, total, ljson, tjson, lbin, tbin, doc, binaire = lire_glb(chemin)
    assert stats == {"couche": 1}
    assert magic == b"glTF" and version == 2
    assert total == len(data)
    assert tjson == b"JSON" and tbin == b"BIN\x00"
    assert ljson % 4 == 0 and lbin % 4 == 0

    assert [n["name"] for n in doc["nodes"]] == ["couche"]
    prim = doc["meshes"][0]["primitives"][0]
    assert set(prim["attributes"]) == {"POSITION", "NORMAL"}
    acc = doc["accessors"][prim["attributes"]["POSITION"]]
    assert acc["count"] == 3 and "min" in acc and "max" in acc

    pos, nor, idx = lire_prim(doc, binaire, prim)
    assert np.allclose(pos[idx[2]], (0, 0, -1))
    assert np.allclose(pos[idx[1]], (1, 0, 0))
    assert np.allclose(nor[idx[0]], (0, 1, 0))
    # la couleur passe par un matériau, convertie de sRGB en linéaire
    base = doc["materials"][prim["material"]]["pbrMetallicRoughness"]["baseColorFactor"]
    assert np.allclose(base, (1.0, 0.21404, 0.05088, 1.0), atol=1e-4)


def test_write_glb_couche_vide_absente(tmp_path):
    chemin = tmp_path / "v.glb"
    gltf.write_glb(chemin, [("vide", np.zeros((0, 3, 3)), np.zeros((0, 3)))])
    doc = lire_glb(chemin)[8]
    assert doc["nodes"] == []


def test_write_glb_nom_interdit(tmp_path):
    tris = np.array([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]], dtype=float)
    with pytest.raises(ValueError):
        gltf.write_glb(tmp_path / "x.glb", [("mur_col", tris, np.array([[1.0, 1.0, 1.0]]))])


def _glb_prim(tmp_path, tris, nom="f.glb"):
    chemin = tmp_path / nom
    gltf.write_glb(chemin, [("c", tris, np.tile([[0.5, 0.5, 0.5]], (len(tris), 1)))])
    lu = lire_glb(chemin)
    doc, binaire = lu[8], lu[9]
    return doc, binaire, doc["meshes"][0]["primitives"][0]


def test_write_glb_carre_partage_ses_sommets(tmp_path):
    tris = np.array([[(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 0, 0), (1, 1, 0), (0, 1, 0)]], dtype=float)
    doc, binaire, prim = _glb_prim(tmp_path, tris)
    pos, nor, idx = lire_prim(doc, binaire, prim)
    assert len(pos) == 4 and len(idx) == 6
    assert doc["accessors"][prim["attributes"]["POSITION"]]["count"] == 4


def test_write_glb_relecture_memes_triangles(tmp_path):
    rng = np.random.default_rng(1234)
    tris = rng.uniform(-50, 50, size=(50, 3, 3))
    doc, binaire, prim = _glb_prim(tmp_path, tris)
    pos, nor, idx = lire_prim(doc, binaire, prim)
    relus = pos[idx].reshape(-1, 3, 3)
    attendu = np.stack([tris[:, :, 0], tris[:, :, 2], -tris[:, :, 1]], axis=2)
    assert len(relus) == 50
    restants = list(range(50))
    for tri in relus:  # même triangle, mêmes coins dans le même ordre
        for i in restants:
            if np.allclose(tri, attendu[i], atol=1e-5):
                restants.remove(i)
                break
        else:
            pytest.fail("triangle relu absent de l'entrée")
    assert not restants


def test_write_glb_normales_differentes_ne_fusionnent_pas(tmp_path):
    # coin de boîte : un sol et un mur qui partagent l'arête (0,0,0)-(1,0,0)
    tris = np.array([[(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 0), (1, 0, 0), (0, 0, 1)]], dtype=float)
    doc, binaire, prim = _glb_prim(tmp_path, tris)
    pos, nor, idx = lire_prim(doc, binaire, prim)
    assert len(pos) == 6
    assert len(set(idx[:3]) & set(idx[3:])) == 0


def test_write_glb_deterministe(tmp_path):
    rng = np.random.default_rng(7)
    tris = rng.uniform(-5, 5, size=(30, 3, 3))
    cols = np.tile([[0.2, 0.4, 0.6]], (30, 1))
    gltf.write_glb(tmp_path / "a.glb", [("c", tris, cols)])
    gltf.write_glb(tmp_path / "b.glb", [("c", tris, cols)])
    assert (tmp_path / "a.glb").read_bytes() == (tmp_path / "b.glb").read_bytes()


def test_write_glb_accessor_indices(tmp_path):
    tris = np.array([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]], dtype=float)
    doc, binaire, prim = _glb_prim(tmp_path, tris)
    acc = doc["accessors"][prim["indices"]]
    assert acc["componentType"] == 5125 and acc["type"] == "SCALAR" and acc["count"] == 3
    assert doc["bufferViews"][acc["bufferView"]]["target"] == 34963
    assert doc["bufferViews"][doc["accessors"][prim["attributes"]["POSITION"]]["bufferView"]]["target"] == 34962
