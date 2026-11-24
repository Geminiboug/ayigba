$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
$p = Start-Process -FilePath $g -ArgumentList @("--headless", "--path", "C:\gtb_local\godot", "--script", "res://tests/test_compile_scripts.gd") -RedirectStandardOutput C:\gtb_local\ay_gtb_compile.txt -RedirectStandardError C:\gtb_local\ay_gtb_compile_err.txt -PassThru
if (-not $p.WaitForExit(180000)) { $p.Kill() }
