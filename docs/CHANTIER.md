# Chantier ayigba : plan et avancement

Écrit pour : Olympe, et tout agent qui reprend le travail. Mis à jour le 17/11/2026 (version 0.2).

Règles de travail : ne rien pousser sans demande d'Olympe ; pas de co-auteur dans les commits ; ne jamais écrire le nom d'une marque ou d'une œuvre protégée ; dire ce qui n'est pas vérifié. Organisation : l'agent principal fait les tâches difficiles (conception, géométrie, contrôles, moteur) ; les tâches bien délimitées (tests, modules simples à contrat écrit) sont déléguées à des sous-agents, puis relues.

## Décisions prises

| Date | Décision | Par |
|---|---|---|
| 17/11/2026 | Langage du moteur : Python | Olympe |
| 17/11/2026 | Premier quartier : Cadjèhoun et l'aéroport de Cotonou | Olympe |
| 17/11/2026 | Nom du dépôt : ayigba (sens à confirmer par Olympe) | Olympe |
| 17/11/2026 | Pas de licence d'utilisation pour l'instant (tous droits réservés) | par défaut, à confirmer |
| 17/11/2026 | Le secours passe avant la génération des maillages (la spec le plaçait après) : les éléments générés suivent ainsi les mêmes contrôles que les données réelles | agent principal, à confirmer |

## Décisions en attente (à demander à Olympe avant d'agir)

- Sources d'images de rue réellement utilisables (Mapillary, vidéos d'Olympe).
- Moment d'entraînement de l'IA de style.
- Licence du code.
- Une cour fermée est comblée par un volume plein de 3 m. Alternative possible : ouvrir un passage dans un mur. À trancher.
- Un îlot n'est rempli que s'il est totalement vide (`[secours] densite_ilot_vide = 0`). Faut-il aussi compléter les îlots à moitié vides ?

## Avancement par étape de la spec

| N° | Étape | État | Détail |
|---|---|---|---|
| 1 | Squelette, configuration, journal, reprise | **fait** | |
| 2 | Collecte et nettoyage | **fait pour OpenStreetMap** | reste : empreintes de bâtiments Google et Microsoft (couverture du Bénin à vérifier), relief, images |
| 3 | Génération de base | **fait, version simple** | routes, bâtiments, auvents, eau, sol plat, décors ; reste : relief, toits en pente, trottoirs, carrefours dessinés, passages piétons, façades |
| 4 | Tests par bots, correction, rapport | **fait** | contrôles de géométrie, accessibilité exacte, bots marcheurs dans Godot sur toutes les routes, comparaison avant/après et retour en arrière ; reste : bots en véhicule, navmesh, bots hors des routes |
| 5 | Génération de secours | **fait, première version** | routes isolées reliées ou retirées, îlots vides remplis, cours fermées comblées ; tout est marqué `genere` |
| 6 | Export Godot et vérification dans un vrai Godot | **fait** | adaptateur `adapters/godot/ayigba_carte.gd` (zones à la demande, collisions, niveaux de détail), vérifié par les bots |
| 7 | Optimisation | **fait, première version** | zones de 250 m, deux niveaux de détail pour les bâtiments, budget par zone ; reste : fichiers plus compacts (sommets partagés), simplification du sol |
| 8 | Interface Tauri | à faire | |
| 9 | IA de style | à faire | commencer par des règles et une classification |
| 10 | Adaptateurs Unity et Unreal | **écrits, NON TESTÉS** | `adapters/unity`, `adapters/unreal` : aucun des deux moteurs n'était disponible |
| 11 | Autres villes | **Ouidah fait** | créée par son seul nom, sans changer le code ; reste : Porto-Novo, Parakou |

## Résultats mesurés (17/11/2026)

| Mesure | Cotonou, Cadjèhoun | Ouidah |
|---|---|---|
| Zone | 7,3 km² | 8,9 km² |
| Bâtiments (dont générés) | 4 302 (28) | 7 985 (140) |
| Routes | 623, 118,9 km | 602, 129,6 km |
| Décors | 2 648 | 3 243 |
| Triangles (carte entière) | 157 000 | 216 000 |
| Zones de 250 m | 126 | 144 |
| Triangles au plus dans une zone, de près | 3 394 | 4 005 |
| Erreurs et avertissements du rapport | 0 et 0 | 0 et 0 |
| Surface libre accessible à pied | 100 % | 100 % |
| Bots dans Godot : routes sans défaut | 623 sur 623 (118,6 km) | 602 sur 602 (129,4 km) |
| Bots : blocages, chutes | 0, 0 | 0, 0 |

Autres vérifications : `carte.glb` de Cadjèhoun ouverte dans Godot 4.7.2, 0 trou sur 32 487 rayons ; même entrée et même graine donnent les mêmes fichiers (test automatique) ; 120 tests automatiques passent.

## Critères d'acceptation de la spec

| Critère | État |
|---|---|
| Une commande génère un quartier à partir d'un nom de ville ou d'une zone | oui : `ayigba creer "Ouidah, Bénin"` puis `ayigba generer` |
| Zéro mur invisible, zéro trou, zéro zone inaccessible selon les bots | oui pour un piéton sur les routes (bots Godot) et pour l'accessibilité de tout l'espace libre (calcul) ; non testé : véhicules, déplacement hors des routes dans le moteur |
| Toute zone sans données est comblée et marquée | en partie : îlots totalement vides et cours fermées ; les zones vides sans routes ne sont pas traitées |
| L'export s'ouvre dans Godot sans erreur | oui (4.7.2) ; Unity et Unreal non testés |
| Même graine, même résultat | oui, vérifié par test |
| Hors ligne après la première collecte | oui, vérifié par test |
| Fichier de sources et licences généré | oui |
| Aucune logique de jeu dans le cœur | oui |

## Ce qui n'est pas fait ou pas vérifié

- Relief : le terrain est plat. Les bas-fonds et la lagune n'ont pas de pente.
- Toits en pente, façades, trottoirs, carrefours dessinés, passages piétons, ponts (rendus comme des remblais), plafond des passages couverts (ouverts à ciel ouvert).
- Sources autres qu'OpenStreetMap. Presque toutes les hauteurs de bâtiments sont estimées par une règle simple.
- Les décors n'ont pas de collision. Leur placement suit des règles simples, pas une observation du terrain.
- Bots en véhicule, navmesh, bots qui quittent les routes.
- Interface graphique, IA de style, édition manuelle.
- Unity, Unreal, Windows natif (l'outil a tourné sous Linux dans WSL ; Godot sous Windows).
- Aucune comparaison avec le terrain réel.
- Fichiers glTF non compacts (sommets non partagés) : 15 à 20 Mo par quartier.

## Prochaines tâches, dans l'ordre proposé

1. **Trottoirs et carrefours** : bordures, passages piétons, sens de circulation et densité de zems exportés comme données.
2. **Relief** : modèle d'élévation libre (Copernicus), sol drapé, bâtiments posés à la bonne altitude.
3. **Deuxième source de bâtiments** : vérifier la couverture de Google Open Buildings au Bénin, fusionner, enregistrer la licence.
4. **Bots en véhicule et hors des routes**, navmesh.
5. **Fichiers plus compacts** et budget mesuré en images par seconde dans Godot.
6. **Interface Tauri** : carte, erreurs en rouge, rejeu d'un bot bloqué, validation des corrections.
7. **Style par quartier** : règles puis classification d'images, sur les photos d'Olympe uniquement.
8. **Test réel d'Unity et d'Unreal**, puis Porto-Novo et Parakou.

## Pièges rencontrés

- Arrondir les coordonnées d'un polygone peut le rendre invalide : `geo.write_features` le recale avec `shapely.set_precision`.
- Dans Godot, un rayon qui tombe pile sur une arête entre deux triangles peut passer au travers : le test tire des rayons décalés avant de conclure à un trou.
- Godot affiche en blanc un glTF coloré par sommets : les couleurs passent par des matériaux.
- Les largeurs de rue par défaut sont trop larges pour Cotonou : 485 bâtiments étaient rognés à tort avant la règle « la rue se rétrécit avant le mur ».
- Une voie couverte qui traverse un bâtiment, ou un auvent posé sur une voie, bloque un personnage si le bâtiment est rendu plein : trouvé par les bots, corrigé (passage ouvert, auvent sur poteaux).
- Godot pour Windows n'écrit pas de façon fiable dans un dossier WSL : le projet de vérification et la carte sont copiés sur un disque Windows avant le test.
- La reprise des étapes dépend de l'empreinte du code : modifier un module commun refait toutes les étapes.
