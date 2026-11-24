$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_pietons.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    Copy-Item "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\gtb_pietons.gd" "C:\gtb_local\ay_gtb_pietons.gd" -Force
    Remove-Item C:\gtb_local\gtb_pietons.json -ErrorAction SilentlyContinue
    Copy-Item "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\base_pietons.json" C:\gtb_local\ay_gtb_base_pietons.json -Force
    Remove-Item C:\gtb_local\ay_gtb_pietons_fin.txt -ErrorAction SilentlyContinue
    $env:GTB_DEMO = "1"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "960x540", "--script", "C:/gtb_local/ay_gtb_pietons.gd", "--", "C:/gtb_local/gtb_pietons.json", "4", "12", "C:/gtb_local/ay_gtb_base_pietons.json") -RedirectStandardOutput C:\gtb_local\ay_gtb_pietons.txt -RedirectStandardError C:\gtb_local\ay_gtb_pietons_err.txt -PassThru
    if (-not $p.WaitForExit(500000)) { $p.Kill(); "DELAI DEPASSE" | Out-File C:\gtb_local\ay_gtb_pietons_fin.txt }
    else { "FINI" | Out-File C:\gtb_local\ay_gtb_pietons_fin.txt }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
