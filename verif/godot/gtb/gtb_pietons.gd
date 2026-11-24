extends SceneTree
## Piétons et joueur dans un mur ou sous le sol, dans le VRAI monde de GTB (fenêtre obligatoire, verrou C:\gtb_local\verrou_fenetre).
## Ne modifie rien dans le jeu. Lancement :
##   GTB_DEMO=1 Godot --path C:\gtb_local\godot --resolution 960x540 --script C:/gtb_local/ay_gtb_pietons.gd -- sortie.json [balayages] [pause_s]
## Chargement copié de tests/scan_textures_map.gd (scène principale, joueur, noeud « histoire », nouvelle partie, 50 s de rodage).
## À chaque balayage, pour chaque noeud du groupe « pnj » et pour le joueur :
##   - « sous_le_sol » : bas du corps plus bas que le sol (couche de collision 10, masque 512) de plus de 0,3 m ;
##   - « sans_sol » : aucun sol sous le corps dans les 8 m (couche 10, sinon premier solide hors bâtiments et props) ;
##   - « centre_dans_un_solide » (défaut réel, seuil donné par la session du jeu) : une sphère de 5 cm au centre du passant, à 0,5 m et à 1,2 m du pied, touche un solide du monde ;
##   - « effleurement » (pas un défaut) : une capsule de 0,25 m de rayon et 1,4 m de haut (bas à 0,3 m au-dessus du pied, pour ne pas toucher le sol)
##     recoupe un solide du monde (masque 1) autre que le sol et que les autres personnages.
## Arguments : sortie.json [balayages] [pause_s] [base_connus.json]. Les passants portant la méta « assis » sont ignorés.
## Les balayages sont espacés (défaut 4 balayages, 12 s) parce que les passants marchent ; un même passant n'est compté qu'une fois par type.
const MASQUE_SOL := 512
var sortie := "C:/gtb_local/gtb_pietons.json"
var balayages := 4
var pause := 12.0
var t := 0.0
var tp := 0.0
var pret := false
var fait_n := 0
var prochain := 50.0
var vus := {}
var defauts: Array = []
var total_obs := 0
var base_connus: Array = []   # cas examinés et acceptés : [{"x","z","raison"}] (position à 1,5 m)


func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	if a.size() > 0:
		sortie = a[0]
	if a.size() > 1:
		balayages = int(a[1])
	if a.size() > 2:
		pause = float(a[2])
	if a.size() > 3 and FileAccess.file_exists(a[3]):
		var lu = JSON.parse_string(FileAccess.get_file_as_string(a[3]))
		if typeof(lu) == TYPE_ARRAY:
			base_connus = lu
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
	if tp < prochain:
		return false
	_balayer(z)
	fait_n += 1
	prochain = tp + pause
	if fait_n >= balayages:
		_finir()
		return true
	return false


func _corps(z: Node) -> Array:
	var liste: Array = []
	var j := z.get_node_or_null("Player")
	if j is Node3D:
		liste.append(j)
	for n in get_nodes_in_group("pnj"):
		if n is Node3D and (n as Node3D).is_visible_in_tree():
			liste.append(n)
	return liste


func _balayer(z: Node) -> void:
	var espace: PhysicsDirectSpaceState3D = root.get_world_3d().direct_space_state
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.25
	capsule.height = 1.4
	for n in _corps(z):
		var p: Vector3 = (n as Node3D).global_position
		total_obs += 1
		var nom := String(n.name)
		if n.has_meta("assis"):
			continue   # vendeur assis à un étal : immobile, contre la caisse de l'étal par construction (déclaré par le jeu)
		var exclus: Array[RID] = []
		if n is CollisionObject3D:
			exclus.append((n as CollisionObject3D).get_rid())
		# sol (couche 10) sous le corps
		var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, 2.0, 0), p + Vector3(0, -8.0, 0), MASQUE_SOL)
		var r := espace.intersect_ray(q)
		if r.is_empty():
			r = _sol_nu(espace, p)   # le sol nu hors surface nommée n'a pas de couche 10 : repli sur le premier solide hors bâtiments et props
		if r.is_empty():
			_noter(nom, "sans_sol", p, "")
		elif p.y < float(r["position"].y) - 0.3:
			_noter(nom, "sous_le_sol", p, "sol à %.2f, pied à %.2f" % [r["position"].y, p.y])
		# mur : capsule contre les solides du monde autres que le sol
		var sq := PhysicsShapeQueryParameters3D.new()
		sq.shape = capsule
		sq.transform = Transform3D(Basis.IDENTITY, p + Vector3(0, 1.0, 0))
		sq.collision_mask = 1
		sq.exclude = exclus
		sq.collide_with_areas = false
		# 1) le CENTRE du passant (sphère de 10 cm à 0,5 m et à 1,2 m du pied) : défaut réel, car le jeu évite le point central
		var point := SphereShape3D.new()
		point.radius = 0.05   # défaut réel = centre à moins de 5 cm d une paroi (seuil convenu avec la session du jeu)
		var centre_pris := false
		for h_ in [0.5, 1.2]:
			var pq := PhysicsShapeQueryParameters3D.new()
			pq.shape = point
			pq.transform = Transform3D(Basis.IDENTITY, p + Vector3(0, h_, 0))
			pq.collision_mask = 1
			pq.exclude = exclus
			pq.collide_with_areas = false
			for h in espace.intersect_shape(pq, 8):
				var c = h["collider"]
				if c is Node and not _ignore(c as Node):
					_noter(nom, "centre_dans_un_solide", p, "à %.1f m du pied : %s" % [h_, String((c as Node).get_path())])
					centre_pris = true
					break
			if centre_pris:
				break
		# 2) la capsule de 0,25 m : simple effleurement (le passant longe un mur, un tronc ou un poteau), compté à part
		if not centre_pris:
			for h in espace.intersect_shape(sq, 8):
				var c2 = h["collider"]
				if c2 is Node and not _ignore(c2 as Node):
					_noter(nom, "effleurement", p, String((c2 as Node).get_path()))
					break


func _sol_nu(espace: PhysicsDirectSpaceState3D, p: Vector3) -> Dictionary:
	var exclus: Array[RID] = []
	for i in 8:
		var q := PhysicsRayQueryParameters3D.create(p + Vector3(0, 1.0, 0), p + Vector3(0, -8.0, 0), 1)
		q.exclude = exclus
		var r := espace.intersect_ray(q)
		if r.is_empty():
			return {}
		var chemin := String((r["collider"] as Node).get_path()) if r["collider"] is Node else ""
		if chemin.contains("/bld_") or chemin.contains("/Props/") or chemin.contains("/Pietons") or chemin.contains("/Circulation"):
			exclus.append(r["rid"])
			continue
		return r
	return {}


func _ignore(c: Node) -> bool:
	var chemin := String(c.get_path())
	return chemin.contains("/Pietons") or chemin.contains("/Circulation") or c.is_in_group("pnj")


func _noter(nom: String, genre: String, p: Vector3, detail: String) -> void:
	for k in base_connus:
		if absf(float(k.get("x", 1e9)) - p.x) < 1.5 and absf(float(k.get("z", 1e9)) - p.z) < 1.5:
			return
	var cle := nom + "|" + genre
	if vus.has(cle):
		return
	vus[cle] = true
	defauts.append({"noeud": nom, "genre": genre, "x": snappedf(p.x, 0.1), "y": snappedf(p.y, 0.01), "z": snappedf(p.z, 0.1), "detail": detail})


func _finir() -> void:
	var par := {}
	for d in defauts:
		par[d["genre"]] = int(par.get(d["genre"], 0)) + 1
	print("GTB_PIETONS %d observation(s) sur %d balayage(s), %d défaut(s) distinct(s)" % [total_obs, fait_n, defauts.size()])
	print("GTB_PIETONS par genre : ", JSON.stringify(par))
	for d in defauts.slice(0, 25):
		print("GTB_PIETONS %-12s %-22s (%.1f, %.1f, %.1f) %s" % [d["genre"], d["noeud"], d["x"], d["y"], d["z"], d["detail"]])
	var f := FileAccess.open(sortie, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"observations": total_obs, "balayages": fait_n, "par_genre": par, "defauts": defauts}, " "))
	quit(0 if int(par.get("centre_dans_un_solide", 0)) == 0 and int(par.get("sous_le_sol", 0)) == 0 and int(par.get("sans_sol", 0)) == 0 else 1)   # les effleurements ne font pas échouer
