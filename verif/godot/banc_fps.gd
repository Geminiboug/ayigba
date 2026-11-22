extends SceneTree
## Banc d'images par seconde : une caméra vole en cercle au-dessus de la carte chargée à la demande par l'adaptateur.
##   Godot --path verif/godot --script res://banc_fps.gd -- export=<out/neutre> [duree=25] [rayon_vol=250] [sortie=<fichier.json>] [collisions=0]
## Fenêtre 1280x720, synchronisation verticale coupée. Les 4 premières secondes (chargement) sont ignorées.

var _cam: Camera3D
var _carte: Node3D
var _t := 0.0
var _mesures: Array = []
var _duree := 25.0
var _rayon := 250.0
var _centre := Vector3.ZERO
var _sortie := ""


func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _lancer() -> void:
	root.size = Vector2i(1280, 720)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	_duree = float(_arg("duree", "25"))
	_rayon = float(_arg("rayon_vol", "250"))
	_sortie = _arg("sortie")
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.74, 0.88)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.75, 0.78, 0.85)
	root.add_child(env)
	var soleil := DirectionalLight3D.new()
	soleil.rotation_degrees = Vector3(-50, -35, 0)
	root.add_child(soleil)
	_cam = Camera3D.new()
	_cam.far = 1500.0
	root.add_child(_cam)
	_cam.current = true
	_carte = Node3D.new()
	_carte.set_script(load("res://ayigba_carte.gd"))
	_carte.set("dossier", _arg("export"))
	_carte.set("avec_collisions", _arg("collisions", "0") == "1")
	_carte.set("cible", _cam.get_path())
	root.add_child(_carte)
	var boite: AABB = _carte.call("emprise")
	_centre = boite.get_center()
	_centre.y = 0.0
	print("carte chargee, emprise ", boite)


func _process(delta: float) -> bool:
	if _cam == null:
		return false
	_t += delta
	var a := _t * 0.12
	_cam.global_position = _centre + Vector3(cos(a) * _rayon, 45.0, sin(a) * _rayon)
	_cam.look_at(_centre + Vector3(0, 5, 0))
	if _t > 4.0:
		_mesures.append(delta)
	if _t > _duree:
		_conclure()
		return true
	return false


func _conclure() -> void:
	var tri := _mesures.duplicate()
	tri.sort()
	var n := tri.size()
	var somme := 0.0
	for d in tri:
		somme += d
	var moy: float = somme / maxi(n, 1)
	var p99: float = tri[mini(n - 1, int(n * 0.99))]
	var r := {
		"images": n, "fps_moyen": snappedf(1.0 / moy, 0.1), "fps_1pct_bas": snappedf(1.0 / p99, 0.1),
		"ms_moyen": snappedf(moy * 1000.0, 0.01), "ms_p99": snappedf(p99 * 1000.0, 0.01),
		"zones_chargees": _carte.call("zones_chargees").size(), "gpu": RenderingServer.get_video_adapter_name(),
		"memoire_video_mo": snappedf(RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED) / 1048576.0, 0.1),
		"objets_dessines": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
		"triangles_dessines": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
	}
	print("RESULTAT banc_fps : ", JSON.stringify(r))
	if _sortie != "":
		var f := FileAccess.open(_sortie, FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(r, " "))
	quit(0)
