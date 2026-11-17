extends Node3D
## Adaptateur Godot 4 pour une carte ayigba découpée en zones (dossier d'export contenant zones.json et zones/*.glb).
## Il ne contient aucune logique de jeu : il charge les zones autour d'une cible, crée les collisions des couches
## qui en demandent, et règle les niveaux de détail (bâtiments réels de près, boîtes de loin, décors de près seulement).
##
## Utilisation : ajouter un Node3D avec ce script, régler `dossier` (par exemple "res://carte/cadjehoun") et `cible`
## (le joueur ou la caméra). Pour tout charger d'un coup (petite carte, tests) : `tout_charger = true`.
## Repère : X = est, Y = haut, Z = sud, en mètres, origine au centre de la carte.

signal zone_chargee(nom: String)
signal zone_liberee(nom: String)

@export_dir var dossier := ""
@export var cible: NodePath
@export var rayon_chargement := 600.0   ## les zones dont le centre est plus près que ce rayon sont chargées
@export var marge_liberation := 150.0   ## une zone est libérée au-delà de rayon_chargement + cette marge
@export var tout_charger := false
@export var avec_collisions := true

var index := {}
var _zones := {}      # nom -> Node3D chargé
var _centres := {}    # nom -> Vector3
var _attente := 0.0


func _ready() -> void:
	lire_index()
	if tout_charger:
		for z in index.get("zones", []):
			charger_zone(z)


func lire_index() -> bool:
	var chemin := dossier.path_join("zones.json")
	if not FileAccess.file_exists(chemin):
		push_error("ayigba : zones.json introuvable dans « %s »" % dossier)
		return false
	var lu = JSON.parse_string(FileAccess.get_file_as_string(chemin))
	if typeof(lu) != TYPE_DICTIONARY:
		push_error("ayigba : zones.json illisible")
		return false
	index = lu
	for z in index["zones"]:
		var e: Array = z["emprise"]   # ouest, sud, est, nord dans le repère local (y vers le nord)
		_centres[z["nom"]] = Vector3((e[0] + e[2]) * 0.5, 0.0, -(e[1] + e[3]) * 0.5)
	return true


func emprise() -> AABB:
	## Emprise de toute la carte dans le repère Godot.
	var boite := AABB()
	var premier := true
	for z in index.get("zones", []):
		var e: Array = z["emprise"]
		var b := AABB(Vector3(e[0], -5.0, -e[3]), Vector3(e[2] - e[0], 60.0, e[3] - e[1]))
		boite = b if premier else boite.merge(b)
		premier = false
	return boite


func _process(delta: float) -> void:
	if tout_charger or cible.is_empty() or index.is_empty():
		return
	_attente -= delta
	if _attente > 0.0:
		return
	_attente = 0.5
	var n := get_node_or_null(cible) as Node3D
	if n == null:
		return
	var p := n.global_position
	for z in index["zones"]:
		var nom: String = z["nom"]
		var d := Vector2(p.x - _centres[nom].x, p.z - _centres[nom].z).length()
		if d <= rayon_chargement and not _zones.has(nom):
			charger_zone(z)
			return   # une zone par passage : pas de saccade
		if d > rayon_chargement + marge_liberation and _zones.has(nom):
			liberer_zone(nom)


func charger_zone(z: Dictionary) -> Node3D:
	var nom: String = z["nom"]
	if _zones.has(nom):
		return _zones[nom]
	var doc := GLTFDocument.new()
	var etat := GLTFState.new()
	var chemin := dossier.path_join(z["fichier"])
	if doc.append_from_file(chemin, etat) != OK:
		push_error("ayigba : zone illisible : %s" % chemin)
		return null
	var scene := doc.generate_scene(etat) as Node3D
	if scene == null:
		return null
	scene.name = nom
	var detail: float = index.get("distance_detail_m", 350.0)
	var couches := {}
	for c in z["couches"]:
		couches[c["nom"]] = c
	for n in scene.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		var c: Dictionary = couches.get(String(mi.name), {})
		match c.get("visible", "toujours"):
			"pres":
				mi.visibility_range_end = detail
				mi.visibility_range_end_margin = 20.0
			"loin":
				mi.visibility_range_begin = detail
				mi.visibility_range_begin_margin = 20.0
		if avec_collisions and c.get("collision", false):
			var corps := StaticBody3D.new()
			var forme := CollisionShape3D.new()
			forme.shape = mi.mesh.create_trimesh_shape()
			corps.add_child(forme)
			mi.add_child(corps)
	add_child(scene)
	_zones[nom] = scene
	zone_chargee.emit(nom)
	return scene


func liberer_zone(nom: String) -> void:
	if _zones.has(nom):
		_zones[nom].queue_free()
		_zones.erase(nom)
		zone_liberee.emit(nom)


func zones_chargees() -> Array:
	return _zones.keys()
