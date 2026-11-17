# Adaptateur Unity

> **NON TESTÉ : écrit sans Unity sous la main, le 17/11/2026.**

Importe un dossier d'export Ayigba (carte.glb, manifeste.json, CREDITS.md) dans un projet Unity.

## Installation

1. Copier le dossier `Editor` dans le dossier `Assets/` de votre projet.
2. Installer un paquet d'import glTF, par exemple glTFast (Package Manager, « Add package by name » : `com.unity.cloud.gltfast`). Sans lui, Unity ne lit pas le fichier .glb.

## Utilisation

1. Menu **Tools > Ayigba > Importer une carte...**
2. Choisir le dossier d'export.
3. Le script copie `carte.glb` et `CREDITS.md` dans `Assets/Ayigba/<projet>/`, place la carte dans la scène et ajoute un MeshCollider aux couches marquées avec collision dans le manifeste.
4. Si le modèle n'a pas pu être chargé, un avertissement apparaît dans la console : vérifier le paquet d'import.

Le glTF est en main droite et Unity en main gauche : le paquet d'import fait la conversion, ne rien inverser à la main.

## Crédits obligatoires

`CREDITS.md` doit rester livré avec la carte (sources et licences, dont OpenStreetMap). Le script le copie à côté du modèle : ne pas le supprimer.
