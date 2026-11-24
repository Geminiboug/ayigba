$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_scan.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    Copy-Item "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\gtb_flottants.gd" "C:\gtb_local\ay_gtb_flottants.gd" -Force
    Remove-Item C:\gtb_local\gtb_flottants.json -ErrorAction SilentlyContinue
    $base = "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\base_flottants.json"
    if ((Test-Path $base) -and -not (Test-Path C:\gtb_local\ay_sans_base.flag)) { Copy-Item $base C:\gtb_local\ay_gtb_base.json -Force } else { Remove-Item C:\gtb_local\ay_gtb_base.json -ErrorAction SilentlyContinue }
    $env:GTB_DEMO = "1"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "960x540", "--script", "C:/gtb_local/ay_gtb_flottants.gd", "--", "C:/gtb_local/gtb_flottants.json", "0.3", "C:/gtb_local/ay_gtb_base.json") -RedirectStandardOutput C:\gtb_local\ay_gtb_scan.txt -RedirectStandardError C:\gtb_local\ay_gtb_scan_err.txt -PassThru
    if (-not $p.WaitForExit(420000)) { $p.Kill(); "DELAI DEPASSE" | Out-File C:\gtb_local\ay_gtb_scan_fin.txt }
    else { "FINI code $($p.ExitCode)" | Out-File C:\gtb_local\ay_gtb_scan_fin.txt }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
