extends SceneTree
## Contrôle fin des toits à quatre pans ajoutés sur les maisons voisines de l'Ararat, maison par maison (vrai monde de GTB, fenêtre, verrou
## C:\gtb_local\verrou_fenetre). Ne modifie rien dans le jeu. Lancement :
##   GTB_DEMO=1 Godot --path C:\gtb_local\godot --resolution 960x540 --script C:/gtb_local/ay_gtb_toits.gd -- sortie.json [tolerance_m]
## Les toits sont de gros MeshInstance3D (un par couleur) sous Lieux/AbordsAraratExterieur, chacun fait de séries de 6 triangles (4 pans, ou 2 pans
## plus 2 croupes) qui partent d'un rectangle (`ararat_exterieur.gd _toit_croupe`). Le script découpe chaque maillage en toits de 18 sommets,
## garde ceux qui ont 6 positions distinctes et un faîte (hauteur > 0,3 m : écarte les dalles planes des annexes), calcule le niveau d'égout
## (y le plus bas) et son rectangle, puis, par des rayons vers le bas sur 5 points (centre et 4 points à mi-chemin des coins ; seul le centre doit toucher un bâtiment), vérifie que le
## collisionneur touché est celui d'un bâtiment (chemin contenant /bld_) et que son sommet est à ±tolérance (0,1 m par défaut) du niveau d'égout.
## Défauts : « pas_de_batiment » (le rayon touche autre chose : toit posé sur rien ou sur un arbre), « decale » (écart > tolérance).

var tol := 0.1
var sortie := "C:/gtb_local/gtb_toits.json"
var t := 0.0
var tp := 0.0
var pret := false
var fait := false


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	if a.size() > 0:
		sortie = a[0]
	if a.size() > 1:
		tol = float(a[1])
	var ch := (load(ProjectSettings.get_setting("application/run/main_scene")) as PackedScene).instantiate()
	root.add_child(ch)
	current_scene = ch


func _process(d: float) -> bool:
	t += d
	tp += d
	var z := current_scene
	if not pret:
		if z == null or not z.has_node("Player"):
			return t > 400.0
		var hh := get_first_node_in_group("histoire")
		if hh == null or (hh.get("points") as Dictionary).is_empty():
			return t > 400.0
		var m := z.get_node_or_null("Menus")
		if m:
			m.call("_close")
		root.get_node("Partie").nouvelle_partie()
		pret = true
		tp = 0.0
		return false
	if tp < 50.0 or fait:
		return false
	fait = true
	_controler(z)
	return true


func _sommet_batiment(espace: PhysicsDirectSpaceState3D, x: float, z: float, y_egout: float) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(Vector3(x, y_egout + 25.0, z), Vector3(x, y_egout - 15.0, z), 1)
	var r := espace.intersect_ray(q)
	if r.is_empty():
		return {"ok": false, "raison": "rien"}
	var chemin := String((r["collider"] as Node).get_path()) if r["collider"] is Node else ""
	return {"ok": chemin.contains("/bld_"), "y": float(r["position"].y), "chemin": chemin}


func _controler(z: Node) -> void:
	var espace: PhysicsDirectSpaceState3D = root.get_world_3d().direct_space_state
	var abords := z.get_node_or_null("Lieux/AbordsAraratExterieur")
	var defauts: Array = []
	var toits := 0
	var maillages := 0
	var pires := []
	if abords != null:
		for n in abords.get_children():
			var mi := n as MeshInstance3D
			if mi == null or mi.mesh == null or mi.mesh.get_surface_count() == 0:
				continue
			var arr: Array = mi.mesh.surface_get_arrays(0)
			var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			if arr[Mesh.ARRAY_INDEX] != null and (arr[Mesh.ARRAY_INDEX] as PackedInt32Array).size() > 0:
				var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX]
				var w := PackedVector3Array()
				for i in idx:
					w.append(v[i])
				v = w
			if v.size() == 0 or v.size() % 18 != 0:
				continue
			maillages += 1
			var tr := mi.global_transform
			for s in range(0, v.size(), 18):
				var pts := {}
				var ymin := 1e9
				var ymax := -1e9
				for k in 18:
					var p := tr * v[s + k]
					pts[Vector3(snappedf(p.x, 0.001), snappedf(p.y, 0.001), snappedf(p.z, 0.001))] = true
					ymin = minf(ymin, p.y)
					ymax = maxf(ymax, p.y)
				if pts.size() != 6 or ymax - ymin < 0.3:
					continue
				toits += 1
				var coins: Array = []
				var cx := 0.0
				var cz := 0.0
				for p in pts.keys():
					if absf(p.y - ymin) < 0.01:
						coins.append(p)
						cx += p.x
						cz += p.z
				if coins.size() != 4:
					continue
				cx /= 4.0
				cz /= 4.0
				var echantillons := [Vector2(cx, cz)]
				for c in coins:
					var dx: float = cx - c.x
					var dz: float = cz - c.z
					var l := maxf(sqrt(dx * dx + dz * dz), 0.001)
					echantillons.append(Vector2(cx - dx * 0.5, cz - dz * 0.5))   # à mi-chemin entre le centre et le coin : bien à l'intérieur de l'emprise
				var pire := 0.0
				var raison := ""
				for k in echantillons.size():
					var e: Vector2 = echantillons[k]
					var r := _sommet_batiment(espace, e.x, e.y, ymin)
					if not r["ok"]:
						if k == 0:   # le centre doit être sur un bâtiment ; un point intermédiaire hors emprise (bâtiment non rectangulaire) est ignoré
							raison = "pas_de_batiment"
							pire = 99.0
							break
						continue
					var ec := absf(float(r["y"]) - ymin)
					if ec > pire:
						pire = ec
				if raison == "" and pire > tol:
					raison = "decale"
				if raison != "":
					defauts.append({"x": snappedf(cx, 0.1), "z": snappedf(cz, 0.1), "egout_y": snappedf(ymin, 0.01), "faite_y": snappedf(ymax, 0.01), "ecart_max": snappedf(pire, 0.01), "raison": raison, "maillage": String(mi.get_path())})
				pires.append(pire if pire < 99.0 else -1.0)
	var ok_max := 0.0
	for p in pires:
		if p >= 0.0:
			ok_max = maxf(ok_max, p)
	print("GTB_TOITS %d maillage(s), %d toit(s) à quatre pans contrôlé(s), %d défaut(s) (tolérance %.2f m), écart maximal mesuré %.2f m" % [maillages, toits, defauts.size(), tol, ok_max])
	defauts.sort_custom(func(a, b): return float(a["ecart_max"]) > float(b["ecart_max"]))
	for d in defauts.slice(0, 20):
		print("GTB_TOITS %-15s (%.1f, %.1f) égout %.2f faîte %.2f écart %.2f" % [d["raison"], d["x"], d["z"], d["egout_y"], d["faite_y"], d["ecart_max"]])
	var f := FileAccess.open(sortie, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"toits": toits, "tolerance_m": tol, "ecart_max_mesure": ok_max, "defauts": defauts}, " "))
	quit(0 if defauts.is_empty() and toits > 0 else 1)
