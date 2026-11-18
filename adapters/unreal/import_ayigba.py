"""Adaptateur Unreal pour un dossier d'export Ayigba.

NON TESTE DANS UNREAL : ecrit sans Unreal sous la main (17/11/2026, complete le 18/11/2026).

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


def importer_zones(dossier_export, destination="/Game/Ayigba/zones"):
    """Importe chaque zones/*.glb (decoupage de 250 m, voir zones.json) et renvoie {nom_de_zone: [assets]}.

    NON TESTE DANS UNREAL. Meme contrat de donnees que adapters/godot/ayigba_carte.gd :
    zones.json (emprise [ouest, sud, est, nord] en metres, repere local, y vers le nord ; couches avec
    collision et visible = toujours | pres | loin ; distance_detail_m). Ce script ne fait QUE l'import des
    fichiers : le chargement a la demande selon la distance (Level Streaming, World Partition ou acteur
    maison) et les niveaux de detail restent a faire dans le projet. Le glTF est en X = est, Y = haut,
    Z = sud (metres) ; Unreal est en centimetres, Z haut. La conversion exacte faite par l'import n'a pas
    ete verifiee : controler a l'ecran avant de placer quoi que ce soit.
    """
    chemin_zones = os.path.join(dossier_export, "zones.json")
    if not os.path.isfile(chemin_zones):
        unreal.log_error("[Ayigba] zones.json introuvable dans : " + dossier_export)
        return {}
    with open(chemin_zones, encoding="utf-8") as f:
        index = json.load(f)
    taches, noms = [], []
    for z in index.get("zones", []):
        glb = os.path.join(dossier_export, z["fichier"])
        if not os.path.isfile(glb):
            unreal.log_warning("[Ayigba] zone absente : " + glb)
            continue
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", glb)
        t.set_editor_property("destination_path", destination + "/" + z["nom"])
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        taches.append(t)
        noms.append(z["nom"])
    if not taches:
        return {}
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(taches)
    resultat = {n: list(t.get_editor_property("imported_object_paths")) for n, t in zip(noms, taches)}
    vides = [n for n, a in resultat.items() if not a]
    if vides:
        unreal.log_warning("[Ayigba] zones sans asset importe : " + ", ".join(vides[:10]))
    unreal.log("[Ayigba] " + str(len(taches) - len(vides)) + " zones importees sur " + str(len(taches)) + ". Conserver CREDITS.md avec la carte.")
    return resultat
