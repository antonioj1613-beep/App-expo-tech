# Read the SQLite database (prints to terminal + updates database_snapshot.txt)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python manage.py showdb --export database_snapshot.txt
