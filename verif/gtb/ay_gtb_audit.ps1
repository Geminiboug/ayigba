$verrou = "C:\gtb_local\verrou_fenetre"
$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
try {
    New-Item -ItemType Directory $verrou -ErrorAction Stop | Out-Null
} catch {
    "VERROU OCCUPE" | Out-File C:\gtb_local\ay_gtb_audit.txt
    exit 3
}
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
    Remove-Item C:\gtb_local\ay_audit_chaussee.csv -ErrorAction SilentlyContinue
    Remove-Item C:\gtb_local\ay_gtb_audit_fin.txt -ErrorAction SilentlyContinue
    $env:GTB_DEMO = "1"
    $env:AUDIT_PAS = "600"
    $env:AUDIT_ATTENTE = "8"
    $env:AUDIT_SORTIE = "C:/gtb_local/ay_audit_chaussee.csv"
    $p = Start-Process -FilePath $g -ArgumentList @("--path", "C:\gtb_local\godot", "--resolution", "1280x720", "--script", "res://tests/audit_chaussee.gd") -RedirectStandardOutput C:\gtb_local\ay_gtb_audit.txt -RedirectStandardError C:\gtb_local\ay_gtb_audit_err.txt -PassThru
    if (-not $p.WaitForExit(1200000)) { $p.Kill(); "DELAI DEPASSE" | Out-File C:\gtb_local\ay_gtb_audit_fin.txt }
    else { "FINI" | Out-File C:\gtb_local\ay_gtb_audit_fin.txt }
} finally {
    Remove-Item $verrou -Recurse -Force -ErrorAction SilentlyContinue
}
