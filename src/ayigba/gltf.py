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

from . import textures as tx

FORBIDDEN_SUFFIXES = ("_col", "-col", "_colonly", "-colonly", "_convcol", "-convcol")  # suffixes d'import interprétés par Godot


def check_name(name: str) -> None:
    if name.lower().endswith(FORBIDDEN_SUFFIXES):
        raise ValueError(f"nom de couche interdit (suffixe de collision réservé par Godot) : {name}")


MAX_COLORS = 32   # couleurs (donc surfaces) par couche : Godot refuse plus de 256 surfaces par maillage et perd le reste en silence
STEPS = (0.0, 0.02, 0.03, 0.04, 0.06, 0.08, 0.12, 0.16, 0.25, 0.5)


def limit_palette(colors: np.ndarray, max_colors: int = MAX_COLORS) -> np.ndarray:
    """Réduit le nombre de couleurs distinctes en arrondissant à un pas de plus en plus grand. Déterministe."""
    col = np.asarray(colors, dtype=np.float64)
    for step in STEPS:
        q = col if step == 0.0 else np.round(col / step) * step
        if len(np.unique(np.round(q, 4), axis=0)) <= max_colors:
            return np.round(q, 4)
    return np.round(np.round(col / 0.5) * 0.5, 4)


def _pad(blob: bytes, fill: bytes) -> bytes:
    return blob + fill * ((4 - len(blob) % 4) % 4)


def _to_linear(rgb) -> list[float]:
    """Couleur sRGB (celle qu'on voit) vers linéaire (celle que glTF attend)."""
    out = []
    for c in rgb:
        c = float(c)
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 5))
    return out


def write_glb(path: Path, layers: list[tuple[str, np.ndarray, np.ndarray]], extras: dict | None = None,
              textures: bool = False, graine: int = 1) -> dict:
    """layers : liste (nom, triangles (T,3,3) en repère local, couleurs sRGB (T,3) entre 0 et 1).
    textures : ajoute des coordonnées de texture (projection plane) et un grain procédural par couche (voir textures.py) ;
    False (défaut) = fichier identique à celui des versions sans textures.
    Renvoie le nombre de triangles écrits par couche."""
    buffer = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    material_of: dict[tuple, int] = {}
    image_of: dict[str, int] = {}   # type de texture -> index de texture glTF
    images, gltf_textures = [], []
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
        t, normals, col = t[ok], normals[ok] / length[ok], limit_palette(np.asarray(colors, dtype=np.float64)[ok])
        if len(t) == 0:
            continue
        kind = tx.type_pour_couche(name) if textures else None
        palette, which = np.unique(col, axis=0, return_inverse=True)
        which = np.asarray(which).reshape(-1)
        primitives = []
        for k, rgb in enumerate(palette):
            sel = which == k
            key = tuple(float(v) for v in rgb) + ((kind,) if kind else ())
            if key not in material_of:
                material_of[key] = len(materials)
                pbr = {"baseColorFactor": _to_linear(key[:3]) + [1.0], "metallicFactor": 0.0, "roughnessFactor": 0.9}
                if kind:
                    if kind not in image_of:
                        raw = tx.png_octets(kind, graine=graine)
                        offset = len(buffer)
                        buffer.extend(_pad(raw, b"\x00"))
                        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw)})
                        images.append({"bufferView": len(views) - 1, "mimeType": "image/png", "name": "grain_" + kind})
                        gltf_textures.append({"sampler": 0, "source": len(images) - 1})
                        image_of[kind] = len(gltf_textures) - 1
                    pbr["baseColorTexture"] = {"index": image_of[kind]}
                materials.append({"name": f"couleur_{len(materials):02d}" + ("_" + kind if kind else ""), "pbrMetallicRoughness": pbr})
            # sommets partagés : lignes [position, normale] glTF dédupliquées (normales arrondies à 4 décimales)
            pos_all = to_gltf(t[sel].reshape(-1, 3))
            nor_all = np.round(to_gltf(np.repeat(normals[sel], 3, axis=0)).astype(np.float64), 4).astype(np.float32)
            if kind:
                loc = t[sel].reshape(-1, 3)
                uv_all = np.round(tx.uv_planaires(loc, np.repeat(normals[sel], 3, axis=0), tx.tuile_m(kind)), 4).astype(np.float32)
                rows = np.concatenate([pos_all, nor_all, uv_all], axis=1)
            else:
                rows = np.concatenate([pos_all, nor_all], axis=1)
            uniq, inverse = np.unique(rows, axis=0, return_inverse=True)
            inverse = np.asarray(inverse).reshape(-1)
            pos = np.ascontiguousarray(uniq[:, :3])
            nor = np.ascontiguousarray(uniq[:, 3:6])
            uvs = np.ascontiguousarray(uniq[:, 6:8]) if kind else None
            idx = inverse.astype("<u4")  # l'ordre des coins de chaque triangle est conservé
            attributes = {}
            if uvs is not None:
                accessors.append({"bufferView": add_view(uvs), "componentType": 5126, "count": len(uvs), "type": "VEC2"})
                attributes["TEXCOORD_0"] = len(accessors) - 1
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
    if images:
        doc["images"] = images
        doc["textures"] = gltf_textures
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
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
