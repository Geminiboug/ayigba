# Chantier ayigba : plan et avancement

Écrit pour : Olympe, et tout agent qui reprend le travail. Mis à jour le 17/11/2026.

Règles de travail : ne rien pousser sans demande d'Olympe ; pas de co-auteur dans les commits ; ne jamais écrire le nom d'une marque ou d'une œuvre protégée ; dire ce qui n'est pas vérifié. Organisation : l'agent principal fait les tâches difficiles (conception, géométrie, contrôles) ; les tâches bien délimitées (tests, modules simples à contrat écrit) sont déléguées à des sous-agents, puis relues.

## Décisions prises

| Date | Décision | Par |
|---|---|---|
| 17/11/2026 | Langage du moteur : Python | Olympe |
| 17/11/2026 | Premier quartier : Cadjèhoun et l'aéroport de Cotonou | Olympe |
| 17/11/2026 | Nom du dépôt : ayigba (sens à confirmer par Olympe) | Olympe |
| 17/11/2026 | Pas de licence d'utilisation pour l'instant (tous droits réservés) | par défaut, à confirmer |

## Décisions en attente (à demander à Olympe avant d'agir)

- Sources d'images de rue réellement utilisables (Mapillary, vidéos d'Olympe).
- Moment d'entraînement de l'IA de style.
- Licence du code.
- Budgets de performance par zone (triangles, objets) pour viser 70 images par seconde.

## Avancement par étape de la spec

| N° | Étape | État | Détail |
|---|---|---|---|
| 1 | Squelette, configuration par ville, journal, reprise | **fait** | `config.py`, `project.py`, `journal.py`, `pipeline.py` ; 27 tests |
| 2 | Collecte et nettoyage sur un quartier | **fait pour OpenStreetMap** | reste : Google Open Buildings et Microsoft (couverture du Bénin à vérifier), relief Copernicus ou SRTM, images |
| 3 | Génération de base | **fait, version simple** | routes, bâtiments, eau, sol plat ; reste : relief, toits, trottoirs, carrefours dessinés, passages piétons, végétation, décors, points d'intérêt en 3D |
| 4 | Tests par bots, correction, rapport | **partiel** | contrôles de géométrie, marcheur sur grille, rapport ; reste : bots dans un moteur, navmesh, boucle de correction après les tests, comparaison avant/après |
| 5 | Génération de secours | à faire | l'étape existe et ne fait rien |
| 6 | Export Godot et vérification dans un vrai Godot | **partiel** | l'export neutre s'ouvre dans Godot 4.7.2, test de rayons sans trou ; reste : adaptateur Godot (scène avec collisions prêtes, données de routes) |
| 7 | Optimisation | à faire | niveaux de détail, découpage en zones, budgets |
| 8 | Interface Tauri | à faire | |
| 9 | IA de style | à faire | commencer par des règles et une classification |
| 10 | Adaptateurs Unity et Unreal | à faire | |
| 11 | Autres villes | à faire | Ouidah, Porto-Novo, Parakou |

## Résultat mesuré sur Cadjèhoun (17/11/2026)

- Zone de 7,3 km² : 5 705 éléments OpenStreetMap, 625 routes (119 km), 4 272 bâtiments, 11 ha d'eau, 366 points d'intérêt.
- Carte : 90 612 triangles, fichier de 6,5 Mo, produite en moins de 10 secondes après la collecte.
- Rapport de qualité : 0 erreur ; 99,9 % de la surface libre accessible à pied depuis les routes ; 2 poches inaccessibles (400 m²) ; 5 routes isolées (416 m).
- Godot 4.7.2 : chargement sans erreur ; 0 trou sur 32 487 rayons (un rayon tous les 15 m).
- Reproductibilité : deux exécutions donnent le même `carte.glb` (même empreinte SHA-256).
- 72 tests automatiques passent.

## Critères d'acceptation de la spec

| Critère | État |
|---|---|
| Une commande génère un quartier complet | oui, à partir d'une zone ; pas encore à partir du seul nom d'une ville |
| Zéro mur invisible, zéro trou, zéro zone inaccessible selon les bots | zéro trou : oui (calcul et rayons Godot) ; murs invisibles : non testé ; zones inaccessibles : 2 poches signalées, non corrigées |
| Toute zone sans données est comblée et marquée | non (étape de secours à faire) ; le marquage `source = genere` existe |
| L'export s'ouvre dans Godot sans erreur | oui pour Godot 4.7.2 ; Unity et Unreal non testés |
| Même graine, même résultat | oui, vérifié par test |
| Fonctionne hors ligne après la première collecte | oui, vérifié par test |
| Fichier de sources et licences généré | oui |
| Aucune logique de jeu dans le cœur | oui |

## Prochaines tâches, dans l'ordre

1. **Corriger après les tests** : fermer ou ouvrir les poches inaccessibles, relier ou retirer les routes isolées, puis retester jusqu'à zéro avertissement ou limite de tentatives.
2. **Génération de secours** : repérer les îlots vides entourés de routes, les remplir de bâtiments cohérents avec les îlots voisins, marqués `genere`.
3. **Deuxième source de bâtiments** : vérifier la couverture réelle de Google Open Buildings au Bénin, fusionner avec OpenStreetMap, enregistrer la licence.
4. **Adaptateur Godot** : scène prête à l'emploi (collisions, couches séparées, routes pour le GPS), testée par un personnage qui marche dans le projet de vérification.
5. **Découpage en zones et niveaux de détail**, avec un budget par zone.
6. **Routes plus vraies** : carrefours, ronds-points, trottoirs, passages piétons, sens de circulation exportés.
7. **Relief** : modèle d'élévation libre, bas-fonds et lagune.
8. **Deuxième ville** (Ouidah) pour vérifier que rien n'est propre à Cotonou.

## Pièges rencontrés

- Arrondir les coordonnées d'un polygone peut le rendre invalide : `geo.write_features` le recale avec `shapely.set_precision`.
- Dans Godot, un rayon qui tombe pile sur une arête entre deux triangles peut passer au travers : le test tire des rayons décalés avant de conclure à un trou.
- Godot affiche en blanc un glTF coloré par sommets : les couleurs passent par des matériaux.
- Les largeurs de rue par défaut sont trop larges pour Cotonou : 485 bâtiments étaient rognés à tort avant la règle « la rue se rétrécit avant le mur ».
- Godot pour Windows n'écrit pas de façon fiable dans un dossier WSL : le projet de vérification et la carte ont été copiés sur un disque Windows avant le test.
