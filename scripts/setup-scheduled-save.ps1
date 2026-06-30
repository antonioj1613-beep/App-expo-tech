# Programa guardado automático en GitHub: lunes–viernes a las 17:00 (hora local)
# Ejecutar una vez como administrador si Windows lo pide:
#   .\scripts\setup-scheduled-save.ps1
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$saveScript = Join-Path $projectRoot "scripts\save-to-github.ps1"
$taskName = "App-expo-tech-GitHub-17h"

if (-not (Test-Path $saveScript)) {
    Write-Host "ERROR: No se encuentra $saveScript" -ForegroundColor Red
    exit 1
}

# Lunes–viernes a las 17:00, hora local del equipo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "17:00"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$saveScript`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Settings $settings -Force | Out-Null

Write-Host ""
Write-Host "Tarea programada creada: $taskName" -ForegroundColor Green
Write-Host "  Cuándo: lunes a viernes a las 17:00 (hora local)" -ForegroundColor White
Write-Host "  Qué hace: commit + push a https://github.com/antonioj1613-beep/App-expo-tech" -ForegroundColor White
Write-Host ""
Write-Host "Para probar ahora:" -ForegroundColor Cyan
Write-Host "  .\scripts\save-to-github.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Para quitar la tarea:" -ForegroundColor Cyan
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor White
