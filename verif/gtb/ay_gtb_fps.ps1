$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_fps.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    $env:GTB_DEMO = "1"
    $env:VUES = "aerogare:378:-378:0:0:12:1.7;ararat:620:70:0:0:12:1.7;plage:399:348:0:0:12:1.7"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "1280x720", "--script", "res://tests/bench_fps.gd") -RedirectStandardOutput C:\gtb_local\ay_gtb_fps.txt -RedirectStandardError C:\gtb_local\ay_gtb_fps_err.txt -PassThru
    if (-not $p.WaitForExit(600000)) { $p.Kill() }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
