# Adaptateur Godot 4

Vérifié avec Godot 4.7.2 le 17/11/2026, par les bots du dossier `verif/godot` (voir plus bas).

## Utilisation

1. Copier le dossier d'export `out/neutre/` d'un projet dans le projet Godot, par exemple `res://carte/cadjehoun/`.
2. Copier `ayigba_carte.gd` dans le projet.
3. Ajouter un `Node3D` avec ce script. Régler :
   - `dossier` : le dossier copié (il contient `zones.json` et `zones/`) ;
   - `cible` : le joueur ou la caméra ; les zones se chargent autour de lui ;
   - `rayon_chargement` : 600 m par défaut ;
   - `tout_charger` : pour une petite carte ou un test.

Le script charge les zones à la demande, crée les collisions des couches qui en demandent (terrain, chaussées, fond de l'eau, bâtiments) et règle les niveaux de détail : bâtiments réels et décors de près, boîtes simples de loin. Il ne contient aucune logique de jeu.

Repère : X = est, Y = haut, Z = sud, en mètres, origine au centre de la carte. Les routes sont dans `routes_local.json` (x, y en mètres ; dans Godot : X = x, Z = -y).

## Mentions obligatoires

Le fichier `CREDITS.md` de l'export donne les mentions à afficher dans le jeu (OpenStreetMap, licence ODbL).

## Vérification par des bots

```bash
godot --headless --path verif/godot --script res://bots_routes.gd -- export=<dossier out/neutre> routes=0
```

Il faut d'abord copier `ayigba_carte.gd` dans `verif/godot/`. Des personnages suivent toutes les routes avec la physique du moteur. Un blocage révèle un mur invisible ou un obstacle sur une route, une chute révèle un trou.

## Limites

- Les zones sont lues à l'exécution avec `GLTFDocument` : le chargement d'une zone prend un instant. Un jeu peut préférer importer les fichiers `.glb` dans l'éditeur.
- Les collisions sont des maillages exacts (trimesh), sans simplification.
- Pas testé sur Android ni avec une manette : l'adaptateur n'a été lancé que sous Windows, sans affichage.
