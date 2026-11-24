extends SceneTree
## Scanner d'objets flottants ou enterrés dans le VRAI monde de GTB (fenêtre obligatoire, le monde ne charge pas en headless).
## Ce script vit dans le dépôt ayigba ; il ne modifie rien dans le jeu. Lancement (une seule fenêtre Godot à la fois : verrou C:\gtb_local\verrou_fenetre) :
##   GTB_DEMO=1 Godot --path C:\gtb_local\godot --resolution 960x540 --script C:/gtb_local/ay_gtb_flottants.gd -- sortie.json [tolerance]
## Procédure de chargement copiée de tests/scan_textures_map.gd du jeu : scène principale, attente du joueur et du noeud « histoire »,
## nouvelle partie, environ 50 s de rodage, puis scan.
## Contrôle : chaque MeshInstance3D sous le noeud « Lieux » (parkings, bordures, lampadaires, massifs de ronds-points, toits ajoutés...) :
##   bas = altitude du bas de sa boîte englobante dans le monde ; support = la plus haute des deux surfaces sous le bas (+0,5 m) :
##   le sol (couche de collision 10, masque 512) et le sommet d'un bâtiment (collisionneur sous un chemin contenant /bld_).
##   écart = bas - support. > tolérance : « flotte » ; bas sous le sol de plus que la tolérance : « enterre ».
## Filtres (conseils de la session du jeu, 24/11/2026) : rayons depuis le bas de l'objet ; ignore les noeuds portant la méta « suspendu », ceux sous
##   /bld_ ou /Lieu_ (intérieurs), et un objet dont le bas touche le haut d'un autre mesh du même parent (tête de mât sur son mât).
## Ne contrôle PAS les MultiMesh (arbres, props de props.gd : pas de noeud par instance), signalé comme limite dans le rapport.

const MASQUE_SOL := 512   # couche 10
var tol := 0.3
var sortie := "C:/gtb_local/gtb_flottants.json"
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
	_scanner(z)
	return true


func _aabb_monde(n: MeshInstance3D) -> AABB:
	return n.global_transform * n.get_aabb()


func _sol(espace: PhysicsDirectSpaceState3D, x: float, y: float, z: float) -> float:
	var q := PhysicsRayQueryParameters3D.create(Vector3(x, y + 0.5, z), Vector3(x, y - 10.0, z), MASQUE_SOL)   # depuis le BAS de l'objet vers le bas : un abri ou un auvent au-dessus ne compte pas
	var r := espace.intersect_ray(q)
	return NAN if r.is_empty() else r["position"].y


func _toit_batiment(espace: PhysicsDirectSpaceState3D, x: float, y: float, z: float) -> float:
	## sommet d'un batiment sous le point : on saute tout collisionneur qui n'est pas sous /bld_
	var exclus: Array[RID] = []
	for i in 8:
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, y + 0.5, z), Vector3(x, y - 40.0, z), 1)
		q.exclude = exclus
		var r := espace.intersect_ray(q)
		if r.is_empty():
			return NAN
		var c = r["collider"]
		if c is Node and String((c as Node).get_path()).contains("/bld_"):
			return r["position"].y
		exclus.append(r["rid"])
	return NAN


func _soutenu_par_voisin(mi: MeshInstance3D, b: AABB) -> bool:
	## vrai s'il existe un autre MeshInstance3D du même parent dont le haut touche le bas de celui-ci (±0,3 m) avec recouvrement en x et z
	var parent := mi.get_parent()
	if parent == null:
		return false
	for f in parent.get_children():
		if f == mi or not (f is MeshInstance3D) or (f as MeshInstance3D).mesh == null:
			continue
		var c := _aabb_monde(f as MeshInstance3D)
		if absf((c.position.y + c.size.y) - b.position.y) > 0.3:
			continue
		if c.position.x > b.position.x + b.size.x or c.position.x + c.size.x < b.position.x:
			continue
		if c.position.z > b.position.z + b.size.z or c.position.z + c.size.z < b.position.z:
			continue
		return true
	return false


func _scanner(z: Node) -> void:
	var lieux := z.get_node_or_null("Lieux")
	var liste: Array = []
	if lieux != null:
		liste = lieux.find_children("*", "MeshInstance3D", true, false)
	var espace: PhysicsDirectSpaceState3D = root.get_world_3d().direct_space_state
	var defauts: Array = []
	var par_famille := {}
	var sans_support := 0
	for n in liste:
		var mi := n as MeshInstance3D
		if mi.mesh == null or not mi.is_visible_in_tree():
			continue
		if mi.has_meta("suspendu"):
			continue   # pièce volontairement en l'air, marquée par le jeu (têtes de lampadaires, totem, auvent, affiches, cônes de paillotes)
		var chemin := String(mi.get_path())
		if chemin.contains("/bld_") or chemin.contains("/Lieu_"):
			continue   # intérieurs et bâtiments
		var b := _aabb_monde(mi)
		if b.size.length() < 0.05:
			continue
		var cx := b.position.x + b.size.x * 0.5
		var cz := b.position.z + b.size.z * 0.5
		var bas := b.position.y
		var sol := _sol(espace, cx, bas, cz)
		var toit := _toit_batiment(espace, cx, bas, cz)
		var support := NAN
		for s in [sol, toit]:
			if not is_nan(s) and s <= bas + 0.5 and (is_nan(support) or s > support):
				support = s
		var famille := String(mi.get_parent().name)
		if famille == "GeneralSkeleton" or mi.get_parent() is Skeleton3D:
			continue   # corps animés (piétons, joueur) : leur boîte englobante change à chaque pose, ce n'est pas un objet posé
		if is_nan(support):
			sans_support += 1
			if not is_nan(sol) and bas < sol - tol:
				support = sol
			else:
				continue
		var ecart := bas - support
		if ecart > tol and _soutenu_par_voisin(mi, b):
			continue   # tête de mât, toile de parasol : une autre pièce de la même famille touche son bas
		if ecart > tol or (not is_nan(sol) and bas < sol - tol):
			var sens := "flotte" if ecart > tol else "enterre"
			var e := ecart if ecart > tol else bas - sol
			defauts.append({"noeud": String(mi.get_path()), "famille": famille, "x": snappedf(cx, 0.1), "y": snappedf(bas, 0.01), "z": snappedf(cz, 0.1), "ecart": snappedf(e, 0.01), "sens": sens, "sol": snappedf(sol, 0.01) if not is_nan(sol) else null, "toit_batiment": snappedf(toit, 0.01) if not is_nan(toit) else null})
			par_famille[famille] = int(par_famille.get(famille, 0)) + 1
	defauts.sort_custom(func(a, b): return absf(a["ecart"]) > absf(b["ecart"]))
	print("GTB_FLOTTANTS %d MeshInstance3D sous Lieux, %d sans support trouvé, %d défaut(s) au-delà de %.2f m" % [liste.size(), sans_support, defauts.size(), tol])
	print("GTB_FLOTTANTS par famille : ", JSON.stringify(par_famille))
	for d in defauts.slice(0, 25):
		print("GTB_FLOTTANTS %-7s %-24s (%.1f, %.1f, %.1f) ecart %+.2f  %s" % [d["sens"], d["famille"], d["x"], d["y"], d["z"], d["ecart"], d["noeud"]])
	var f := FileAccess.open(sortie, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify({"scannes": liste.size(), "sans_support": sans_support, "tolerance_m": tol, "par_famille": par_famille, "limite": "les MultiMesh (arbres, props de props.gd) ne sont pas contrôlés", "defauts": defauts}, " "))
	quit(0 if defauts.is_empty() else 1)
