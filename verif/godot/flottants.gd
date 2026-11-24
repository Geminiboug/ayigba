extends SceneTree
## Scanner d'objets flottants ou enterrés : compare l'altitude ATTENDUE d'objets posés (arbres, poteaux, toits...) à l'altitude du sol
## (ou du sommet du bâtiment) réellement présente dans les collisions, par des rayons verticaux. Un écart anormal = un objet qui flotte
## ou qui est dans le sol (le défaut des toits et des massifs de rond-point trouvé le 23/11/2026 dans GTB).
##
## Deux façons de donner les objets :
##   points=<fichier.json>   liste [{"id","genre","x","y","z","mode"}] en repère Godot (y = altitude attendue ; mode "sol" ou "toit") ;
##                           `ayigba points-controle <projet>` écrit ce fichier pour une carte ayigba.
##   groupes=a,b,c           noeuds des groupes Godot nommés (leur global_position donne x, y, z ; mode "sol")
## Carte à charger :
##   export=<dossier out/neutre>   charge les zones d'une carte ayigba avec collisions (adaptateur ayigba_carte.gd)
##   scene=res://chemin.tscn       charge une scène (jeu ou test) ; elle doit contenir des collisions
## Sol : par défaut les couches terrain, chaussees, trottoirs, berges de la carte ayigba (nom du MeshInstance parent du corps de collision) ;
##   masque=<entier>             masque de collision Godot du SOL pour une scène de jeu (ex. 512 pour la couche 10)
## Réglages : tolerance=0.3 (m), sortie=<rapport.json>.
## Sortie : liste des objets au-delà de la tolérance, comptes par genre, code de sortie 0 si aucun défaut, 1 sinon.

const SOLS := ["terrain", "chaussees", "trottoirs", "berges"]
var _tol := 0.3
var _masque := 0


func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _sol(espace: PhysicsDirectSpaceState3D, x: float, y: float, z: float) -> float:
	var exclus: Array[RID] = []
	for i in 8:
		var q := PhysicsRayQueryParameters3D.create(Vector3(x, y + 3.0, z), Vector3(x, y - 8.0, z), _masque if _masque != 0 else 1)
		q.exclude = exclus
		var r := espace.intersect_ray(q)
		if r.is_empty():
			return NAN
		if _masque != 0:
			return r["position"].y   # le masque ne désigne déjà que le sol
		var corps = r["collider"]
		var parent: Node = corps.get_parent() if corps is Node else null
		if parent != null and String(parent.name) in SOLS:
			return r["position"].y
		exclus.append(r["rid"])
	return NAN


func _sommet(espace: PhysicsDirectSpaceState3D, x: float, y: float, z: float) -> float:
	var r := espace.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(x, y + 25.0, z), Vector3(x, y - 8.0, z), 1))
	return NAN if r.is_empty() else r["position"].y


func _lancer() -> void:
	_tol = float(_arg("tolerance", "0.3"))
	_masque = int(_arg("masque", "0"))
	if _arg("export") != "":
		var carte := Node3D.new()
		carte.set_script(load("res://ayigba_carte.gd"))
		carte.set("dossier", _arg("export"))
		carte.set("tout_charger", true)
		root.add_child(carte)
	elif _arg("scene") != "":
		root.add_child(load(_arg("scene")).instantiate())
	else:
		print("ECHEC donne export=<dossier> ou scene=res://...")
		quit(2)
		return
	for i in 4:
		await physics_frame
	var objets: Array = []
	if _arg("points") != "":
		var lu = JSON.parse_string(FileAccess.get_file_as_string(_arg("points")))
		if typeof(lu) != TYPE_ARRAY:
			print("ECHEC fichier de points illisible")
			quit(2)
			return
		objets = lu
	for g in _arg("groupes").split(",", false):
		for n in get_nodes_in_group(g):
			if n is Node3D:
				var p: Vector3 = (n as Node3D).global_position
				objets.append({"id": String(n.name), "genre": g, "x": p.x, "y": p.y, "z": p.z, "mode": "sol"})
	if objets.is_empty():
		print("ECHEC aucun objet à contrôler")
		quit(2)
		return
	var espace := root.get_world_3d().direct_space_state
	var defauts: Array = []
	var sans_reponse := 0
	var par_genre := {}
	for o in objets:
		var x: float = o["x"]
		var y: float = o["y"]
		var z: float = o["z"]
		var genre := String(o.get("genre", "?"))
		var vu: float = _sommet(espace, x, y, z) if o.get("mode", "sol") == "toit" else _sol(espace, x, y, z)
		if is_nan(vu):
			sans_reponse += 1
			continue
		var ecart := y - vu   # > 0 : l'objet est au-dessus de ce que les collisions montrent
		if absf(ecart) > _tol:
			defauts.append({"id": o["id"], "genre": genre, "x": snappedf(x, 0.1), "y": snappedf(y, 0.01), "z": snappedf(z, 0.1), "attendu": snappedf(y, 0.01), "vu": snappedf(vu, 0.01), "ecart": snappedf(ecart, 0.01), "sens": "flotte" if ecart > 0 else "enterre"})
			par_genre[genre] = int(par_genre.get(genre, 0)) + 1
	defauts.sort_custom(func(a, b): return absf(a["ecart"]) > absf(b["ecart"]))
	print("%d objet(s) contrôlé(s), %d sans réponse (aucune collision sous le point), %d défaut(s) au-delà de %.2f m" % [objets.size(), sans_reponse, defauts.size(), _tol])
	print("par genre : ", JSON.stringify(par_genre))
	for d in defauts.slice(0, 15):
		print("      %-8s %-14s en (%.1f, %.1f, %.1f) attendu %.2f vu %.2f ecart %+.2f" % [d["sens"], d["genre"], d["x"], d["y"], d["z"], d["attendu"], d["vu"], d["ecart"]])
	if _arg("sortie") != "":
		var f := FileAccess.open(_arg("sortie"), FileAccess.WRITE)
		if f:
			f.store_string(JSON.stringify({"controles": objets.size(), "sans_reponse": sans_reponse, "tolerance_m": _tol, "par_genre": par_genre, "defauts": defauts}, " "))
	print("RESULTAT flottants : %s" % ("OK" if defauts.is_empty() else "%d DEFAUT(S)" % defauts.size()))
	quit(0 if defauts.is_empty() else 1)
