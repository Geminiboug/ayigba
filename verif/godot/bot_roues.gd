extends VehicleBody3D
## Bot à roues : un vrai véhicule (châssis, 4 roues avec suspension, direction aux roues avant, moteur aux roues arrière)
## qui suit des routes point par point avec la physique du moteur. Même interface que bot.gd (routes, echecs, fini...).
## Il révèle ce que la capsule ne voit pas : bosses et marches de la chaussée, pentes trop raides, virages trop serrés,
## passages plus étroits que le châssis. Défauts notés : « bloque » (n'avance plus, ou renversé) et « chute » (trou).

var vitesse := 4.0           # m/s visés
const DELAI_BLOCAGE := 5.0     # un véhicule met plus de temps à repartir qu'un piéton
const BRAQUAGE_MAX := 0.6      # radians
const FORCE_MAX := 3500.0
const SENS_MOTEUR := -1.0       # signe de la force moteur pour avancer vers -Z du châssis : réglé par essai
const LARGEUR := 1.8
const LONGUEUR := 4.0

var routes: Array = []
var tolerance := 2.0
var echecs: Array = []
var fini := false
var distance := 0.0
var routes_faites := 0
var renverses := 0

var _r := 0
var _p := 1
var _meilleur := INF
var _depuis := 0.0
var _libre := 0.0


func monter() -> void:
	var v := self
	v.mass = 1100.0
	var forme := CollisionShape3D.new()
	var boite := BoxShape3D.new()
	boite.size = Vector3(LARGEUR, 0.7, LONGUEUR)
	forme.shape = boite
	forme.position.y = 0.55
	v.add_child(forme)
	for av in [true, false]:
		for cote in [-1.0, 1.0]:
			var roue := VehicleWheel3D.new()
			roue.wheel_radius = 0.35
			roue.wheel_rest_length = 0.12
			roue.suspension_travel = 0.25
			roue.suspension_stiffness = 45.0
			roue.suspension_max_force = 8000.0
			roue.wheel_friction_slip = 3.0
			roue.use_as_steering = av
			roue.use_as_traction = not av
			roue.position = Vector3(cote * (LARGEUR * 0.5 - 0.15), 0.35, (-1.0 if av else 1.0) * (LONGUEUR * 0.5 - 0.6))
			v.add_child(roue)


func demarrer() -> void:
	_r = -1
	_suivante()


func _suivante() -> void:
	_r += 1
	_p = 1
	_meilleur = INF
	_depuis = 0.0
	engine_force = 0.0
	steering = 0.0
	linear_velocity = Vector3.ZERO
	angular_velocity = Vector3.ZERO
	if _r >= routes.size():
		fini = true
		freeze = true
		return
	var pts: PackedVector3Array = routes[_r]["points"]
	var cap := Vector3(pts[1].x - pts[0].x, 0.0, pts[1].z - pts[0].z)
	var depart := pts[0] + Vector3(0, 0.9, 0)
	if cap.length() < 0.01:
		cap = Vector3(0, 0, -1)
	var b := Basis.looking_at(cap.normalized(), Vector3.UP)   # -Z du châssis vers le premier point
	global_transform = Transform3D(b, depart)


func _echec(genre: String) -> void:
	echecs.append({"genre": genre, "route": routes[_r]["id"], "x": snappedf(global_position.x, 0.1), "y": snappedf(global_position.y, 0.1), "z": snappedf(global_position.z, 0.1)})
	_suivante()


func _physics_process(delta: float) -> void:
	if fini or routes.is_empty() or _r < 0:
		return
	var pts: PackedVector3Array = routes[_r]["points"]
	if _p >= pts.size():
		routes_faites += 1
		_suivante()
		return
	var vers := Vector3(pts[_p].x - global_position.x, 0.0, pts[_p].z - global_position.z)
	var d := vers.length()
	if d < tolerance:
		_p += 1
		_meilleur = INF
		_depuis = 0.0
		return
	var avant := -global_transform.basis.z
	avant.y = 0.0
	avant = avant.normalized()
	var angle := avant.signed_angle_to(vers.normalized(), Vector3.UP)   # positif : le point est à gauche
	steering = clampf(angle, -BRAQUAGE_MAX, BRAQUAGE_MAX)
	var v := linear_velocity.dot(avant)
	var cible := vitesse * (0.4 if absf(angle) > 0.6 else 1.0)
	engine_force = SENS_MOTEUR * clampf((cible - v) * 1800.0, -FORCE_MAX, FORCE_MAX)
	var fait := Vector2(linear_velocity.x, linear_velocity.z).length() * delta
	distance += fait
	if d < _meilleur - 0.3:
		_meilleur = d
		_depuis = 0.0
	else:
		_depuis += delta
	if global_position.y < -3.0:
		_echec("chute")
	elif global_transform.basis.y.y < 0.25:   # renversé
		renverses += 1
		_echec("renverse")
	elif _depuis > DELAI_BLOCAGE:
		_echec("bloque")
