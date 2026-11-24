# Contrôles automatiques de GTB (lecture seule)

Mis en place le 24/11/2026 avec la session du jeu. Ces contrôles ne modifient rien dans le dépôt du jeu : ils lisent une copie de travail
(`C:\gtb_local\godot`, mise à jour par `C:\gtb_local\sync.ps1` du jeu). Le jeu se corrige de son côté ; la publication reste à Olympe.

**Règle des fenêtres** : le monde de GTB ne se charge pas en mode sans fenêtre. Une seule fenêtre Godot à la fois pour tous : chaque script
prend le verrou `C:\gtb_local\verrou_fenetre` (dossier créé puis supprimé) et échoue avec « VERROU OCCUPE » s'il est pris.

| Contrôle | Script ayigba (`verif/godot/gtb/`) | Lanceur (`verif/gtb/`, à copier dans `C:\gtb_local`) | Durée | État du 24/11/2026 |
|---|---|---|---|---|
| Objets flottants ou enterrés (sous `Lieux`) | `gtb_flottants.gd` | `ay_gtb_scan.ps1` | 2 min, fenêtre | 0 défaut sur 1 814 objets |
| Passants et joueur dans un mur ou sous le sol | `gtb_pietons.gd` | `ay_gtb_pietons.ps1` | 3 min, fenêtre | 0 centre contre un solide sur 110 observations |
| Toits à quatre pans de l'Ararat, maison par maison | `gtb_toits.gd` | `ay_gtb_toits.ps1` | 2 min, fenêtre | 0 défaut sur 61 toits |
| Chaussée sans sol ou encombrée | `tests/audit_chaussee.gd` du jeu | `ay_gtb_audit.ps1` | 5 min, fenêtre | 0 sans sol, 613 rues sur 1 073 |
| Circulation (banc sans monde) | `tests/banc_circulation.gd` du jeu | `ay_gtb_circ.ps1` puis `verif/gtb_seuils_circulation.py` | 2 min, sans fenêtre | seuils respectés |
| Sens des feux | `tests/test_feux_sens.gd` du jeu | `ay_gtb_feux.ps1` | 2 min, fenêtre | OK : 150 boîtiers, 29 carrefours |

Modèles trop lourds et textures magenta : déjà contrôlés par le jeu (`tools/controle_assets.gd`, `controle_textures.gd`, `scan_textures_map.gd`).

## Seuils de non-régression de la circulation (démo, 300 s, fixés avec la session du jeu)

chevauchements = 0 ; immobiles = 0 ; passages au rouge ≤ 12 ; véhicules replacés à moins de 150 m du joueur ≤ 45 (recyclage normal) ;
klaxons ≤ 3 par minute ; freinages brusques ≤ 5 % des mesures (stable vers 3,5 à 4 %). `python3 verif/gtb_seuils_circulation.py sortie.txt`.

## Cas validés (pièces volontairement en l'air, etc.)

Le jeu marque ses pièces suspendues par la méta `suspendu` et ses vendeurs assis par la méta `assis` : les scripts les ignorent. Les cas déjà
examinés qui ne portent pas de méta sont dans `verif/godot/gtb/base_flottants.json` et `base_pietons.json` (famille ou position à 1,5 m, avec la raison).
Tout nouvel écart est une régression à examiner, pas à ajouter à la base sans l'avoir compris.

## Limites

Seuls sont contrôlés les MeshInstance3D sous `Lieux` (pas les arbres et props en MultiMesh), les passants du groupe `pnj`, les toits de l'Ararat,
la zone de démo. Les validations des écarts viennent de la session du jeu, pas d'une vérification visuelle d'ayigba. Les scripts supposent la
structure actuelle du jeu (noeuds `Lieux`, `Player`, `histoire`, `Partie`, couche de collision 10 pour le sol) : un changement de cette structure les casse.
