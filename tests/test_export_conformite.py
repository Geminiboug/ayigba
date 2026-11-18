"""Conformité de l'export pour Unity et Unreal, sans réseau et sans moteur.

Ces tests vérifient des PROPRIÉTÉS du fichier dont dépendent les importeurs (glTFast, Interchange) : indices,
valeurs finies, accesseurs min/max, nœuds, extras. Ils ne prouvent PAS qu'un import fonctionne dans Unity ou
Unreal : aucun des deux n'a été lancé. Le validateur officiel Khronos est lancé à part (voir adapters/).
"""
from __future__ import annotations

import json
import struct

import numpy as np
import pytest

from ayigba.gltf import write_glb
from test_pipeline_synthetique import construire, ville_de_base

TYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NB = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def lire_glb(chemin):
    b = chemin.read_bytes()
    magic, version, total = struct.unpack("<4sII", b[:12])
    assert magic == b"glTF" and version == 2 and total == len(b)
    n, typ = struct.unpack("<I4s", b[12:20])
    assert typ == b"JSON" and n % 4 == 0
    doc = json.loads(b[20:20 + n])
    m, typ2 = struct.unpack("<I4s", b[20 + n:28 + n])
    assert typ2 == b"BIN\x00" and m % 4 == 0
    return doc, b[28 + n:28 + n + m]


def acces(doc, blob, i):
    a = doc["accessors"][i]
    v = doc["bufferViews"][a["bufferView"]]
    dt = np.dtype(TYPES[a["componentType"]]).newbyteorder("<")
    n = a["count"] * NB[a["type"]]
    arr = np.frombuffer(blob, dtype=dt, count=n, offset=v["byteOffset"] + a.get("byteOffset", 0))
    return arr.reshape(a["count"], NB[a["type"]]) if a["type"] != "SCALAR" else arr


def verifier_glb(chemin):
    doc, blob = lire_glb(chemin)
    assert doc["asset"]["version"] == "2.0"
    assert doc["buffers"][0]["byteLength"] == len(blob)
    noms = [n["name"] for n in doc["nodes"]]
    assert len(set(noms)) == len(noms), "noms de nœuds en double"
    meshes = [m["name"] for m in doc["meshes"]]
    assert sorted(meshes) == sorted(noms)               # un seul maillage par couche, nommé comme son nœud
    assert len(doc["scenes"][0]["nodes"]) == len(doc["nodes"])
    for nom in noms:
        assert not nom.lower().endswith(("_col", "-col", "_colonly", "-colonly", "_convcol", "-convcol"))
        assert nom and all(c not in nom for c in "/\\:*?\"<>|"), nom
    for m in doc["meshes"]:
        assert 0 < len(m["primitives"]) <= 256           # Godot perd les surfaces au-delà de 256
        for p in m["primitives"]:
            assert p["mode"] == 4
            ia = doc["accessors"][p["indices"]]
            pa = doc["accessors"][p["attributes"]["POSITION"]]
            idx = acces(doc, blob, p["indices"])
            # indices 32 bits (5125) ou, à défaut, moins de 65 535 sommets par primitive (16 bits)
            assert ia["componentType"] == 5125 or pa["count"] < 65535
            assert ia["count"] % 3 == 0 and idx.max() < pa["count"]
            for nom_attr, i in p["attributes"].items():
                data = acces(doc, blob, i)
                assert np.isfinite(data).all(), nom_attr
            pos = acces(doc, blob, p["attributes"]["POSITION"])
            assert "min" in pa and "max" in pa                # obligatoire pour POSITION (spec glTF 2.0)
            assert np.allclose(pa["min"], pos.min(axis=0)) and np.allclose(pa["max"], pos.max(axis=0))
            nor = acces(doc, blob, p["attributes"]["NORMAL"])
            assert np.allclose(np.linalg.norm(nor, axis=1), 1.0, atol=1e-3)
            assert p["material"] < len(doc["materials"])
    assert "textures" not in doc and "images" not in doc     # couleurs par matériaux, aucune texture
    return doc


def test_gros_maillage_indices_32_bits(tmp_path):
    """Plus de 65 535 sommets dans une primitive : les indices doivent être en 32 bits."""
    n = 30000
    rng = np.random.default_rng(1)
    tris = rng.random((n, 3, 3)) * 100.0
    cols = np.tile([0.5, 0.4, 0.3], (n, 1))
    write_glb(tmp_path / "gros.glb", [("terrain", tris, cols)], extras={"unite": "metre"})
    doc = verifier_glb(tmp_path / "gros.glb")
    p = doc["meshes"][0]["primitives"][0]
    assert doc["accessors"][p["attributes"]["POSITION"]]["count"] > 65535
    assert doc["accessors"][p["indices"]]["componentType"] == 5125


def test_repere_gltf_y_haut(tmp_path):
    """Un point à 7 m d'altitude et 10 m au nord doit sortir en Y = 7, Z = -10 (X = est)."""
    tri = np.array([[[0, 0, 7.0], [5, 0, 7.0], [0, 10.0, 7.0]]])
    write_glb(tmp_path / "t.glb", [("terrain", tri, np.array([[0.5, 0.5, 0.5]]))])
    doc, blob = lire_glb(tmp_path / "t.glb")
    pos = acces(doc, blob, doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
    assert set(pos[:, 1].round(3)) == {7.0}
    assert -10.0 in pos[:, 2].round(3) and 5.0 in pos[:, 0].round(3)


def test_export_synthetique_conforme(tmp_path):
    d = construire(tmp_path, ville_de_base())
    neutre = d / "out" / "neutre"
    doc = verifier_glb(neutre / "carte.glb")
    manifeste = json.loads((neutre / "manifeste.json").read_text(encoding="utf-8"))

    # extras du manifeste cohérents avec le fichier
    extras = doc["scenes"][0]["extras"]
    assert extras["unite"] == "metre" and extras["graine"] == manifeste["graine"]
    assert manifeste["repere"]["unite"] == "metre"
    assert "Y = haut" in manifeste["repere"]["gltf"]

    # un seul maillage par couche, nommé comme dans le manifeste
    noms_manifeste = [c["nom"] for c in manifeste["couches"] if c["triangles"] > 0]
    assert sorted(m["name"] for m in doc["meshes"]) == sorted(noms_manifeste)
    for c in manifeste["couches"]:
        assert isinstance(c["collision"], bool) and c["nom"]
    # triangles du manifeste = indices / 3 du fichier
    par_couche = {m["name"]: sum(doc["accessors"][p["indices"]]["count"] for p in m["primitives"]) // 3 for m in doc["meshes"]}
    for c in manifeste["couches"]:
        if c["triangles"] > 0:
            assert par_couche[c["nom"]] == c["triangles"]
    for f in manifeste["fichiers"]:
        assert (neutre / f).exists(), f

    # zones à la demande (si l'étape optimisation en a produit)
    if (neutre / "zones.json").is_file():
        zones = json.loads((neutre / "zones.json").read_text(encoding="utf-8"))
        assert zones["distance_detail_m"] > 0 and zones["zones"]
        for z in zones["zones"]:
            e = z["emprise"]
            assert len(e) == 4 and e[0] < e[2] and e[1] < e[3]
            zdoc = verifier_glb(neutre / z["fichier"])
            assert sorted(m["name"] for m in zdoc["meshes"]) == sorted(c["nom"] for c in z["couches"])
            assert zdoc["scenes"][0]["extras"]["zone"] == z["nom"]
            for c in z["couches"]:
                assert c["visible"] in ("toujours", "pres", "loin") and isinstance(c["collision"], bool)
