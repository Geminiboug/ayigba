extends SceneTree
## Capture d'une zone glb vue de 3/4 : Godot --path ay_verif --script res://photo_zone.gd -- glb=<fichier> sortie=<png> [x=..] [z=..]

func _arg(nom: String, defaut: String = "") -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(nom + "="):
			return a.substr(nom.length() + 1)
	return defaut


func _initialize() -> void:
	_lancer.call_deferred()


func _lancer() -> void:
	root.size = Vector2i(1400, 800)
	var doc := GLTFDocument.new()
	var etat := GLTFState.new()
	var err := doc.append_from_file(_arg("glb"), etat)
	if err != OK:
		print("ECHEC lecture glb ", err)
		quit(1)
		return
	var scene := doc.generate_scene(etat)
	root.add_child(scene)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.74, 0.88)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.75, 0.78, 0.85)
	env.environment.ambient_light_energy = 0.7
	root.add_child(env)
	var soleil := DirectionalLight3D.new()
	soleil.rotation_degrees = Vector3(-50, -35, 0)
	soleil.light_energy = 1.1
	root.add_child(soleil)
	var cam := Camera3D.new()
	root.add_child(cam)
	var x := float(_arg("x", "0"))
	var z := float(_arg("z", "0"))
	cam.global_position = Vector3(x + 60, 38, z + 60)
	cam.look_at(Vector3(x, 0, z))
	cam.fov = 55
	cam.current = true
	for i in 12:
		await process_frame
	var img := root.get_texture().get_image()
	img.save_png(_arg("sortie"))
	print("OK capture ", _arg("sortie"), " ", img.get_size())
	quit(0)
