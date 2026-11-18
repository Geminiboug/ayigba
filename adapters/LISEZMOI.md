# Adaptateurs

Un adaptateur convertit le dossier d'export neutre (carte.glb, manifeste.json,
routes.geojson, CREDITS.md) pour un moteur de jeu. Il ne contient aucune logique
de jeu. Les crédits (CREDITS.md) restent obligatoires.

| Moteur | Dossier | État |
|--------|---------|------|
| Godot | voir le projet verif/godot | Vérifié avec le projet verif/godot |
| Unity | adapters/unity | Écrit (import d'un bloc et zones à la demande), **jamais lancé dans Unity** |
| Unreal | adapters/unreal | Écrit (import d'un bloc et de zones, sans chargement à la demande), **jamais lancé dans Unreal** |

Vérifié sans moteur : les .glb passent le validateur officiel Khronos (`node tools/valider_gltf.js <fichier.glb>`, validateur installé hors dépôt dans `/home/olympe/outils_valid`) et `tests/test_export_conformite.py`.
