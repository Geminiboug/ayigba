# Adaptateur Unity

> **NON TESTÉ DANS UNITY.** Écrit sans Unity sous la main (17/11/2026, complété le 18/11/2026). Le code C# n'a jamais été compilé ni lancé. Seule la conformité du fichier glTF a été vérifiée (voir plus bas).

Importe un dossier d'export ayigba dans un projet Unity, soit d'un bloc (`carte.glb`), soit par zones chargées à la demande (`zones.json` et `zones/*.glb`, comme l'adaptateur Godot).

## Version visée

Unity 2021 LTS ou plus récent avec le paquet **glTFast** (`com.unity.cloud.gltfast`, documentation 6.0). La page officielle des fonctions de glTFast indique « Unity glTFast requires Unity 2020.1 or newer » (https://docs.unity3d.com/Packages/com.unity.cloud.gltfast@6.0/manual/features.html). La compatibilité avec les pipelines Built-in, URP et HDRP est annoncée par la page d'accueil du paquet (https://docs.unity3d.com/Packages/com.unity.cloud.gltfast@6.0/manual/index.html), pas constatée ici.

## Installation

1. Package Manager, « Add package by name » : `com.unity.cloud.gltfast`.
2. Copier `Editor/AyigbaImporter.cs` et `Runtime/AyigbaCarte.cs` dans `Assets/` (par exemple `Assets/Ayigba/Editor` et `Assets/Ayigba/Runtime`).

## Utilisation

- **Carte entière** : menu *Tools > Ayigba > Importer une carte...*, choisir `projects/<projet>/out/neutre`. Copie `carte.glb` et `CREDITS.md` dans `Assets/Ayigba/<projet>/`, place la carte dans la scène, ajoute un `MeshCollider` aux couches `collision: true` du manifeste.
- **Zones à la demande** : menu *Tools > Ayigba > Importer les zones...*. Copie `zones.json`, `zones/` et `CREDITS.md` dans `StreamingAssets/ayigba/<projet>` et crée un objet `AyigbaCarte`. Renseigner `cible` (joueur ou caméra). Les zones à moins de `rayonChargement` (600 m) sont chargées, libérées au-delà de `rayonChargement + margeLiberation`. Collisions : `MeshCollider` sur les couches `collision: true`. Détail : les couches `pres` ne s'affichent que sous `distance_detail_m`, les couches `loin` au-delà (approximation par la distance au centre de la boîte englobante, pas un vrai `LODGroup`).

## Repère et échelle

- Fichiers : mètres, Y vers le haut, X = est, Z = sud (`manifeste.json`, `repere.gltf`, et `extras.unite` du glTF).
- glTF est en main droite, Unity en main gauche : glTFast fait la conversion. **Le sens exact (quel axe est inversé) n'a pas été vérifié.** L'option `inverserX` de `AyigbaCarte` (vrai par défaut) est une hypothèse : si la cible n'est pas au bon endroit par rapport aux zones chargées, la basculer. Ne rien inverser à la main sur la carte.

## Ce que le fichier contient (vérifié sans Unity)

- Aucune texture, aucune couleur de sommet : une couleur = un matériau PBR (`baseColorFactor`, métal 0, rugosité 0,9). Rien à régler côté shader de couleurs de sommets ; glTFast crée ses matériaux par défaut du pipeline actif (non vérifié dans Unity).
- Attributs : POSITION et NORMAL seulement, pas de tangentes ni de UV ; indices **32 bits** (`UNSIGNED_INT`). Des primitives dépassent 65 535 sommets (jusqu'à 147 021 dans la carte entière d'Ouidah) : le moteur doit donc accepter des maillages 32 bits. Unity le permet (`IndexFormat.UInt32`) ; non vérifié ici que glTFast le choisisse seul. Les fichiers de zones sont petits (zones de 250 m).
- Aucune extension requise (`extensionsUsed` absent) : ni Draco, ni meshopt, ni `KHR_materials_*`. Mode triangles uniquement (pas de strips ni de fans, que glTFast ne gère pas d'après sa page des fonctions).
- Un nœud et un maillage par couche (5 à 8 nœuds dans la carte entière), jusqu'à 22 primitives (sous-maillages) par maillage (limite de 32 couleurs par couche). Noms de couches sans suffixe réservé.

## Non testé

Compilation du C#, import réel dans Unity, aspect des matériaux sous URP/HDRP, performance du chargement de zones, orientation et sens des triangles après conversion, nom des objets créés par glTFast (le script retrouve la couche par le nom du `GameObject` ; sinon avertissement), collisions.

## Crédits obligatoires

`CREDITS.md` (sources et licences, dont OpenStreetMap) doit rester livré avec la carte.
