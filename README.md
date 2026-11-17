# ayigba

Générateur automatique de cartes 3D fidèles à de vrais lieux, pour les moteurs de jeu.
Priorité au Bénin : Cotonou d'abord, puis Ouidah, Porto-Novo et Parakou.

> « Ayigba » : la terre, le sol.

![Cadjèhoun et l'aéroport de Cotonou, générés par ayigba et affichés dans Godot](docs/images/cadjehoun_vue_ensemble.png)

*Cadjèhoun et l'aéroport de Cotonou, générés en une commande et ouverts dans Godot 4.7. Données : © les contributeurs d'OpenStreetMap (ODbL).*

## Principe

La cohérence passe avant la fidélité à 100 %. Une carte sans trou, sans mur invisible et sans zone mal formée vaut mieux qu'une copie exacte mais cassée. Là où les données manquent, l'outil génère lui-même et marque ce qui est généré.

L'outil est indépendant de tout jeu : il ne contient ni missions, ni météo, ni scénario. Il produit une carte et ses données, c'est tout.

## État actuel (version 0.1, 17/11/2026)

Ce qui marche, vérifié sur le quartier de Cadjèhoun (7,3 km², 4 272 bâtiments, 119 km de routes) :

- une seule commande, du nom du projet jusqu'aux fichiers exportés ;
- collecte OpenStreetMap avec cache : après le premier téléchargement, tout fonctionne hors ligne ;
- nettoyage : routes recollées, carrefours manquants créés, doublons et chevauchements retirés, bâtiments posés sur les routes corrigés, mer déduite du trait de côte ;
- génération 3D : sol en partition exacte (terre, chaussées revêtues ou non, eau), bâtiments en volumes, berges ;
- contrôles automatiques et rapport de qualité ;
- export neutre : glTF, GeoJSON, manifeste et fichier de crédits ;
- même entrée et même graine donnent exactement le même fichier (empreinte identique) ;
- la carte s'ouvre dans Godot 4.7.2 sans erreur, et 32 487 rayons tirés vers le sol n'y trouvent aucun trou.

Ce qui n'est pas fait ou pas vérifié :

- relief (le terrain est plat), toits en pente, trottoirs, végétation, décors, ponts (rendus comme des remblais) ;
- génération de secours des zones vides (l'étape existe mais ne fait rien) ;
- niveaux de détail et découpage en zones ;
- bots qui marchent ou roulent dans un moteur, navmesh : le contrôle actuel est un marcheur sur grille, plus le test de rayons dans Godot ;
- sources autres qu'OpenStreetMap (empreintes de bâtiments, relief, images) ;
- adaptateurs Unity et Unreal, interface graphique, IA de style ;
- aucune comparaison avec le terrain réel n'a été faite ;
- Windows natif non testé : l'outil a tourné sous Linux (WSL).

Le plan complet et l'avancement sont dans [docs/CHANTIER.md](docs/CHANTIER.md). Le fonctionnement interne est dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Utilisation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Générer le quartier d'essai (télécharge les données la première fois)
.venv/bin/ayigba generer projects/cotonou-cadjehoun

# Ensuite, sans réseau
.venv/bin/ayigba generer projects/cotonou-cadjehoun --hors-ligne

# Options : --jusqua <étape>, --etape <étape>, --forcer
.venv/bin/ayigba etapes
```

Résultat dans `projects/<projet>/out/neutre/` : `carte.glb`, `routes.geojson`, `batiments.geojson`, `points_interet.geojson`, `manifeste.json`, `CREDITS.md`. Le rapport de qualité est dans `reports/qualite.md` et le journal des décisions dans `logs/decisions.jsonl`.

Un projet est un dossier avec un fichier `config.toml` : la zone (rectangle en degrés), la graine, le style. Voir [projects/cotonou-cadjehoun/config.toml](projects/cotonou-cadjehoun/config.toml).

Tests : `.venv/bin/python -m pytest`.

Vérification dans Godot (projet de test, sans aucun jeu) :

```bash
godot --headless --path verif/godot --script res://verifier_carte.gd -- carte=/chemin/vers/carte.glb
```

## Sources et licences des données

Les données ne sont pas dans ce dépôt. Chaque carte générée est livrée avec un fichier `CREDITS.md` qui liste les sources et leurs mentions obligatoires. OpenStreetMap est sous licence ODbL : la mention « © les contributeurs d'OpenStreetMap » doit apparaître partout où la carte est montrée. Ce n'est pas un avis juridique.

## Droits sur le code

© 2026 Olympe Mahougnon HOUNKPEVI. Aucune licence d'utilisation n'est accordée pour l'instant : le code est visible, tous droits réservés, jusqu'au choix d'une licence.
