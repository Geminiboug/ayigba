$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_toits.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    Copy-Item "\\wsl.localhost\Ubuntu\home\olympe\ayigba\verif\godot\gtb\gtb_toits.gd" "C:\gtb_local\ay_gtb_toits.gd" -Force
    Remove-Item C:\gtb_local\gtb_toits.json -ErrorAction SilentlyContinue
    $env:GTB_DEMO = "1"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "960x540", "--script", "C:/gtb_local/ay_gtb_toits.gd", "--", "C:/gtb_local/gtb_toits.json", "0.1") -RedirectStandardOutput C:\gtb_local\ay_gtb_toits.txt -RedirectStandardError C:\gtb_local\ay_gtb_toits_err.txt -PassThru
    if (-not $p.WaitForExit(420000)) { $p.Kill() }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
