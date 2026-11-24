$g = "C:\Users\La Paix Technology\Desktop\Godot_v4.7.2-stable_win64.exe"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\gtb_local\sync.ps1" | Out-Null
Remove-Item C:\gtb_local\ay_gtb_circ_fin.txt -ErrorAction SilentlyContinue
$env:GTB_DEMO = "1"
$env:BANC_DUREE = "300"
$env:BANC_DETAIL = "1"
$i = 0
foreach ($pos in @(@("", ""), @("620", "70"))) {
    $i++
    if ($pos[0] -ne "") { $env:BANC_X = $pos[0]; $env:BANC_Z = $pos[1] } else { Remove-Item Env:BANC_X -ErrorAction SilentlyContinue; Remove-Item Env:BANC_Z -ErrorAction SilentlyContinue }
    $p = Start-Process -FilePath $g -ArgumentList @("--headless", "--path", "C:\gtb_local\godot", "--script", "res://tests/banc_circulation.gd") -RedirectStandardOutput "C:\gtb_local\ay_gtb_circ_$i.txt" -RedirectStandardError "C:\gtb_local\ay_gtb_circ_err_$i.txt" -PassThru
    if (-not $p.WaitForExit(900000)) { $p.Kill() }
}
"FINI" | Out-File C:\gtb_local\ay_gtb_circ_fin.txt
