# Chantier ayigba : plan et avancement

Écrit pour : Olympe, et tout agent qui reprend le travail. Mis à jour le 17/11/2026 (version 0.5).

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
| 2 | Collecte et nettoyage | **fait : OpenStreetMap, relief Copernicus (plusieurs tuiles), Google Open Buildings 2.5D** | reste : Microsoft Building Footprints, images de rue |
| 3 | Génération de base | **fait, version simple** | relief (Copernicus 30 m), sol conforme drapé sur le relief, routes, trottoirs à plat, bâtiments posés sur le relief, auvents, eau à son niveau propre, décors ; densité de zems et sens de circulation exportés comme données ; reste : relief plus fin que 30 m, toits en pente, bordures de trottoir surélevées, carrefours dessinés, passages piétons peints, façades |
| 4 | Tests par bots, correction, rapport | **fait** | contrôles de géométrie, accessibilité exacte, bots dans Godot sur toutes les routes au gabarit piéton et au gabarit voiture (1,8 m de large), comparaison avant/après et retour en arrière ; reste : navmesh, bots hors des routes, vrai véhicule à roues |
| 5 | Génération de secours | **fait, première version** | routes isolées reliées ou retirées, îlots vides remplis, cours fermées comblées ; tout est marqué `genere` |
| 6 | Export Godot et vérification dans un vrai Godot | **fait** | adaptateur `adapters/godot/ayigba_carte.gd` (zones à la demande, collisions, niveaux de détail), vérifié par les bots |
| 7 | Optimisation | **fait, première version** | zones de 250 m, deux niveaux de détail pour les bâtiments, budget par zone, sommets partagés dans les fichiers ; reste : simplification du sol, mesure réelle des images par seconde |
| 8 | Interface Tauri | à faire | |
| 9 | IA de style | à faire | commencer par des règles et une classification |
| 10 | Adaptateurs Unity et Unreal | **écrits, NON TESTÉS** | `adapters/unity`, `adapters/unreal` : aucun des deux moteurs n'était disponible |
| 11 | Autres villes | **Ouidah fait** | créée par son seul nom, sans changer le code ; reste : Porto-Novo, Parakou |

## Résultats mesurés (17/11/2026, version 0.5)

| Mesure | Cotonou, Cadjèhoun | Ouidah |
|---|---|---|
| Zone | 7,3 km² | 8,9 km² |
| Bâtiments | 7 504 : 4 274 OSM, 3 108 détectés par IA, 122 générés | 14 744 : 7 845 OSM, 6 816 détectés par IA, 83 générés |
| Hauteurs des bâtiments | 6 919 mesurées par IA, 109 d'OSM, 476 estimées | 12 966 mesurées par IA, 77 d'OSM, 1 701 estimées |
| Altitudes du sol nu | de 0.0 à 8.41 m | de 2.67 à 24.04 m |
| Pente maximale du sol | 5.1 degrés | 3.8 degrés |
| Triangles (carte entière) | 479 979 | 685 189 |
| Triangles au plus dans une zone, de près (budget 15 000) | 12 496 | 14 849 |
| Erreurs et avertissements du rapport | 0 et 0 | 0 et 0 |
| Surface libre accessible à pied | 100 % | 100 % |
| Godot : triangles retrouvés après import ; trous du sol | tous ; 0 sur 32 487 rayons | tous ; 0 sur 39 600 rayons |
| Bots piétons : routes sans défaut | 623 sur 623 (118,5 km) | 602 sur 602 (129,3 km) |
| Bots gabarit voiture : routes sans défaut | 610 sur 610 (116,0 km) | 574 sur 574 (126,4 km) |
| Bots : sorties de chaussée | 248 sur 248 | non lancé |
| Blocages et chutes de tous les bots | 0 et 0 | 0 et 0 |

Même entrée et même graine donnent les mêmes fichiers (test automatique). Aucune comparaison avec le terrain réel.

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

- Relief : modèle de SURFACE de 30 m (Copernicus GLO-30). Depuis la version 0.5, la hauteur moyenne des toits mesurée par Google Open Buildings 2.5D en est retirée (« sol nu »), avec trois garde-fous : correction de 8 m au plus, jamais plus de 4 m sous le terrain bas des environs, jamais une terre sous 0,5 m d'altitude abaissée sous ce niveau. Les arbres ne sont pas retirés (l'enveloppe basse d'un pixel atténue les pics). Aucune comparaison avec un relevé de terrain.
- Bâtiments détectés par IA (Google Open Buildings 2.5D, 2023) : ce sont des détections, pas des relevés. Faux positifs possibles, bâtiments voisins parfois fusionnés, formes simplifiées en rectangles. Ils sont marqués `source = google_25d`.
- Les hauteurs « google_25d » sont la médiane des pixels de 2 m sous l'emprise : un bâtiment à étages en retrait est rendu comme un seul bloc.
- Les rives : le sol redescend vers chaque plan d'eau sur 40 m, jusqu'à 15 cm au-dessus de l'eau. C'est une règle, pas une mesure.
- Toits en pente, façades, carrefours dessinés, passages piétons peints, ponts (rendus comme des remblais), plafond des passages couverts (ouverts à ciel ouvert).
- Sources autres qu'OpenStreetMap. Presque toutes les hauteurs de bâtiments sont estimées par une règle simple.
- Les décors n'ont pas de collision. Leur placement suit des règles simples, pas une observation du terrain.
- Navmesh, bots qui quittent les routes, vrai véhicule à roues (le bot « voiture » est une capsule de 1,8 m de large).
- Les bots marchent à vitesse constante sur le sol : ils ne testent pas la pente maximale franchissable par un vrai véhicule (la pente maximale du sol est mesurée par le rapport : 6,5 à 6,8 degrés).
- La densité de zems exportée est une règle (classe de route, proximité d'un marché, d'une gare, d'une école...), pas une mesure.
- Interface graphique, IA de style, édition manuelle.
- Unity, Unreal, Windows natif (l'outil a tourné sous Linux dans WSL ; Godot sous Windows).
- Aucune comparaison avec le terrain réel.

## Prochaines tâches, dans l'ordre proposé

1. **Carrefours dessinés et passages piétons peints.**
2. **Contrôler les détections** : comparer sur le terrain ou sur images un échantillon des bâtiments détectés par l'IA (faux positifs, bâtiments fusionnés).
3. **Arbres** : les retirer aussi du relief (pas de donnée libre identifiée pour l'instant).
4. **Bots hors des routes**, navmesh, vrai véhicule à roues.
5. **Budget mesuré en images par seconde** dans Godot, sur une machine modeste.
6. **Interface Tauri** : carte, erreurs en rouge, rejeu d'un bot bloqué, validation des corrections.
7. **Style par quartier** : règles puis classification d'images, sur les photos d'Olympe uniquement.
8. **Test réel d'Unity et d'Unreal**, puis Porto-Novo et Parakou.

## Pièges rencontrés

- Arrondir les coordonnées d'un polygone peut le rendre invalide : `geo.write_features` le recale avec `shapely.set_precision`.
- Dans Godot, un rayon qui tombe pile sur une arête entre deux triangles peut passer au travers : le test tire des rayons décalés avant de conclure à un trou.
- Godot affiche en blanc un glTF coloré par sommets : les couleurs passent par des matériaux.
- Les largeurs de rue par défaut sont trop larges pour Cotonou : 485 bâtiments étaient rognés à tort avant la règle « la rue se rétrécit avant le mur ».
- Bordure de trottoir en pente obtenue en triangulant l'anneau entre deux contours : 1 757 faces à plus de 45 degrés, bots piétons bloqués. Retirée ; les trottoirs sont à plat tant qu'une bordure garantie franchissable n'existe pas.
- Un bot plus large que la tolérance d'arrivée ne peut pas « toucher » le dernier point d'une voie qui finit contre un mur : la tolérance suit le rayon du bot.
- Une correction du relief sans garde-fou a creusé le sol jusqu'à 18 m sous la mer (un grand toit mal mesuré). Le garde-fou régional a d'abord été trop strict (aucune correction dans un quartier dense uniforme) : les tests synthétiques l'ont montré avant toute régénération.
- Le téléchargement des manifestes Open Buildings a échoué une fois par refus de certificat (filtrage réseau local). La vérification des certificats n'a pas été désactivée : un nouvel essai a réussi.
- **Godot perd en silence les surfaces au-delà de 256 par maillage.** Les décors avaient 5 700 surfaces (une teinte légèrement différente par pièce) : 63 700 triangles manquaient dans Godot et rien ne l'indiquait. Corrigé (32 couleurs au plus par couche) et le vérificateur compare désormais le nombre de triangles du manifeste à celui de Godot.
- Un sol drapé sur un modèle de surface fabrique des bosses sous les quartiers denses : à regarder sur la carte d'altitude (`tools/apercu_relief.py`), pas sur une capture 3D exagérée (l'exagération verticale déforme aussi les bâtiments).
- Quand plusieurs plans d'eau sont proches, le niveau de rive ne doit pas dépendre du « plus proche » (il saute d'un plan d'eau à l'autre) : les corrections de tous les plans d'eau sont additionnées puis ramenées à un poids de 1.
- Une voie couverte qui traverse un bâtiment, ou un auvent posé sur une voie, bloque un personnage si le bâtiment est rendu plein : trouvé par les bots, corrigé (passage ouvert, auvent sur poteaux).
- Godot pour Windows n'écrit pas de façon fiable dans un dossier WSL : le projet de vérification et la carte sont copiés sur un disque Windows avant le test.
- La reprise des étapes dépend de l'empreinte du code : modifier un module commun refait toutes les étapes.
