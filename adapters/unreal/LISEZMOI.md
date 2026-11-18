# Adaptateur Unreal

> **NON TESTÉ DANS UNREAL.** Écrit sans Unreal sous la main (17/11/2026, complété le 18/11/2026). Le script Python n'a jamais été lancé. Seule la conformité du fichier glTF a été vérifiée (voir plus bas).

Importe un dossier d'export ayigba (`carte.glb`, ou `zones/*.glb`) dans un projet Unreal Engine 5.

## Version visée

Unreal Engine 5.4 ou plus récent, import glTF par le cadre **Interchange** (documentation : « Importing glTF Files into Unreal Engine », https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-gltf-files-into-unreal-engine ; script Python Interchange : https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-assets-using-interchange-in-unreal-engine). Cette documentation montre l'import d'un `.glb` par menu (+Add > Import to, ou File > Import Into Level) et un exemple Python qui choisit un pipeline selon l'extension. La version minimale exacte et les limites de l'import glTF d'Interchange n'ont pas pu être lues dans la documentation (pages rendues côté navigateur) : à vérifier.

## Étapes manuelles (les plus sûres)

1. Ouvrir un projet UE5, activer **Interchange** si besoin (Édition > Greffons).
2. Content Browser : *+Add > Import to /Game/Ayigba* et choisir `carte.glb`. Dans la fenêtre « Interchange Pipeline Configuration », régler la conversion d'échelle si la carte arrive 100 fois trop petite ou grande (voir plus bas), puis *Import*.
3. Pour une carte entière dans un niveau : *File > Import Into Level*. Pour les zones : importer les `zones/*.glb` un par un ou par script.
4. Collisions : ouvrir chaque maillage des couches `collision: true` du manifeste (terrain, chaussees, trottoirs, batiments, berges, fond_eau) et régler *Collision Complexity* sur *Use Complex Collision As Simple*.
5. Garder `CREDITS.md` avec le projet.

## Par script

Activer **Python Editor Script Plugin**, copier `import_ayigba.py` dans `Content/Python`, puis dans la console Python de l'éditeur :

```python
import import_ayigba
import_ayigba.importer(r"C:/chemin/vers/export", "/Game/Ayigba")           # carte.glb d'un bloc
import_ayigba.importer_zones(r"C:/chemin/vers/export", "/Game/Ayigba/zones") # zones/*.glb
```

Le script utilise `unreal.AssetImportTask` avec `automated = True`. Des discussions publiques signalent que les options glTF de cette voie sont limitées et que l'import Interchange passe plutôt par `unreal.InterchangeManager` (non essayé ici). Le script avertit si aucun asset n'est importé.

Le chargement à la demande (World Partition, Level Streaming, acteur maison) n'est **pas** fait : `importer_zones` n'importe que les fichiers. Le contrat de données est le même que pour Godot (`zones.json` : `emprise`, couches `collision`, `visible`, `distance_detail_m`).

## Repère et échelle

Fichiers : mètres, Y haut, X = est, Z = sud (`manifeste.json`). Unreal : centimètres, Z haut, main gauche. Si l'import ne convertit pas l'échelle, multiplier par 100 à l'import. **Non vérifié.**

## Ce que le fichier contient (vérifié sans Unreal)

Aucune texture ni couleur de sommet (une couleur = un matériau PBR), POSITION et NORMAL seulement, indices 32 bits, aucune extension requise, mode triangles, un maillage par couche. Primitives jusqu'à 147 021 sommets dans la carte entière d'Ouidah (non vérifié avec l'import glTF d'Unreal). Chaque couleur d'une couche donne un emplacement de matériau (jusqu'à 22 par maillage). Une discussion publique rapporte que l'import glTF d'Interchange ne gère qu'une carte UV : sans objet ici, il n'y a pas de UV.

## Non testé

Tout ce qui se passe dans Unreal : import, échelle, orientation, nombre d'emplacements de matériaux, collisions, temps d'import de la carte entière (plusieurs centaines de milliers de triangles), script Python.

## Crédits obligatoires

`CREDITS.md` doit rester livré avec la carte. Les scripts ne le copient pas.
