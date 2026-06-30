# Learning Skills - one command to start everything
# Usage:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ and make sure 'python' is on your PATH." -ForegroundColor Red
    exit 1
}

function Write-Step($msg) {
    Write-Host ""
    Write-Host ">> $msg" -ForegroundColor Cyan
}

Write-Step "Checking dependencies..."
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
    exit 1
}

Write-Step "Applying database migrations..."
python manage.py migrate --noinput | Out-Null

Write-Step "Seeding lesson catalogs..."
python manage.py seed_skills | Out-Null
python manage.py seed_reading | Out-Null

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Learning Skills is starting" -ForegroundColor Green
Write-Host "  http://127.0.0.1:8000/" -ForegroundColor White
Write-Host "  Speaking: /speaking/ (voice practice in Chrome/Edge)" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

python manage.py runserver 127.0.0.1:8000
