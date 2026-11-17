"""Écriture d'un fichier glTF binaire (.glb) minimal : un nœud par couche, un matériau par couleur.

Les couleurs passent par des matériaux (baseColorFactor) et non par des couleurs de sommets : tous les moteurs
affichent un matériau glTF sans réglage, alors que les couleurs de sommets demandent une option (constaté dans Godot 4.7).

Passage du repère local (x est, y nord, z haut) au repère glTF (Y vers le haut, main droite) :
X = x, Y = z, Z = -y. C'est une rotation : le sens des triangles est conservé.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

FORBIDDEN_SUFFIXES = ("_col", "-col", "_colonly", "-colonly", "_convcol", "-convcol")  # suffixes d'import interprétés par Godot


def check_name(name: str) -> None:
    if name.lower().endswith(FORBIDDEN_SUFFIXES):
        raise ValueError(f"nom de couche interdit (suffixe de collision réservé par Godot) : {name}")


def _pad(blob: bytes, fill: bytes) -> bytes:
    return blob + fill * ((4 - len(blob) % 4) % 4)


def _to_linear(rgb) -> list[float]:
    """Couleur sRGB (celle qu'on voit) vers linéaire (celle que glTF attend)."""
    out = []
    for c in rgb:
        c = float(c)
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 5))
    return out


def write_glb(path: Path, layers: list[tuple[str, np.ndarray, np.ndarray]], extras: dict | None = None) -> dict:
    """layers : liste (nom, triangles (T,3,3) en repère local, couleurs sRGB (T,3) entre 0 et 1).
    Renvoie le nombre de triangles écrits par couche."""
    buffer = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    material_of: dict[tuple, int] = {}
    stats = {}

    def add_view(data: np.ndarray, target: int = 34962) -> int:
        offset = len(buffer)
        raw = data.tobytes()
        buffer.extend(_pad(raw, b"\x00"))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw), "target": target})
        return len(views) - 1

    def to_gltf(v: np.ndarray) -> np.ndarray:
        return np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)

    for name, tris, colors in layers:
        check_name(name)
        if len(tris) == 0:
            continue
        t = np.asarray(tris, dtype=np.float64)
        normals = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        ok = length[:, 0] > 1e-12
        t, normals, col = t[ok], normals[ok] / length[ok], np.round(np.asarray(colors, dtype=np.float64)[ok], 4)
        if len(t) == 0:
            continue
        palette, which = np.unique(col, axis=0, return_inverse=True)
        which = np.asarray(which).reshape(-1)
        primitives = []
        for k, rgb in enumerate(palette):
            sel = which == k
            key = tuple(float(v) for v in rgb)
            if key not in material_of:
                material_of[key] = len(materials)
                materials.append({"name": f"couleur_{len(materials):02d}", "pbrMetallicRoughness": {
                    "baseColorFactor": _to_linear(key) + [1.0], "metallicFactor": 0.0, "roughnessFactor": 0.9}})
            # sommets partagés : lignes [position, normale] glTF dédupliquées (normales arrondies à 4 décimales)
            pos_all = to_gltf(t[sel].reshape(-1, 3))
            nor_all = np.round(to_gltf(np.repeat(normals[sel], 3, axis=0)).astype(np.float64), 4).astype(np.float32)
            rows = np.concatenate([pos_all, nor_all], axis=1)
            uniq, inverse = np.unique(rows, axis=0, return_inverse=True)
            inverse = np.asarray(inverse).reshape(-1)
            pos = np.ascontiguousarray(uniq[:, :3])
            nor = np.ascontiguousarray(uniq[:, 3:])
            idx = inverse.astype("<u4")  # l'ordre des coins de chaque triangle est conservé
            attributes = {}
            for attr, data in (("POSITION", pos), ("NORMAL", nor)):
                acc = {"bufferView": add_view(data), "componentType": 5126, "count": len(pos), "type": "VEC3"}
                if attr == "POSITION":
                    acc["min"] = [float(v) for v in pos.min(axis=0)]
                    acc["max"] = [float(v) for v in pos.max(axis=0)]
                accessors.append(acc)
                attributes[attr] = len(accessors) - 1
            accessors.append({"bufferView": add_view(idx, 34963), "componentType": 5125, "count": len(idx), "type": "SCALAR"})
            primitives.append({"attributes": attributes, "indices": len(accessors) - 1, "material": material_of[key], "mode": 4})
        meshes.append({"name": name, "primitives": primitives})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
        stats[name] = int(len(t))

    doc = {
        "asset": {"version": "2.0", "generator": "ayigba"},
        "scene": 0,
        "scenes": [{"name": "carte", "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buffer)}],
    }
    if extras:
        doc["scenes"][0]["extras"] = extras
    js = _pad(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), b" ")
    total = 12 + 8 + len(js) + 8 + len(buffer)
    with Path(path).open("wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON"))
        f.write(js)
        f.write(struct.pack("<I4s", len(buffer), b"BIN\x00"))
        f.write(bytes(buffer))
    return stats
