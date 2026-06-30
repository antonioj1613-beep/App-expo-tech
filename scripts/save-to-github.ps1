# Guarda cambios locales en GitHub (commit + push)
# Uso: .\scripts\save-to-github.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$remoteUrl = "https://github.com/antonioj1613-beep/App-expo-tech.git"
$branch = "main"

if (-not (Test-Path ".git")) {
    Write-Host "ERROR: No hay repositorio git aquí. Ejecuta primero la configuración inicial." -ForegroundColor Red
    exit 1
}

$origin = git remote get-url origin 2>$null
if (-not $origin) {
    git remote add origin $remoteUrl
}

git add -A
$status = git status --porcelain
if (-not $status) {
    Write-Host "Sin cambios que guardar ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))." -ForegroundColor Yellow
    exit 0
}

$msg = "Guardado automático $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git commit -m $msg
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: No se pudo crear el commit." -ForegroundColor Red
    exit 1
}

git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: No se pudo subir a GitHub. Comprueba tu sesión de Git (credenciales o SSH)." -ForegroundColor Red
    exit 1
}

Write-Host "Cambios guardados en GitHub: $msg" -ForegroundColor Green
