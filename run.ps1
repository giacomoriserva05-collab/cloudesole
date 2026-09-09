# Avvia il Restock Monitor usando l'interprete del venv.
# Tutti gli argomenti vengono passati al programma:
#   .\run.ps1 --once
#   .\run.ps1 --test-notify
#   .\run.ps1 -c altra-config.yaml -v

Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "Ambiente non inizializzato. Esegui prima:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File setup.ps1"
    exit 1
}

if (-not (Test-Path 'config.yaml')) {
    Write-Host "config.yaml mancante. Copialo dal template:" -ForegroundColor Red
    Write-Host "  Copy-Item config.example.yaml config.yaml"
    exit 1
}

& $venvPython -m restock @args
exit $LASTEXITCODE
