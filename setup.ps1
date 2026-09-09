# Setup del Restock Monitor: verifica Python, crea il venv, installa le dipendenze.
# Uso:  powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host "=== Setup Restock Monitor ===" -ForegroundColor Cyan

# --- 1. Python -------------------------------------------------------------
$MinPython = [Version]'3.10'

function Get-PythonVersion {
    # Unico test affidabile: si chiede all'eseguibile la propria versione.
    # Lo stub dello Store fallisce, il Python Manager (che vive anch'esso in
    # WindowsApps) risponde correttamente: filtrare per percorso li' confonderebbe.
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }

    $global:LASTEXITCODE = 0
    try {
        $raw = & $Path -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }

    try { return [Version]($raw | Select-Object -First 1).Trim() } catch { return $null }
}

function Get-RealPython {
    $candidates = @()
    $commands = Get-Command python, python3, py -ErrorAction SilentlyContinue
    foreach ($c in $commands) { $candidates += $c.Source }

    # Percorsi di installazione tipici, nel caso il PATH non sia aggiornato.
    $globs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe",
        "C:\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        $hits = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
        foreach ($h in $hits) { $candidates += $h }
    }

    $tooOld = @()
    foreach ($c in ($candidates | Select-Object -Unique)) {
        $version = Get-PythonVersion $c
        if (-not $version) { continue }
        if ($version -lt $MinPython) { $tooOld += "$c ($version)"; continue }
        return [PSCustomObject]@{ Path = $c; Version = $version }
    }

    foreach ($old in $tooOld) {
        Write-Host "Ignorato, versione troppo vecchia: $old" -ForegroundColor DarkYellow
    }
    return $null
}

$python = Get-RealPython

if (-not $python) {
    Write-Host "Python $MinPython+ non trovato. Provo a installarlo con winget..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "winget non disponibile." -ForegroundColor Red
        Write-Host "Installa Python 3.11+ da https://www.python.org/downloads/ e rilancia questo script."
        Write-Host "Durante l'installazione spunta 'Add python.exe to PATH'."
        exit 1
    }

    winget install --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installazione di Python fallita (exit $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }

    # Ricarica il PATH nella sessione corrente, altrimenti python resta invisibile.
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $python = Get-RealPython

    if (-not $python) {
        Write-Host "Python installato ma non ancora nel PATH." -ForegroundColor Yellow
        Write-Host "Chiudi e riapri il terminale, poi rilancia setup.ps1."
        exit 1
    }
}

Write-Host "Python $($python.Version): $($python.Path)" -ForegroundColor Green

# --- 2. Ambiente virtuale --------------------------------------------------
if (-not (Test-Path '.venv')) {
    Write-Host "Creo l'ambiente virtuale in .venv ..."
    & $python.Path -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "Creazione venv fallita." -ForegroundColor Red; exit 1 }
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "Interprete del venv non trovato in $venvPython" -ForegroundColor Red
    exit 1
}

# --- 3. Dipendenze ---------------------------------------------------------
Write-Host "Installo le dipendenze ..."
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "Installazione dipendenze fallita." -ForegroundColor Red; exit 1 }

# --- 4. Configurazione -----------------------------------------------------
if (-not (Test-Path 'config.yaml')) {
    Copy-Item 'config.example.yaml' 'config.yaml'
    Write-Host "Creato config.yaml dal template." -ForegroundColor Green
    $configIsNew = $true
} else {
    Write-Host "config.yaml gia' presente: lasciato invariato." -ForegroundColor Green
    $configIsNew = $false
}

Write-Host ""
Write-Host "=== Setup completato ===" -ForegroundColor Cyan
if ($configIsNew) {
    Write-Host "1. Apri config.yaml e sostituisci i target di esempio con i tuoi." -ForegroundColor Yellow
}
Write-Host "2. Icona sul desktop:    powershell -ExecutionPolicy Bypass -File crea-icona.ps1"
Write-Host "3. Avvia l'interfaccia:  .\gui.ps1"
Write-Host ""
Write-Host "Da riga di comando:"
Write-Host "   verifica la config:   .\run.ps1 --once"
Write-Host "   prova le notifiche:   .\run.ps1 --test-notify"
Write-Host "   monitoraggio:         .\run.ps1"
