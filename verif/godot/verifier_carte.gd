extends SceneTree
## Vérifie qu'une carte ayigba (carte.glb) s'ouvre dans Godot et que son sol n'a pas de trou.
##   Godot --headless --path verif/godot --script res://verifier_carte.gd -- carte=<chemin de carte.glb>
##   Godot --path verif/godot --resolution 1600x900 --script res://verifier_carte.gd -- carte=<...> captures=<dossier>
## Contrôles : chargement glTF sans erreur ; collisions créées pour chaque couche sauf « eau » ; un rayon tiré vers le bas
## tous les PAS mètres doit toujours toucher un sol. Code de sortie 0 si tout va bien, 1 sinon.

const PAS := 15.0
const SANS_COLLISION := ["eau"]

var echecs := 0


func _note(ok: bool, texte: String) -> void:
	print(("OK    " if ok else "ECHEC ") + texte)
	if not ok:
		echecs += 1


func _arg(nom: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return ""


func _initialize() -> void:
	_verifier.call_deferred()


func _verifier() -> void:
	var chemin := _arg("carte")
	if chemin == "" or not FileAccess.file_exists(chemin):
		_note(false, "fichier de carte introuvable : « %s »" % chemin)
		_finir()
		return
	var doc := GLTFDocument.new()
	var etat := GLTFState.new()
	var err := doc.append_from_file(chemin, etat)
	_note(err == OK, "lecture du glTF (code %d)" % err)
	if err != OK:
		_finir()
		return
	var scene := doc.generate_scene(etat)
	_note(scene != null, "scène générée")
	if scene == null:
		_finir()
		return
	root.add_child(scene)

	var boite := AABB()
	var premier := true
	var triangles := 0
	var couches: Array[String] = []
	for n in scene.find_children("*", "MeshInstance3D", true, false):
		var mi := n as MeshInstance3D
		couches.append(String(mi.name))
		for s in mi.mesh.get_surface_count():
			var tab := mi.mesh.surface_get_arrays(s)
			var idx = tab[Mesh.ARRAY_INDEX]
			triangles += (idx.size() if idx != null and idx.size() > 0 else (tab[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()) / 3
		var b := mi.global_transform * mi.get_aabb()
		boite = b if premier else boite.merge(b)
		premier = false
		if not SANS_COLLISION.has(String(mi.name)):
			var corps := StaticBody3D.new()
			var forme := CollisionShape3D.new()
			forme.shape = mi.mesh.create_trimesh_shape()
			corps.add_child(forme)
			mi.add_child(corps)
	_note(couches.size() > 0, "%d couche(s) : %s" % [couches.size(), ", ".join(couches)])
	_note(triangles > 0, "%d triangles" % triangles)
	print("      emprise : %.0f m (est-ouest) x %.0f m (nord-sud), hauteur de %.1f à %.1f m" % [boite.size.x, boite.size.z, boite.position.y, boite.end.y])

	await physics_frame
	await physics_frame
	var espace := root.get_world_3d().direct_space_state
	var rayons := 0
	var trous := 0
	var exemples: Array[String] = []
	var x := boite.position.x + PAS * 0.5
	while x < boite.end.x:
		var z := boite.position.z + PAS * 0.5
		while z < boite.end.z:
			rayons += 1
			# un rayon qui tombe pile sur une arête entre deux triangles peut passer au travers : on ne compte un trou
			# que si des rayons décalés de quelques centimètres manquent aussi
			var touche := false
			for decal in [Vector2.ZERO, Vector2(0.07, 0.03), Vector2(-0.05, 0.08), Vector2(0.04, -0.09)]:
				var q := PhysicsRayQueryParameters3D.create(Vector3(x + decal.x, boite.end.y + 50.0, z + decal.y), Vector3(x + decal.x, boite.position.y - 50.0, z + decal.y))
				if not espace.intersect_ray(q).is_empty():
					touche = true
					break
			if not touche:
				trous += 1
				if exemples.size() < 5:
					exemples.append("(%.0f, %.0f)" % [x, z])
			z += PAS
		x += PAS
	_note(trous == 0, "sol sans trou : %d rayon(s) sur %d ne touchent rien %s" % [trous, rayons, " ".join(exemples)])

	var dossier := _arg("captures")
	if dossier != "" and DisplayServer.get_name() != "headless":
		await _capturer(dossier, boite)
	_finir()


func _capturer(dossier: String, boite: AABB) -> void:
	DirAccess.make_dir_recursive_absolute(dossier)
	var soleil := DirectionalLight3D.new()
	soleil.rotation_degrees = Vector3(-52, 35, 0)
	soleil.shadow_enabled = true
	soleil.directional_shadow_max_distance = 600.0
	root.add_child(soleil)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.74, 0.86)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.75, 0.78, 0.85)
	env.environment.ambient_light_energy = 0.35
	env.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	root.add_child(env)
	var cam := Camera3D.new()
	cam.far = 12000.0
	root.add_child(cam)
	cam.make_current()
	var centre := boite.get_center()
	var vues := {
		"vue_ensemble": [centre + Vector3(0, boite.size.z * 0.55, boite.size.z * 0.75), centre],
		"vue_quartier": [centre + Vector3(-boite.size.x * 0.18, 140, boite.size.z * 0.02), centre + Vector3(-boite.size.x * 0.28, 0, -boite.size.z * 0.12)],
		"vue_rue": [centre + Vector3(boite.size.x * 0.2, 35, boite.size.z * 0.1), centre + Vector3(boite.size.x * 0.3, 0, -boite.size.z * 0.02)],
	}
	for nom in vues:
		cam.global_position = vues[nom][0]
		cam.look_at(vues[nom][1], Vector3.UP)
		for i in 6:
			await process_frame
		var image := root.get_viewport().get_texture().get_image()
		var fichier := dossier.path_join(nom + ".png")
		_note(image.save_png(fichier) == OK, "capture " + fichier)


func _finir() -> void:
	print("RESULTAT verifier_carte : %s" % ("OK" if echecs == 0 else "%d ECHEC(S)" % echecs))
	quit(0 if echecs == 0 else 1)
