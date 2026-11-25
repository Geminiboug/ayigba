$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_arret.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    Copy-Item "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\gtb_arret_sans_recul.gd" "C:\gtb_local\ay_gtb_arret.gd" -Force
    $env:GTB_DEMO = "1"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "640x360", "--script", "C:/gtb_local/ay_gtb_arret.gd") -RedirectStandardOutput C:\gtb_local\ay_gtb_arret.txt -RedirectStandardError C:\gtb_local\ay_gtb_arret_err.txt -PassThru
    if (-not $p.WaitForExit(600000)) { $p.Kill() }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
