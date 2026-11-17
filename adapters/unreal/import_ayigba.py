"""Adaptateur Unreal pour un dossier d'export Ayigba.

NON TESTE : ecrit sans Unreal sous la main, le 17/11/2026.

A lancer dans l'editeur Unreal (greffon « Python Editor Script Plugin » active),
par exemple dans la console Python :

    import import_ayigba
    import_ayigba.importer(r"C:/chemin/vers/export", "/Game/Ayigba")

Unreal travaille en centimetres, Z vers le haut ; le glTF est en metres, Y vers
le haut. L'import glTF d'Unreal fait la conversion : a verifier a l'ecran
(taille et orientation de la carte). Rien n'est converti a la main ici.

Un adaptateur ne fait que convertir : aucune logique de jeu.
"""
import json
import os

import unreal


def importer(dossier_export, destination="/Game/Ayigba"):
    chemin_manifeste = os.path.join(dossier_export, "manifeste.json")
    chemin_glb = os.path.join(dossier_export, "carte.glb")
    if not (os.path.isfile(chemin_manifeste) and os.path.isfile(chemin_glb)):
        unreal.log_error("[Ayigba] manifeste.json ou carte.glb introuvable dans : " + dossier_export)
        return []

    with open(chemin_manifeste, encoding="utf-8") as f:
        manifeste = json.load(f)
    couches = manifeste.get("couches", [])
    avec_collision = [c["nom"] for c in couches if c.get("collision")]

    tache = unreal.AssetImportTask()
    tache.set_editor_property("filename", chemin_glb)
    tache.set_editor_property("destination_path", destination)
    tache.set_editor_property("automated", True)
    tache.set_editor_property("replace_existing", True)
    tache.set_editor_property("save", True)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([tache])

    chemins = list(tache.get_editor_property("imported_object_paths"))
    if not chemins:
        unreal.log_warning("[Ayigba] Aucun asset importe. L'import glTF/Interchange est-il disponible dans cette version d'Unreal ?")
        return []

    nb_collision = 0
    for chemin in chemins:
        unreal.log("[Ayigba] asset importe : " + str(chemin))
        asset = unreal.EditorAssetLibrary.load_asset(chemin)
        if not isinstance(asset, unreal.StaticMesh):
            continue
        nom = asset.get_name()
        if not any(couche in nom for couche in avec_collision):
            continue
        try:
            body = asset.get_editor_property("body_setup")
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            unreal.EditorAssetLibrary.save_loaded_asset(asset)
            nb_collision += 1
        except Exception as e:  # noqa: BLE001
            unreal.log_warning("[Ayigba] collision non reglee pour " + nom + " : " + str(e))

    unreal.log("[Ayigba] Import termine : " + str(len(chemins)) + " assets, " + str(len(couches)) + " couches, "
               + str(nb_collision) + " maillages avec collision complexe. Conserver CREDITS.md avec la carte.")
    return chemins
