extends SceneTree
## Sonde : liste les corps de collision de la carte autour d'un point (diagnostic d'un blocage de bot).
##   Godot --headless --path verif/godot --script res://sonde.gd -- export=<dossier> x=<est> z=<z glTF> [rayon=4] [y=altitude]
## x et z sont les coordonnées glTF (celles du TRACE de bots_routes.gd). Affiche, pour des sphères de 0,3 m posées tous les 0,5 m
## autour du point à 0,3 / 0,8 / 1,5 m au-dessus du sol, le nom du noeud touché.


func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _lancer() -> void:
	var carte := Node3D.new()
	carte.set_script(load("res://ayigba_carte.gd"))
	carte.set("dossier", _arg("export"))
	carte.set("tout_charger", true)
	root.add_child(carte)
	await physics_frame
	await physics_frame
	var cx := float(_arg("x", "0"))
	var cz := float(_arg("z", "0"))
	var r := float(_arg("rayon", "4"))
	var espace := root.world_3d.direct_space_state
	var q := PhysicsRayQueryParameters3D.create(Vector3(cx, 2000, cz), Vector3(cx, -200, cz))
	var h = espace.intersect_ray(q)
	var sol := float(_arg("y", "0")) if h.is_empty() else (h.position as Vector3).y
	print("sol à %.2f m (%s)" % [sol, "rayon" if not h.is_empty() else "argument"])
	if _arg("profil") == "1":   # matrice des altitudes du sol (cm au-dessus du point), pas de 1 m, lignes = z croissant, colonnes = x croissant
		var rr := int(r)
		for k in range(-rr, rr + 1):
			var ligne := ""
			for i in range(-rr, rr + 1):
				var q2 := PhysicsRayQueryParameters3D.create(Vector3(cx + i, sol + 3.0, cz + k), Vector3(cx + i, sol - 3.0, cz + k))
				var h2 = espace.intersect_ray(q2)
				ligne += "%5s" % ("  --" if h2.is_empty() else str(int(round(((h2.position as Vector3).y - sol) * 100.0))))
			print("PROFIL z%+d" % k, ligne)
	var vus := {}
	var sph := SphereShape3D.new()
	sph.radius = 0.3
	var dx := -r
	while dx <= r:
		var dz := -r
		while dz <= r:
			for dh in [0.3, 0.8, 1.5]:
				var p := PhysicsShapeQueryParameters3D.new()
				p.shape = sph
				p.transform = Transform3D(Basis(), Vector3(cx + dx, sol + dh, cz + dz))
				p.collision_mask = 0xFFFFF
				for res in espace.intersect_shape(p, 8):
					var c = res.collider
					var nom := str(c.get_path()) if c is Node else str(c)
					if not vus.has(nom):
						vus[nom] = [dx, dz, dh]
			dz += 0.5
		dx += 0.5
	for k in vus:
		print("TOUCHE ", k, " premier point dx=%.1f dz=%.1f h=%.1f" % [vus[k][0], vus[k][1], vus[k][2]])
	print("fin sonde : %d corps" % vus.size())
	quit(0)
