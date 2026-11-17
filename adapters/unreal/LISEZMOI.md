# Adaptateur Unreal

> **NON TESTÉ : écrit sans Unreal sous la main, le 17/11/2026.**

Importe un dossier d'export Ayigba (carte.glb, manifeste.json) dans un projet Unreal Engine.

## Lancer le script

1. Activer le greffon **Python Editor Script Plugin** (Édition > Greffons), puis redémarrer l'éditeur.
2. Copier `import_ayigba.py` dans le dossier `Content/Python` du projet (ou ajouter son dossier au chemin Python).
3. Ouvrir la console Python de l'éditeur (Sortie > Cmd, choisir Python) et taper :

```python
import import_ayigba
import_ayigba.importer(r"C:/chemin/vers/export", "/Game/Ayigba")
```

Les maillages des couches avec collision reçoivent la collision « complexe utilisée comme simple ».

Unreal travaille en centimètres et Z vers le haut : l'import glTF fait la conversion, à vérifier à l'écran.

## Crédits obligatoires

`CREDITS.md` (sources et licences, dont OpenStreetMap) doit rester livré avec la carte. Le script ne le copie pas : le conserver à côté du projet.
