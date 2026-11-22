extends SceneTree
## Mesure autour des défauts d'un rapport de bots : pente du sol et largeur libre, pour dire si un défaut vient d'une rampe
## (pont rendu en remblai) ou d'un passage étroit (deux murs trop proches), ou d'aucun des deux (donc plutôt de la conduite du bot).
##   Godot --headless --path verif/godot --script res://analyse_defauts.gd -- export=<out/neutre> rapport=<bots.json> [sortie=<analyse.json>]
## Pour chaque défaut : pente maximale (%) du sol sur un cercle de 3 m, dénivelé sur 6 m, écart libre minimal entre deux murs
## opposés à 0,8 m du sol (rayons horizontaux de 5 m, 8 directions par paires), nombre de zones d'eau sous le point.

func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _sol(espace: PhysicsDirectSpaceState3D, x: float, y: float, z: float) -> float:
	var r := espace.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(x, y + 4.0, z), Vector3(x, y - 8.0, z), 1))
	return r["position"].y if not r.is_empty() else NAN


func _lancer() -> void:
	var dossier := _arg("export")
	var carte := Node3D.new()
	carte.set_script(load("res://ayigba_carte.gd"))
	carte.set("dossier", dossier)
	carte.set("tout_charger", true)
	root.add_child(carte)
	await physics_frame
	await physics_frame
	var lu = JSON.parse_string(FileAccess.get_file_as_string(_arg("rapport")))
	if typeof(lu) != TYPE_DICTIONARY:
		print("ECHEC rapport illisible")
		quit(1)
		return
	var espace := root.get_world_3d().direct_space_state
	var sortie: Array = []
	for d in lu["defauts"]:
		var x: float = d["x"]
		var y: float = d["y"]
		var z: float = d["z"]
		var s0 := _sol(espace, x, y, z)
		var pente := 0.0
		var deniv := 0.0
		for k in 16:
			var a := TAU * k / 16.0
			var s3 := _sol(espace, x + cos(a) * 3.0, y, z + sin(a) * 3.0)
			var s6 := _sol(espace, x + cos(a) * 6.0, y, z + sin(a) * 6.0)
			if not is_nan(s0) and not is_nan(s3):
				pente = maxf(pente, absf(s3 - s0) / 3.0 * 100.0)
			if not is_nan(s0) and not is_nan(s6):
				deniv = maxf(deniv, absf(s6 - s0))
		var libre := 99.0
		var h0 := (s0 if not is_nan(s0) else y) + 0.8
		for k in 4:
			var a := PI * k / 4.0
			var dir := Vector3(cos(a), 0.0, sin(a))
			var o := Vector3(x, h0, z)
			var p := espace.intersect_ray(PhysicsRayQueryParameters3D.create(o, o + dir * 5.0, 1))
			var q := espace.intersect_ray(PhysicsRayQueryParameters3D.create(o, o - dir * 5.0, 1))
			var l1 := 5.0 if p.is_empty() else o.distance_to(p["position"])
			var l2 := 5.0 if q.is_empty() else o.distance_to(q["position"])
			libre = minf(libre, l1 + l2)
		var cause := "inconnue"
		if libre < 3.2:
			cause = "passage_etroit"
		elif pente > 25.0 or deniv > 1.2:
			cause = "rampe"
		sortie.append({"genre": d["genre"], "route": d["route"], "x": x, "z": z, "pente_pct": snappedf(pente, 0.1), "deniv_6m": snappedf(deniv, 0.01), "libre_m": snappedf(libre, 0.1), "cause_probable": cause})
		print("%-8s %-22s pente %5.1f %%  deniv6m %4.2f  libre %4.1f m  -> %s" % [d["genre"], d["route"], pente, deniv, libre, cause])
	var n := {}
	for e in sortie:
		n[e["cause_probable"]] = int(n.get(e["cause_probable"], 0)) + 1
	print("RESUME ", JSON.stringify(n))
	if _arg("sortie") != "":
		var f := FileAccess.open(_arg("sortie"), FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify(sortie, " "))
	quit(0)
