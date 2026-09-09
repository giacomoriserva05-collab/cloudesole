# Analisi sintattica dei sorgenti Swift, da Windows.
#
#   powershell -ExecutionPolicy Bypass -File ios-app\tools\check-swift.ps1
#
# Non è una compilazione: `swiftc -parse` legge la grammatica senza risolvere
# gli import, quindi funziona anche dove SwiftUI e WebKit non esistono. Prende
# refusi, parentesi sbagliate e file troncati; non prende errori di tipo, di
# firma delle API o di disponibilità. Per quelli serve il runner macOS
# (.github/workflows/ios-build.yml).
#
# `swiftc -typecheck` qui non funziona: vuole la libreria standard, che sotto
# Windows arriva col Windows SDK di Visual Studio.

$ErrorActionPreference = "Stop"

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

if (-not (Get-Command swiftc -ErrorAction SilentlyContinue)) {
    Write-Host "swiftc non trovato. Installalo con:" -ForegroundColor Yellow
    Write-Host "  winget install --id Swift.Toolchain"
    exit 2
}

$radice = Join-Path $PSScriptRoot "..\CheckoutAutofill" | Resolve-Path
Write-Host "Analisi di $radice`n"

$falliti = 0
foreach ($f in Get-ChildItem -Path $radice -Recurse -Filter *.swift | Sort-Object FullName) {
    $rel = $f.FullName.Substring($radice.Path.Length + 1)
    $out = & swiftc -parse $f.FullName 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ok   $rel" -ForegroundColor DarkGray
    } else {
        Write-Host "  ERR  $rel" -ForegroundColor Red
        ($out -split "`n" | Where-Object { $_ -match "error:" } | Select-Object -First 5) |
            ForEach-Object { Write-Host "       $($_.Trim())" }
        $falliti++
    }
}

Write-Host ""
if ($falliti -eq 0) {
    Write-Host "Sintassi a posto in tutti i file." -ForegroundColor Green
    Write-Host "Restano da verificare tipi e API: quello lo fa il runner macOS."
    exit 0
} else {
    Write-Host "$falliti file con errori di sintassi." -ForegroundColor Red
    exit 1
}
