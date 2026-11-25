extends SceneTree
## Arrêt sans recul (demande de la session du jeu, 25/11/2026) : un véhicule freiné à l'arrêt ne doit pas passer en marche arrière tout seul.
## Pour un zem et une berline, lancés à 12 m/s puis freinés :
##   joueur, frein relâché 0,3 s après l'arrêt : recul <= 0,3 m ;
##   joueur, frein tenu 1,0 s après l'arrêt (> 0,35 s) : le véhicule recule ;
##   pilote automatique sans braquage : aucun recul (<= 0,3 m) ; avec braquage : recule (manoeuvre voulue).
## Lancement (AVEC fenêtre, GTB_DEMO=1, verrou de fenêtre) :
##   Godot --path <copie du jeu> --resolution 640x360 --script C:/gtb_local/ay_gtb_arret.gd
## Chargement comme gtb_pietons.gd (scène principale, joueur, noeud « histoire », nouvelle partie). Les véhicules sont posés dans un couloir
## dégagé de 40 m (rayons) trouvé autour du joueur. Ne modifie rien dans le jeu.

const V0 := 12.0
const COULOIR := 40.0
const SCENARIOS := [
	{"nom": "joueur, frein relâché 0,3 s après l'arrêt", "joueur": true, "tenue": 0.3, "braq": 0.0, "recul": false},
	{"nom": "joueur, frein tenu 2,0 s après l'arrêt", "joueur": true, "tenue": 2.0, "braq": 0.0, "recul": true},
	{"nom": "pilote auto sans braquage", "joueur": false, "tenue": 1.5, "braq": 0.0, "recul": false},
	{"nom": "pilote auto avec braquage", "joueur": false, "tenue": 1.5, "braq": 0.5, "recul": true},
]
const MODELES := ["zem", "veh_berline"]

var t := 0.0
var pret := false
var fails := 0
var file: Array = []
var courant := -1
var v: Node3D
var phase := 0
var tp := 0.0
var depart := Vector3.ZERO
var avant := Vector3(0, 0, -1)
var dir := Vector2(0, -1)
var p_arret := 0.0
var v_min := 0.0
var attente := 0.0
var tenir_frein := false   # le frein du joueur est appuyé au début de CHAQUE pas de physique (voir _initialize)


func _check(ok: bool, msg: String) -> void:
	print(("OK    " if ok else "ECHEC ") + msg)
	if not ok:
		fails += 1


func _initialize() -> void:
	var ch := (load(ProjectSettings.get_setting("application/run/main_scene")) as PackedScene).instantiate()
	root.add_child(ch)
	current_scene = ch
	# Une fenêtre sans focus fait relâcher les touches par Godot au début de chaque image, avant la physique : le véhicule verrait le frein à 0
	# alors que ce script le voit à 1. On appuie donc au début de chaque pas de physique (signal physics_frame, émis avant les noeuds).
	physics_frame.connect(func() -> void:
		if tenir_frein:
			var e := InputEventAction.new()
			e.action = "brake"
			e.pressed = true
			e.strength = 1.0
			Input.parse_input_event(e))
	var rapide := OS.get_environment("GTB_ARRET_RAPIDE") == "1"   # essai ciblé : berline, scénario « frein tenu » seulement
	for m in MODELES:
		for s in SCENARIOS:
			if rapide and (m != "veh_berline" or not s["joueur"] or float(s["tenue"]) < 2.0):
				continue
			file.append([m, s])


func _corridor_libre() -> bool:
	## Cherche autour du joueur un point de départ et une direction dont les 40 m devant sont dégagés (rayons à 0,6 et 1,2 m) et ont du sol.
	var espace := root.get_world_3d().direct_space_state
	var j := (current_scene.get_node("Player") as Node3D).global_position
	for rayon: float in [0.0, 10.0, 25.0, 50.0]:
		for k in 8:
			var ang := TAU * k / 8.0
			var base := j + Vector3(cos(ang), 0, sin(ang)) * rayon
			var q3 := PhysicsRayQueryParameters3D.create(base + Vector3(0, 5, 0), base + Vector3(0, -5, 0))
			var s3: Dictionary = espace.intersect_ray(q3)
			if s3.is_empty():
				continue
			var y0: float = (s3.position as Vector3).y
			for k2 in 8:
				var a2 := TAU * k2 / 8.0
				var d := Vector3(cos(a2), 0, sin(a2))
				var ok := true
				for h: float in [0.6, 1.2]:
					var o := Vector3(base.x, y0 + h, base.z)
					var r2 := PhysicsRayQueryParameters3D.create(o, o + d * COULOIR)
					r2.collision_mask = 1
					if not espace.intersect_ray(r2).is_empty():
						ok = false
						break
				if ok:
					depart = Vector3(base.x, y0 + 0.4, base.z)
					dir = Vector2(d.x, d.z)
					avant = d
					return true
	return false


func _progres(n: Node3D) -> float:
	return (n.global_position - depart).dot(avant)


func _suivant() -> void:
	tenir_frein = false
	if v != null:
		var j := current_scene.get_node("Player")
		if j.get("vehicle") != null:
			j.call("exit_vehicle", true)
		Input.action_release("brake")
		Input.action_release("accelerate")
		v.queue_free()
		v = null
	courant += 1
	if courant >= file.size():
		print("RESULTAT gtb_arret_sans_recul : %s" % ("OK" if fails == 0 else "%d ECHEC(S)" % fails))
		quit(1 if fails else 0)
		return
	var m: String = file[courant][0]
	var s: Dictionary = file[courant][1]
	v = Vehicules.create(m, Color.WHITE)
	v.transform = Transform3D(Basis(Vector3.UP, atan2(-dir.x, -dir.y)), depart)
	current_scene.add_child(v)
	if s["joueur"]:
		# le joueur monte vraiment : sinon la couche de commandes du jeu (couches_commandes.gd) relâche « brake » à chaque image
		var joueur := current_scene.get_node("Player")
		joueur.global_position = depart + Vector3(0, 0, 3)
		joueur.call("enter_vehicle", v)
	else:
		v.set("ai", true)
		v.set("ai_input", Vector3.ZERO)
	if m == "zem":
		v.set("speed", V0)
	else:
		v.set("_vel", dir * V0)   # vitesse monde (x, z) : speed = _vel . (-sin lacet, -cos lacet) = V0
	phase = 0
	tp = 0.0
	v_min = 0.0


func _process(d: float) -> bool:
	t += d
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
		attente = t + 20.0     # laisse le monde s'installer
		return false
	if t < attente:
		return false
	if courant < 0:
		if not _corridor_libre():
			print("ECHEC aucun couloir dégagé de %.0f m trouvé autour du joueur" % COULOIR)
			quit(1)
			return true
		print("couloir de départ : %s, direction %s" % [depart, dir])
		_suivant()
		return false
	if v == null:
		return false
	var mod: String = file[courant][0]
	var s: Dictionary = file[courant][1]
	tp += d
	var p := _progres(v)
	tenir_frein = s["joueur"] and phase >= 1 and not (phase == 2 and tp >= float(s["tenue"]))
	match phase:
		0:
			if tp > 0.1:
				if s["joueur"]:
					Input.action_press("brake")
				else:
					v.set("ai_input", Vector3(0, 1, float(s["braq"])))
				phase = 1
				tp = 0.0
		1:
			if absf(float(v.get("speed"))) < 0.3 or tp > 12.0:
				p_arret = p
				phase = 2
				tp = 0.0
		2:
			v_min = minf(v_min, float(v.get("speed")))
			if tp >= float(s["tenue"]):
				if s["joueur"]:
					Input.action_release("brake")
				var recul := p_arret - p
				var a_recule := recul > 0.3 or v_min < -0.3
				var nom := "%s, %s" % [mod, s["nom"]]
				if s["recul"]:
					_check(a_recule, "%s : recule bien (recul %.2f m, vitesse mini %.2f m/s)" % [nom, recul, v_min])
				else:
					_check(not a_recule, "%s : ne recule pas (recul %.2f m, vitesse mini %.2f m/s)" % [nom, recul, v_min])
				_suivant()
	return false
