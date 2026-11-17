# Architecture d'ayigba

Écrit pour : une personne ou un agent qui va modifier le code.

## Vue d'ensemble

```
collecte -> nettoyage -> secours -> generation -> tests -> optimisation -> export
```

Chaque étape est un module de `src/ayigba/stages/` qui expose `run(ctx) -> dict`. Elle lit les fichiers de l'étape précédente et écrit les siens : on peut donc reprendre après un plantage, et inspecter chaque fichier intermédiaire.

| Étape | Module | Lit | Écrit |
|---|---|---|---|
| collecte | `collect.py` | API Overpass | `cache/osm_overpass.json`, `data/sources.json` |
| nettoyage | `clean.py` | le cache | `work/nettoyage/*.geojson` |
| secours | `fallback.py` | nettoyage | `work/secours/roads.geojson`, `buildings.geojson` (réel + généré) |
| generation | `generate.py` | nettoyage, secours | `work/generation/*.npz`, `sol.geojson`, `buildings.geojson`, `decors.geojson`, `scene.json` |
| tests | `validate.py` | secours, generation | `reports/qualite.json`, `reports/qualite.md` |
| optimisation | `optimize.py` | generation | `work/optimisation/zones.json`, `zones/*.npz` |
| export | `export.py` | tout | `out/neutre/*` |

Modules communs : `access.py` (accessibilité à pied sur les formes exactes), `decor.py` et `props.py` (placement et formes des décors), `mesh.py` et `gltf.py` (maillages et écriture glTF), `geocode.py` (projet à partir d'un nom), `history.py` (instantanés et comparaison).

Le secours passe avant la génération des maillages : les éléments générés suivent ainsi exactement le même chemin (maillages, contrôles, export) que les données réelles.

Les bots qui marchent dans un vrai moteur ne sont pas une étape du pipeline : ils sont dans `verif/godot/` et se lancent avec Godot.

## Dossier d'un projet

```
projects/<ville-quartier>/
  config.toml   seul fichier suivi par Git
  data/         registre des sources (sources.json)
  cache/        données téléchargées : sert au mode hors ligne
  work/         fichiers intermédiaires, un sous-dossier par étape
  out/          cartes exportées
  reports/      rapports de qualité
  logs/         journal des décisions (decisions.jsonl)
```

## Règles du code

1. **Reprise.** `pipeline.py` écrit `work/<étape>/_fait.json` avec une empreinte faite de la configuration, de l'étape précédente et du code. Si l'une change, l'étape et les suivantes sont refaites. `--forcer` refait tout.
2. **Reproductibilité.** Aucun tirage aléatoire global, aucune date dans les sorties. Un tirage passe par `mesh.rng_for(graine, identifiant)`. Les éléments sont traités dans l'ordre de leurs identifiants. Un test compare deux sorties octet pour octet.
3. **Journal.** Toute correction, suppression, génération ou anomalie passe par `ctx.journal.record(action, objet, raison)`. Les actions : `corrige`, `supprime`, `genere`, `signale`, `info`.
4. **Sources.** Toute donnée extérieure s'enregistre avec `sources.register_source`. Le fichier `CREDITS.md` en découle. Un élément produit par l'outil porte `source = "genere"`.
5. **Indépendance.** Aucune logique de jeu dans `src/ayigba/`. Un adaptateur de moteur ne fait que convertir le format neutre.
6. **Noms.** Aucun nom de couche ou d'objet ne finit par `_col`, `-col`, `_colonly`, `_convcol` : Godot les interprète à l'import (`gltf.check_name`).
7. **Honnêteté.** Chaque rapport liste ce qui n'a pas été vérifié.

## Repères

- **Repère local** (`geo.LocalFrame`) : mètres, origine au centre de la zone, x vers l'est, y vers le nord, z vers le haut. Projection UTM choisie d'après la longitude (zone 31N pour le Bénin). Tous les fichiers de `work/` sont dans ce repère.
- **glTF** : X = est, Y = haut, Z = sud. C'est une rotation du repère local, le sens des triangles est conservé.
- **Export GeoJSON** : WGS84 (longitude, latitude), pour le GPS et la mini-carte.

## Choix techniques

- **Python** (décision d'Olympe du 17/11/2026) : bibliothèques géographiques mûres et développement rapide. Les points lents pourront passer en Rust plus tard. Dépendances : numpy, shapely, pyproj, mapbox-earcut. Pas de GDAL ni de geopandas pour l'instant.
- **Sol en partition exacte.** Le sol est découpé en parties qui ne se chevauchent pas (eau, revêtu, non revêtu, terre) et dont la réunion vaut la zone. Pas de surfaces superposées, donc pas de scintillement, et un trou se détecte par un calcul de surface.
- **Couleurs par matériaux.** Un matériau glTF par couleur, et non des couleurs de sommets : Godot 4.7 affiche les couleurs de sommets en blanc sans réglage (constaté le 17/11/2026).
- **La rue se rétrécit avant le mur.** Quand OpenStreetMap ne donne pas la largeur d'une rue et que des bâtiments débordent sur la largeur supposée, on réduit la chaussée jusqu'à un minimum par classe. On ne rogne un bâtiment qu'ensuite.

## Limites connues des règles de nettoyage

- Un pont est rendu comme un remblai : l'eau est coupée sous la route.
- Un sentier qui traverse un bâtiment est coupé ; un passage couvert réel est donc perdu.
- Un bâtiment à cheval sur la limite de la zone est retiré.
- Les revêtements non renseignés sont supposés : revêtu pour les grands axes, non revêtu pour le reste (`revetement_suppose`).
- Les noms de commerces d'OpenStreetMap sont gardés tels quels dans les points d'intérêt. Un jeu qui ne veut pas de marques réelles doit les remplacer lui-même.
