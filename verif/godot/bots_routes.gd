extends SceneTree
## Bots dans le moteur : des personnages parcourent les routes de la carte avec la physique de Godot.
##   Godot --headless --path verif/godot --script res://bots_routes.gd -- export=<dossier out/neutre> [routes=200] [bots=24] [gabarit=pieton|vehicule] [rapport=<fichier.json>]
## La carte est chargée zone par zone avec l'adaptateur (res://ayigba_carte.gd), toutes zones chargées, collisions créées.
## Un bot « bloque » révèle un mur invisible ou un obstacle sur une route ; une « chute » révèle un trou.
## routes=0 : toutes les routes. Code de sortie 0 si aucun défaut, 1 sinon.

const MARGE_BORD := 1.5   # un point de route trop près du bord de la carte est ramené à l'intérieur

var _bots: Array = []
var _debut := 0
var _total_routes := 0
var _rapport := ""


func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _lancer() -> void:
	var dossier := _arg("export")
	_rapport = _arg("rapport")
	var carte := Node3D.new()
	carte.set_script(load("res://ayigba_carte.gd"))
	carte.set("dossier", dossier)
	carte.set("tout_charger", true)
	root.add_child(carte)
	var zones: Array = carte.call("zones_chargees")
	print("OK    %d zone(s) chargée(s) avec collisions" % zones.size() if zones.size() > 0 else "ECHEC aucune zone chargée depuis « %s »" % dossier)
	if zones.is_empty():
		quit(1)
		return
	var boite: AABB = carte.call("emprise")
	var lu = JSON.parse_string(FileAccess.get_file_as_string(dossier.path_join("routes_local.json")))
	if typeof(lu) != TYPE_DICTIONARY:
		print("ECHEC routes_local.json illisible")
		quit(1)
		return
	var toutes: Array = lu["routes"]
	var voulu := int(_arg("routes", "200"))
	var pas := 1 if voulu <= 0 else maxi(1, int(ceil(float(toutes.size()) / voulu)))
	var choisies: Array = []
	var vehicule := _arg("gabarit", "pieton") == "vehicule"
	if vehicule:   # un véhicule ne prend que les routes carrossables
		toutes = toutes.filter(func(r): return not r["pieton"])
	for k in range(0, toutes.size(), pas):
		var pts := PackedVector3Array()
		for q in toutes[k]["points"]:
			var x := clampf(q[0], boite.position.x + MARGE_BORD, boite.end.x - MARGE_BORD)
			var z := clampf(-q[1], boite.position.z + MARGE_BORD, boite.end.z - MARGE_BORD)
			pts.append(Vector3(x, float(q[2]) if q.size() > 2 else 0.0, z))   # q[2] : altitude du sol sous le point
		if pts.size() >= 2:
			choisies.append({"id": toutes[k]["id"], "points": pts})
	if _arg("mode") == "traversees":
		# sortie de chaussée : du milieu de la rue jusque sur le bas-côté ou le trottoir, perpendiculairement à la rue
		await physics_frame
		await physics_frame
		var espace := root.get_world_3d().direct_space_state
		choisies.clear()
		for k in range(0, toutes.size(), pas):
			var r: Dictionary = toutes[k]
			var q: Array = r["points"]
			if r["pieton"] or r["revetement"] != "pave" or q.size() < 2:
				continue
			var i := (q.size() - 1) / 2
			var a := Vector3(q[i][0], q[i][2], -q[i][1])
			var b := Vector3(q[i + 1][0], q[i + 1][2], -q[i + 1][1])
			if a.distance_to(b) < 4.0:
				continue
			var milieu := (a + b) * 0.5
			var travers := (b - a).normalized().cross(Vector3.UP)
			for cote in [1.0, -1.0]:
				var but: Vector3 = milieu + travers * cote * (float(r["largeur"]) * 0.5 + 1.3)
				var sol := espace.intersect_ray(PhysicsRayQueryParameters3D.create(but + Vector3(0, 6, 0), but + Vector3(0, -6, 0)))
				if sol.is_empty() or absf(sol["position"].y - milieu.y) > 1.5:
					continue   # pas de sol franc à cet endroit (eau, toit)
				but.y = sol["position"].y
				if not espace.intersect_ray(PhysicsRayQueryParameters3D.create(milieu + Vector3(0, 1, 0), but + Vector3(0, 1, 0))).is_empty():
					continue   # un mur borde la rue ici : ce n'est pas un test de bordure
				choisies.append({"id": "traversee:" + String(r["id"]), "points": PackedVector3Array([milieu, but])})
	_total_routes = choisies.size()
	var nb := clampi(int(_arg("bots", "24")), 1, 64)
	Engine.time_scale = 8.0
	Engine.max_physics_steps_per_frame = 64
	var script_bot: Script = load("res://bot.gd")
	for b in nb:
		var bot := CharacterBody3D.new()
		bot.set_script(script_bot)
		var forme := CollisionShape3D.new()
		var capsule := CapsuleShape3D.new()
		capsule.radius = 0.9 if vehicule else 0.35   # 1,8 m de large : le gabarit d'une voiture
		capsule.height = 1.8 if vehicule else 1.7
		forme.shape = capsule
		forme.position.y = capsule.height * 0.5
		bot.add_child(forme)
		bot.collision_mask = 1
		bot.collision_layer = 2   # les bots ne se gênent pas entre eux
		var lot: Array = []
		for k in range(b, choisies.size(), nb):
			lot.append(choisies[k])
		bot.set("routes", lot)
		bot.set("tolerance", capsule.radius + 0.35)
		root.add_child(bot)
		_bots.append(bot)
	await physics_frame
	await physics_frame
	for bot in _bots:
		bot.call("demarrer")
	_debut = Time.get_ticks_msec()
	print("      %d bot(s) au gabarit %s sur %d route(s) (une route sur %d)" % [nb, "véhicule (1,8 m de large)" if vehicule else "piéton", _total_routes, pas])


func _process(_delta: float) -> bool:
	if _bots.is_empty():
		return false
	for bot in _bots:
		if not bot.get("fini"):
			if Time.get_ticks_msec() - _debut > 900000:
				print("ECHEC délai de 15 minutes dépassé")
				_conclure(true)
				return true
			return false
	_conclure(false)
	return true


func _conclure(hors_delai: bool) -> void:
	var echecs: Array = []
	var distance := 0.0
	var faites := 0
	for bot in _bots:
		echecs.append_array(bot.get("echecs"))
		distance += bot.get("distance")
		faites += bot.get("routes_faites")
	var bloques := 0
	var chutes := 0
	for e in echecs:
		if e["genre"] == "chute":
			chutes += 1
		else:
			bloques += 1
	print("%s routes parcourues sans défaut : %d sur %d (%.1f km à pied)" % ["OK   " if echecs.is_empty() else "ECHEC", faites, _total_routes, distance / 1000.0])
	print("%s blocages (murs invisibles ou obstacles) : %d" % ["OK   " if bloques == 0 else "ECHEC", bloques])
	print("%s chutes (trous) : %d" % ["OK   " if chutes == 0 else "ECHEC", chutes])
	for e in echecs.slice(0, 15):
		print("      %s sur %s en (%.1f, %.1f, %.1f)" % [e["genre"], e["route"], e["x"], e["y"], e["z"]])
	if _rapport != "":
		var f := FileAccess.open(_rapport, FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify({"routes": _total_routes, "routes_sans_defaut": faites, "km": snappedf(distance / 1000.0, 0.01), "blocages": bloques, "chutes": chutes, "defauts": echecs}, " "))
	var ok := echecs.is_empty() and not hors_delai
	print("RESULTAT bots_routes : %s" % ("OK" if ok else "%d DEFAUT(S)" % echecs.size()))
	quit(0 if ok else 1)
