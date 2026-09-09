# Fa partire il monitor da solo all'accesso a Windows, senza aprire la finestra.
#
#   powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1
#   powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Rimuovi
#   powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Stato
#
# Non serve essere amministratore: l'operazione pianificata e' registrata per
# l'utente corrente e parte quando accedi.

param(
    [switch]$Rimuovi,
    [switch]$Stato
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$nome = 'Restock Monitor'

if ($Stato) {
    $op = Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue
    if (-not $op) {
        Write-Host "Avvio automatico: NON configurato."
        exit 0
    }
    $info = Get-ScheduledTaskInfo -TaskName $nome
    Write-Host "Avvio automatico: configurato"
    Write-Host "  stato            : $($op.State)"
    Write-Host "  ultimo avvio     : $($info.LastRunTime)"
    Write-Host "  esito ultimo giro: $($info.LastTaskResult)"
    Write-Host "  prossimo avvio   : $($info.NextRunTime)"
    exit 0
}

if ($Rimuovi) {
    if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $nome -Confirm:$false
        Write-Host "Avvio automatico rimosso." -ForegroundColor Green
    } else {
        Write-Host "Non c'era nessun avvio automatico da rimuovere."
    }
    exit 0
}

# --- Controlli preliminari --------------------------------------------------
$pythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Host "Ambiente non inizializzato. Esegui prima:" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File setup.ps1"
    exit 1
}
if (-not (Test-Path (Join-Path $PSScriptRoot 'config.yaml'))) {
    Write-Host "config.yaml mancante." -ForegroundColor Red
    exit 1
}

# --- Registrazione ----------------------------------------------------------
# pythonw non apre nessuna finestra: il monitor gira in silenzio e scrive tutto
# in monitor.log. L'avvio e' ritardato di un minuto perche' all'accesso la rete
# spesso non e' ancora pronta e il primo giro fallirebbe.
$azione = New-ScheduledTaskAction -Execute $pythonw `
    -Argument '-m restock -c config.yaml' `
    -WorkingDirectory $PSScriptRoot

$innesco = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$innesco.Delay = 'PT1M'

$condizioni = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -RestartCount 5 `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$principale = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $nome -Confirm:$false
}

Register-ScheduledTask -TaskName $nome `
    -Action $azione -Trigger $innesco -Settings $condizioni -Principal $principale `
    -Description 'Monitor di disponibilita: parte da solo a ogni accesso.' | Out-Null

Write-Host ""
Write-Host "Avvio automatico configurato." -ForegroundColor Green
Write-Host "  Il monitor parte da solo un minuto dopo ogni accesso a Windows."
Write-Host "  Gira senza finestra; il registro e' in monitor.log."
Write-Host "  Se si interrompe, viene riavviato fino a 5 volte a distanza di 2 minuti."
Write-Host ""
Write-Host "  Stato:    powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Stato"
Write-Host "  Rimuovi:  powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Rimuovi"
Write-Host ""
Write-Host "Nella finestra grafica NON premere Avvia: il monitor gira gia'." -ForegroundColor Yellow
Write-Host "Se lo fai, viene rifiutato con un messaggio invece di partire due volte."
