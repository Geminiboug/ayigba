extends SceneTree
## Zones de la démo sans collision de sol : le défaut qui fait tomber le joueur sous la carte (vrai monde de GTB, fenêtre, verrou
## C:\gtb_local\verrou_fenetre). Ne modifie rien dans le jeu. Lancement :
##   GTB_DEMO=1 Godot --path C:\gtb_local\godot --resolution 960x540 --script C:/gtb_local/ay_gtb_sol.gd -- sortie.json [pas_stations_m] [attente_s] [pas_grille_m]
## Procédure : chargement du jeu comme les autres scans, puis le joueur est posé à tour de rôle sur une grille de stations (250 m par défaut) ;
## à chacune, une fois les tuiles chargées (7 s), une grille de rayons verticaux (10 m par défaut, rayon de 125 m) cherche le sol :
##   1. la couche de collision 10 (masque 512 : chaussée, terre, plage, accotement), sinon
##   2. repli sur le premier solide du monde (masque 1) qui n'est ni un bâtiment (/bld_), ni un prop (/Props/), ni un personnage ou un véhicule.
## Un point sans 1 ni 2 est un « trou » : le joueur y tomberait. Les points d'eau (mer, lagune) peuvent en faire partie par construction : à trier.
## Sortie : liste de trous regroupés en amas de 30 m, avec leurs coordonnées, un compte par station, et un code de sortie 0 si aucun trou.
const MASQUE_SOL := 512
var sortie := "C:/gtb_local/gtb_sol.json"
var pas_st := 250.0
var attente := 7.0
var pas_gr := 10.0
var rayon := 125.0
var x0 := -1000.0
var x1 := 1500.0
var z0 := -2000.0
var z1 := 500.0
var t := 0.0
var tp := 0.0
var pret := false
var stations: Array[Vector2] = []
var k := -1
var trous: Array = []
var points := 0
var par_station: Array = []


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	if a.size() > 0:
		sortie = a[0]
	if a.size() > 1:
		pas_st = float(a[1])
	if a.size() > 2:
		attente = float(a[2])
	if a.size() > 3:
		pas_gr = float(a[3])
	rayon = pas_st * 0.5
	var zz := z0 + pas_st * 0.5
	var ligne := 0
	while zz < z1:
		var xs: Array = []
		var xx := x0 + pas_st * 0.5
		while xx < x1:
			xs.append(Vector2(xx, zz))
			xx += pas_st
		if ligne % 2 == 1:
			xs.reverse()
		stations.append_array(xs)
		zz += pas_st
		ligne += 1
	var ch := (load(ProjectSettings.get_setting("application/run/main_scene")) as PackedScene).instantiate()
	root.add_child(ch)
	current_scene = ch


func _ignore(c: Variant) -> bool:
	if not (c is Node):
		return true
	var chemin := String((c as Node).get_path())
	return chemin.contains("/bld_") or chemin.contains("/Props/") or chemin.contains("/Pietons") or chemin.contains("/Circulation") or (c as Node).is_in_group("pnj") or (c as Node).is_in_group("vehicules") or (c as Node).is_in_group("vehicules_circulation")


func _sol_present(espace: PhysicsDirectSpaceState3D, x: float, z: float) -> bool:
	var q := PhysicsRayQueryParameters3D.create(Vector3(x, 80.0, z), Vector3(x, -30.0, z), MASQUE_SOL)
	if not espace.intersect_ray(q).is_empty():
		return true
	var exclus: Array[RID] = []
	for i in 10:
		var q2 := PhysicsRayQueryParameters3D.create(Vector3(x, 80.0, z), Vector3(x, -30.0, z), 1)
		q2.exclude = exclus
		var r := espace.intersect_ray(q2)
		if r.is_empty():
			return false
		if not _ignore(r["collider"]):
			return true
		exclus.append(r["rid"])
	return false


func _sonder(centre: Vector2, espace: PhysicsDirectSpaceState3D) -> void:
	var n := 0
	var xx := centre.x - rayon + pas_gr * 0.5
	while xx < centre.x + rayon:
		var zz := centre.y - rayon + pas_gr * 0.5
		while zz < centre.y + rayon:
			points += 1
			if xx >= x0 and xx <= x1 and zz >= z0 and zz <= z1 and not _sol_present(espace, xx, zz):
				trous.append(Vector2(xx, zz))
				n += 1
			zz += pas_gr
		xx += pas_gr
	par_station.append({"x": centre.x, "z": centre.y, "trous": n})


func _process(d: float) -> bool:
	var z := current_scene
	if not pret:
		t += d
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
		k = -1
		return false
	tp += d
	if tp < (50.0 if k < 0 else attente):   # 50 s de rodage au premier chargement, puis attente par station
		return false
	var espace: PhysicsDirectSpaceState3D = root.get_world_3d().direct_space_state
	if k >= 0:
		_sonder(stations[k], espace)
	k += 1
	tp = 0.0
	if k < stations.size():
		var pl := z.get_node("Player") as Node3D
		pl.global_position = Vector3(stations[k].x + 9.0, 0.6, stations[k].y + 9.0)
		if pl.get("velocity") != null:
			pl.set("velocity", Vector3.ZERO)
		return false
	_finir()
	return true


func _finir() -> void:
	# amas de 30 m
	var amas: Array = []
	for p in trous:
		var trouve := false
		for a in amas:
			if Vector2(a["x"], a["z"]).distance_to(p) < 30.0:
				a["n"] = int(a["n"]) + 1
				trouve = true
				break
		if not trouve:
			amas.append({"x": snappedf(p.x, 1.0), "z": snappedf(p.y, 1.0), "n": 1})
	amas.sort_custom(func(a, b): return int(a["n"]) > int(b["n"]))
	print("GTB_SOL %d stations, %d points sondés, %d trous (points sans sol) en %d amas de 30 m" % [stations.size(), points, trous.size(), amas.size()])
	for a in amas.slice(0, 25):
		print("GTB_SOL amas (%.0f, %.0f) : %d point(s)" % [a["x"], a["z"], a["n"]])
	var f := FileAccess.open(sortie, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"stations": stations.size(), "points": points, "trous": trous.size(), "amas": amas, "par_station": par_station}, " "))
	quit(0 if trous.is_empty() else 1)
