# Chantier ayigba : plan et avancement

Écrit pour : Olympe, et tout agent qui reprend le travail. Mis à jour le 17/11/2026 (version 0.6).

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
| 3 | Génération de base | **fait, version simple** | relief (Copernicus 30 m), sol conforme drapé sur le relief, routes, trottoirs à plat, bâtiments posés sur le relief, auvents, eau à son niveau propre, décors ; densité de zems et sens de circulation exportés comme données ; toits à deux pentes pour une partie des petits bâtiments rectangulaires (version 0.6) ; reste : relief plus fin que 30 m, bordures de trottoir surélevées, carrefours dessinés, passages piétons peints, façades |
| 4 | Tests par bots, correction, rapport | **fait** | contrôles de géométrie, accessibilité exacte, bots dans Godot sur toutes les routes au gabarit piéton et au gabarit voiture (1,8 m de large), comparaison avant/après et retour en arrière ; reste : navmesh, bots hors des routes, vrai véhicule à roues |
| 5 | Génération de secours | **fait, première version** | routes isolées reliées ou retirées, îlots vides remplis, cours fermées comblées ; tout est marqué `genere` |
| 6 | Export Godot et vérification dans un vrai Godot | **fait** | adaptateur `adapters/godot/ayigba_carte.gd` (zones à la demande, collisions, niveaux de détail), vérifié par les bots |
| 7 | Optimisation | **fait, première version** | zones de 250 m, deux niveaux de détail pour les bâtiments, budget par zone, sommets partagés dans les fichiers ; reste : simplification du sol, mesure réelle des images par seconde |
| 8 | Interface Tauri | à faire | |
| 9 | IA de style | à faire | commencer par des règles et une classification |
| 10 | Adaptateurs Unity et Unreal | **préparés, fichiers validés, NON TESTÉS dans les moteurs** | 18/11/2026. Validé sans moteur : validateur officiel Khronos (gltf-validator 2.0.0-dev.3.10) sur carte.glb de Cadjèhoun et d'Ouidah et sur leurs 126 et 144 zones : 0 erreur, 0 avertissement, 0 info, 0 conseil ; `tests/test_export_conformite.py` (indices 32 bits, valeurs finies, min/max, un maillage par couche, manifeste cohérent). Préparé : `adapters/unity` (import d'un bloc, `Runtime/AyigbaCarte.cs` zones à la demande), `adapters/unreal` (`importer`, `importer_zones`, étapes manuelles). Reste NON testé : compilation du C#, tout import réel dans Unity et Unreal, conversion de repère et d'échelle (sens de l'axe X sous Unity, centimètres sous Unreal), matériaux, collisions, chargement à la demande sous Unreal (non écrit). Aucune texture ni extension glTF requise ; primitives jusqu'à 147 021 sommets (indices 32 bits) |
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
- **Contrôle des détections (`ayigba controler-detections`, `src/ayigba/controle.py`, ajouté le 17/11/2026).** L'outil mesure des INDICES DE SUSPICION, pas la vérité terrain : aucune vérité terrain n'est disponible, le score (somme de poids dans `controle.POIDS`) est un outil de tri et jamais une probabilité d'erreur. Les seuils de surface, d'allongement, de hauteur et de densité sont ceux demandés ; ceux de rectangularité (0,5) et de présence moyenne (0,55) et tous les poids sont des choix de l'auteur, réglés sur la distribution observée pour que l'indice discrimine, pas sur des erreurs réelles. Limites : les indices viennent des mêmes données 2.5D que la détection (un bâtiment « sûr » est cohérent avec ses propres données, pas confirmé par une source indépendante) ; l'étape secours retire déjà des détections ce qui touche l'eau et les chaussées, donc `proche_eau` et `zone_tres_dense` ne se déclenchent presque jamais (0 sur les deux projets) ; « proche » veut dire à 1 m ou moins. Résultats du 17/11/2026 : Cadjèhoun, 3 108 détections, 1 389 sans indice, 165 de score 4 ou plus ; Ouidah, 6 816 détections, 3 773 sans indice, 317 de score 4 ou plus. Les planches (échantillon stratifié, graine fixe) montrent que les suspects sont surtout de très petites taches coincées entre des bâtiments, de faible hauteur ; elles ne prouvent rien sur la précision réelle. Exclusion : `--exclure-score X` écrit une liste d'identifiants dans `[batiments25d] exclure` de `config.toml` seulement à la demande ; l'étape secours les retire à la génération suivante et journalise le nombre exclu (`logs/decisions.jsonl`). Les identifiants `g25d/x_y_k` peuvent changer si la détection change : un identifiant sans correspondance est ignoré (compté dans le journal).
- **Filtre de fragments douteux (`detection.filtrer_fragments`, appelé par `stages/fallback.py`, ajouté le 18/11/2026).** Par défaut, une détection `google_25d` est retirée si sa surface est < 20 m2 ET (sa hauteur médiane est < 2,4 m, OU elle est à 3 m ou moins d'un bâtiment plus grand, OSM ou détecté). Une détection de 20 m2 ou plus n'est jamais touchée ; une hauteur inconnue ne déclenche pas le critère de hauteur ; une petite construction isolée et haute (kiosque, cabine) reste. Options `[batiments25d]` de `config.toml` : `fragments_actif`, `fragment_surface_m2`, `fragment_hauteur_m`, `fragment_voisin_m`. Journal : une ligne `supprime` dans `logs/decisions.jsonl` (nombre et seuils) à chaque génération, résumé de l'étape : `fragments_retires`. Tests : `tests/test_fragments.py`. Effet mesuré le 18/11/2026 (avant -> après) : Cadjèhoun 262 fragments retirés, 3 108 -> 2 846 détections, 7 504 -> 7 239 bâtiments au total (262 attendus : l'écart de 3 en plus n'est pas expliqué, probablement un autre changement du dépôt) ; Ouidah 690 retirés, 6 816 -> 6 126 détections, 14 744 -> 14 054 bâtiments. Détections de score >= 4 au contrôle : Cadjèhoun 165 -> 66, Ouidah 317 -> 99. LIMITES HONNÊTES : (1) il n'y a pas de vérité terrain, rien ne prouve que les fragments retirés soient des résidus plutôt que de vrais petits bâtiments (appentis, toilettes, annexes) ; (2) la baisse du score >= 4 est en partie circulaire, car le filtre et le score s'appuient sur les mêmes indices (surface, hauteur) : les 262 et 690 retirés étaient tous des détections à indices, aucune détection sans indice n'a bougé ; (3) la planche du contrôle montre ce qui RESTE, pas ce qui a été retiré, et il reste des suspects de 14 à 36 m2 et 2 à 3 m de haut (ceux de 20 m2 ou plus ou de hauteur >= 2,4 m échappent au filtre) ; (4) les seuils (20 m2, 2,4 m, 3 m) sont prudents mais choisis sans mesure, pas étalonnés sur le terrain ; (5) un voisin « plus grand » peut lui-même être un fragment retiré dans le même passage.
- Les hauteurs « google_25d » sont la médiane des pixels de 2 m sous l'emprise : un bâtiment à étages en retrait est rendu comme un seul bloc.
- Les rives : le sol redescend vers chaque plan d'eau sur 40 m, jusqu'à 15 cm au-dessus de l'eau. C'est une règle, pas une mesure.
- Toits : seuls les petits bâtiments (25 à 500 m2, 9 m de haut au plus) presque rectangulaires (au moins 90 % de leur rectangle englobant), plus longs que larges, sans cour intérieure, reçoivent un toit à deux pentes (14 degrés, faîte de 1,8 m au plus), pour 60 % d'entre eux tirés selon la graine. C'est un CHOIX DE STYLE : les données ne disent pas la forme des toits, et la propriété `toit = deux_pentes` est inscrite dans buildings.geojson avec une ligne `genere` au journal. Les autres toits restent plats (toits à quatre pentes, en L, terrasses : non faits). De loin, les boîtes restent plates. Réglage : `[toits] actif`, `part_deux_pentes`. Résultat : 1 936 toits à Cadjèhoun, 3 821 à Ouidah.
- Carrefours (`src/ayigba/carrefours.py`, version 0.6) : un carrefour est un point où au moins trois bras de rues REVÊTUES se rejoignent (ponts, tunnels, chemins piétons, rues non revêtues et ronds-points exclus). Les coins rentrants sont arrondis (congé de 4 m, seulement près d'un carrefour, petites surfaces, jamais un îlot entouré de chaussée ni l'espace entre deux chaussées parallèles). Des passages piétons en zèbre sont peints à l'entrée de chaque bras des grandes rues (trunk, primary, secondary, tertiary, au moins 5 m de large). C'est une RÈGLE DE STYLE générale : la présence réelle des passages piétons n'est pas dans les données. La peinture est une partie du sol à part (`marquage`), à fleur de chaussée, donc sans effet sur les collisions. Résultat : 124 carrefours et 627 bandes à Cadjèhoun, 19 carrefours et 231 bandes à Ouidah (presque toutes ses rues sont non revêtues). Limites : quand plusieurs carrefours sont très proches, certains zèbres se chevauchent ou sont orientés en biais ; pas de lignes d'arrêt, de flèches ni de marquage central ; les ronds-points ne sont pas traités. Réglage : `[carrefours] actif`, `arrondi_m`, `passages`.
- Sources d'empreintes interchangeables (`src/ayigba/empreintes.py`, version 0.7) : toute source de bâtiments suit la même interface (`SourceEmpreintes` : identifiant, licence, attribution, `collecter`) et s'ajoute en écrivant UN fichier ; une source sans licence complète est refusée. Elles s'activent dans config.toml : `[empreintes] sources = ["microsoft"]` (l'ordre donne la priorité). Une seule fusion pour toutes : doublons (plus de 30 % de recouvrement), bâtiments sur chaussée ou dans l'eau, surfaces hors de 8 à 5 000 m2 et géométries invalides sont écartés, et un candidat qui chevauche un peu est DÉCOUPÉ (le contrôle de qualité refuse toute superposition). Chaque rejet est compté et journalisé. `ayigba sources` les liste. Source livrée : Microsoft Global ML Building Footprints (licence CDLA Permissive 2.0, et non ODbL ; téléchargement de la tuile concernée, 22 à 77 Mo, option `[empreintes.microsoft] telecharger = true` pour le permettre hors mode en ligne). Mesuré le 18/11/2026 : à Ouidah 12 585 candidats, 9 610 doublons de bâtiments déjà connus (76 %), 320 sur chaussée ou eau, 2 631 ajoutés ; à Cadjèhoun 8 226 candidats, 5 247 doublons, 2 312 ajoutés. Microsoft ne fournit AUCUNE hauteur au Bénin (toutes à -1) : les bâtiments ajoutés prennent une hauteur estimée. Ce sont des empreintes tirées d'images satellite par IA, comme celles de Google : non vérifiées sur le terrain, et aucune comparaison avec la vérité terrain n'a été faite. Désactivé par défaut. Overture Maps n'est pas intégré (il faudrait `duckdb`).
- Étape secours, poches fermées : la boucle de comblement analyse maintenant les géométries arrondies au millimètre, comme le fichier écrit (un interstice de moins de 1 mm entre deux bâtiments créait une poche vue seulement par l'étape de contrôle), et recommence jusqu'à 8 fois tant qu'elle progresse.
- Façades, carrefours dessinés, passages piétons peints, ponts (rendus comme des remblais), plafond des passages couverts (ouverts à ciel ouvert).
- Sources autres qu'OpenStreetMap. Presque toutes les hauteurs de bâtiments sont estimées par une règle simple.
- Les décors n'ont pas de collision. Leur placement suit des règles simples, pas une observation du terrain.
- Navmesh, bots qui quittent les routes, vrai véhicule à roues (le bot « voiture » est une capsule de 1,8 m de large).
- Les bots marchent à vitesse constante sur le sol : ils ne testent pas la pente maximale franchissable par un vrai véhicule (la pente maximale du sol est mesurée par le rapport : 6,5 à 6,8 degrés).
- La densité de zems exportée est une règle (classe de route, proximité d'un marché, d'une gare, d'une école...), pas une mesure.
- Interface graphique, IA de style, édition manuelle.
- Unity, Unreal (fichiers validés par Khronos, adaptateurs jamais lancés dans les moteurs ; voir l'étape 10), Windows natif (l'outil a tourné sous Linux dans WSL ; Godot sous Windows).
- Aucune comparaison avec le terrain réel.

## Prochaines tâches, dans l'ordre proposé

1. **Carrefours dessinés et passages piétons peints.**
2. **Contrôler les détections** : l'outil de tri existe (`ayigba controler-detections`, planche exemple dans `docs/images/`) ; reste à comparer sur le terrain ou sur images satellite les 20 plus suspects et un échantillon au hasard, pour savoir si le score trie bien, et d'en tirer un taux d'erreur mesuré.
3. **Arbres** : les retirer aussi du relief (pas de donnée libre identifiée pour l'instant).
4. **Bots hors des routes**, navmesh, vrai véhicule à roues.
5. **Budget mesuré en images par seconde** dans Godot, sur une machine modeste.
6. **Interface Tauri** : carte, erreurs en rouge, rejeu d'un bot bloqué, validation des corrections.
7. **Style par quartier** : règles puis classification d'images, sur les photos d'Olympe uniquement.
8. **Test réel d'Unity et d'Unreal**, puis Porto-Novo et Parakou.

## Test hors du Bénin (18/11/2026)

Deux zones de 1,4 km², créées par `ayigba creer` (rayon 0,6 km) et générées de bout en bout, en ligne :

| | Croix-Rousse, Lyon (France) | Cusco (Pérou) |
|---|---|---|
| Ce que la zone teste | hors couverture Open Buildings 2.5D, colline, hémisphère nord et est | latitude et longitude négatives, altitude 3 356 à 3 614 m |
| Bâtiments | 3 590 (dont 358 générés) | 1 628 (dont 58 générés) |
| Hauteurs | 2 034 estimées, 0 mesurée (pas de 2.5D : le message « zone non couverte » est journalisé, rien ne plante) | 1 572 estimées ; la couverture 2.5D n'est que de 0,33 %, 36 pixels de relief corrigés |
| Pente maximale du sol | 30,7 degrés (avertissement : donnée peut-être bruitée) | 32,1 degrés (idem) |
| Erreurs de qualité | 0 | 0 |
| Triangles | 332 311 | 96 714 |

Deux défauts trouvés par ce test, corrigés : (1) `carrefours.arrondir` recalculait un tampon de tout le réseau de rues pour chaque pièce : la génération de Lyon prenait 2 092 s, elle prend 42 s avec un résultat identique ; (2) la boucle de comblement des poches fermées ne voyait pas une poche de 416 m2 à Cusco, parce que le tampon de 2 cm de l'union de quatre bâtiments voisins recouvrait toute la poche (défaut de la géométrie quand des bâtiments se touchent presque) : un second calcul sert de secours. Les deux zones avaient 1 erreur de qualité avant ces corrections.

Ce que ce test NE démontre PAS : les garde-fous du sol nu n'ont pas été éprouvés sur une vraie colline couverte par le 2.5D (Cusco n'a presque pas de couverture, Lyon aucune) ; il faut une zone en pente AVEC couverture, par exemple une ville de montagne d'Amérique latine ou d'Asie du Sud. Aucun contrôle visuel dans Godot, aucun bot lancé sur ces deux zones. La zone Lyon est rendue avec les couleurs de sable et de latérite, les teintes de murs et de toits et les largeurs de rue pensées pour le Bénin : ces constantes régionales sont encore codées en dur dans `stages/generate.py` (`SAND`, `LATERITE`, `WALLS`, `ROOFS`, `_estimate_height`) et `stages/clean.py` (`ROAD_WIDTH`, `PAVED_BY_DEFAULT`) ; elles sont à déplacer dans la configuration, ce qui rejoint le chantier des textures. Autre limite vue à Lyon : 318 cours intérieures ont été comblées par des volumes pleins parce que les données ne montrent aucun passage vers la rue.

## Textures cohérentes et fidèles (demande d'Olympe, 18/11/2026, pas commencé)

Objectif : l'outil sait choisir et appliquer des textures et des matériaux de façon COHÉRENTE entre bâtiments voisins et FIDÈLE à la réalité du lieu, quel que soit le lieu (pas seulement le Bénin). Un « agent de style » cherche des références, en tire un profil de quartier, applique des textures existantes, et en GÉNÈRE par IA là où il en manque, en le disant.

État aujourd'hui : l'export n'a ni texture ni coordonnées de texture ; chaque bâtiment a seulement un matériau de couleur tiré au hasard (graine) parmi des listes codées dans `stages/generate.py` (`WALLS`, `ROOFS`), donc deux voisins peuvent diverger. Les données libres ne disent presque rien du matériau ou de la couleur (OSM : 0 tag `building:colour`, `building:material` ou `roof:shape` sur Cadjèhoun et Ouidah).

Principes retenus :
- Fidélité au niveau du QUARTIER et du type de bâtiment, pas du bâtiment, sauf là où une photo de référence existe. Ne jamais prétendre le contraire.
- Cohérence : un profil de style par quartier (palette, matériaux, usure, types de toit), appliqué avec un lissage spatial (les voisins partagent le style, avec des variations contrôlées), au lieu d'un tirage indépendant par bâtiment.
- Références : (1) photos fournies par l'utilisateur dans un dossier du projet, la voie la plus fidèle et la plus sûre juridiquement ; (2) sources libres : Mapillary (jeton gratuit à créer par l'utilisateur ; photos CC BY-SA : on en tire des statistiques de couleur et de matière, jamais les pixels recopiés), Sentinel-2 pour la couleur du sol et des toits à 10 m ; (3) textures libres CC0 (ambientCG, Poly Haven) avec licence enregistrée.
- Génération par IA seulement pour les matériaux manquants : textures carrelables, produites à partir du profil de style (couleurs, usure, climat), marquées `genere` dans le journal et dans les crédits, avec une planche de contrôle à valider avant l'export. Le fournisseur (API payante ou modèle local) reste à décider avec Olympe : la carte graphique actuelle (RTX 2050) est limitée pour un modèle local.
- Jamais d'images, de tuiles ou de 3D tirées de Google Maps ou Street View (conditions d'utilisation).
- Aucune logique de jeu : l'outil exporte des matériaux et des textures ; l'application dans le moteur se fait par les adaptateurs.

Phases proposées : 1) profil de style par quartier et lissage spatial, avec couleurs seulement (sans clé ni réseau) ; 2) coordonnées de texture et textures CC0 carrelables dans le glTF (budget de poids à mesurer) ; 3) références utilisateur et extraction de palette ; 4) Mapillary ; 5) génération IA des textures manquantes ; 6) mode agent qui enchaîne recherche, profil, génération et contrôle.

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
