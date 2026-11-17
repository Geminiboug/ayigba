extends CharacterBody3D
## Bot de vérification : un personnage (capsule) qui suit des routes point par point avec la physique du moteur.
## Il note deux défauts : « bloque » (il n'avance plus : mur invisible ou obstacle sur la route) et « chute » (trou dans le sol).

const VITESSE := 5.0
const DELAI_BLOCAGE := 3.0

var routes: Array = []    # [{ "id": String, "points": PackedVector3Array }]
var echecs: Array = []
var fini := false
var distance := 0.0
var routes_faites := 0

var _r := 0
var _p := 1
var _meilleur := INF
var _depuis := 0.0


func demarrer() -> void:
	_r = -1
	_suivante()


func _suivante() -> void:
	_r += 1
	_p = 1
	_meilleur = INF
	_depuis = 0.0
	velocity = Vector3.ZERO
	if _r >= routes.size():
		fini = true
		return
	global_position = routes[_r]["points"][0] + Vector3(0, 1.0, 0)


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
	if d < 0.6:
		_p += 1
		_meilleur = INF
		_depuis = 0.0
		return
	var dir := vers / d
	velocity.x = dir.x * VITESSE
	velocity.z = dir.z * VITESSE
	velocity.y = -0.5 if is_on_floor() else velocity.y - 9.8 * delta
	var avant := global_position
	move_and_slide()
	distance += Vector2(global_position.x - avant.x, global_position.z - avant.z).length()
	if d < _meilleur - 0.3:
		_meilleur = d
		_depuis = 0.0
	else:
		_depuis += delta
	if global_position.y < -3.0:
		_echec("chute")
	elif _depuis > DELAI_BLOCAGE:
		_echec("bloque")
