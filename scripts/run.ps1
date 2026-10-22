[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [int]$Port = 7860
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = Join-Path $Root ".venv-cpp\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "KittenTTS Local no esta instalado todavia." -ForegroundColor Yellow
    Write-Host "Ejecuta setup.bat primero."
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}

$env:PYTHONUTF8 = "1"
$env:GRADIO_ANALYTICS_ENABLED = "False"
$appArgs = @("app.py", "--port", "$Port")
if ($NoBrowser) {
    $appArgs += "--no-browser"
}

try {
    & $python @appArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "La aplicacion termino con codigo $LASTEXITCODE." -ForegroundColor Red
        Write-Host "Revisa logs\app.log y logs\engine.log."
        Read-Host "Pulsa Enter para cerrar"
    }
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Revisa logs\app.log."
    Read-Host "Pulsa Enter para cerrar"
    exit 1
}
