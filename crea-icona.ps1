# Crea (o aggiorna) il collegamento "Restock Monitor" sul desktop.
#   powershell -ExecutionPolicy Bypass -File crea-icona.ps1
#   powershell -ExecutionPolicy Bypass -File crea-icona.ps1 -Rimuovi

param(
    [switch]$Rimuovi
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

# GetFolderPath tiene conto del desktop spostato su OneDrive.
$desktop = [Environment]::GetFolderPath('Desktop')
$collegamento = Join-Path $desktop 'Restock Monitor.lnk'

if ($Rimuovi) {
    if (Test-Path $collegamento) {
        Remove-Item $collegamento -Force
        Write-Host "Collegamento rimosso." -ForegroundColor Green
    } else {
        Write-Host "Nessun collegamento da rimuovere."
    }
    exit 0
}

# --- Interprete -------------------------------------------------------------
# pythonw.exe (non python.exe) apre la finestra senza console nera dietro.
$pythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Host "Ambiente non inizializzato: manca $pythonw" -ForegroundColor Red
    Write-Host "Esegui prima:  powershell -ExecutionPolicy Bypass -File setup.ps1"
    exit 1
}

# --- Icona ------------------------------------------------------------------
$icona = Join-Path $PSScriptRoot 'restock.ico'
if (-not (Test-Path $icona)) {
    Write-Host "Icona mancante, la genero..."
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'makeicon.py')
    if (-not (Test-Path $icona)) {
        Write-Host "Generazione dell'icona fallita." -ForegroundColor Red
        exit 1
    }
}

# --- Configurazione ---------------------------------------------------------
if (-not (Test-Path (Join-Path $PSScriptRoot 'config.yaml'))) {
    Copy-Item (Join-Path $PSScriptRoot 'config.example.yaml') (Join-Path $PSScriptRoot 'config.yaml')
    Write-Host "Creato config.yaml dal template." -ForegroundColor Yellow
}

# --- Collegamento -----------------------------------------------------------
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($collegamento)
$link.TargetPath = $pythonw
$link.Arguments = '-m restock.gui'
$link.WorkingDirectory = $PSScriptRoot
$link.IconLocation = "$icona,0"
$link.Description = 'Monitor di disponibilita per store online'
$link.WindowStyle = 1
$link.Save()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null

if (Test-Path $collegamento) {
    Write-Host ""
    Write-Host "Collegamento creato:" -ForegroundColor Green
    Write-Host "  $collegamento"
    Write-Host ""
    Write-Host "Doppio clic sull'icona 'Restock Monitor' sul desktop per avviare il programma."
} else {
    Write-Host "Creazione del collegamento fallita." -ForegroundColor Red
    exit 1
}
