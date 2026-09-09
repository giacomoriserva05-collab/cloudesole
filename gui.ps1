# Avvia l'interfaccia grafica del Restock Monitor.
# Usa pythonw.exe, quindi non resta aperta nessuna finestra di console.
#   .\gui.ps1
#   .\gui.ps1 altra-config.yaml

Set-Location -Path $PSScriptRoot

$venvPythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $venvPythonw)) {
    Write-Host "Ambiente non inizializzato. Esegui prima:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File setup.ps1"
    exit 1
}

if (-not (Test-Path 'config.yaml')) {
    Copy-Item 'config.example.yaml' 'config.yaml'
    Write-Host "Creato config.yaml dal template." -ForegroundColor Green
}

Start-Process -FilePath $venvPythonw -ArgumentList (@('-m', 'restock.gui') + $args) -WorkingDirectory $PSScriptRoot
