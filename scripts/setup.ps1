<#
Instalador de KittenTTS Local para Windows 10/11.
Se puede ejecutar con doble clic en setup.bat o manualmente:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$RuntimeOnly,
    [switch]$SkipAssets,
    [switch]$NoShortcut,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$AssetProfile = if ($RuntimeOnly) { "runtime" } else { "full" }
$CpuIndex = "https://download.pytorch.org/whl/cpu"
$PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    # PowerShell moderno ya negocia TLS correctamente.
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "assets") | Out-Null
$transcriptStarted = $false
try {
    Start-Transcript -Path (Join-Path $Root "logs\setup.log") -Append | Out-Null
    $transcriptStarted = $true
} catch {
    # El log de Python sigue disponible aunque la transcripcion falle.
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-PythonInfo {
    param(
        [string]$Exe,
        [string[]]$Prefix = @()
    )
    try {
        $code = "import sys,struct,json; print(json.dumps({'exe':sys.executable,'version':list(sys.version_info[:3]),'bits':struct.calcsize('P')*8,'abiflags':getattr(sys,'abiflags','')}))"
        $raw = & $Exe @Prefix -c $code 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
        $line = @($raw)[-1]
        $info = $line | ConvertFrom-Json
        if (-not $info.exe) { return $null }
        if ($info.exe -match "WindowsApps") { return $null }
        if ([int]$info.bits -ne 64) { return $null }
        if ([string]$info.abiflags -match "t") { return $null }
        $version = [version](@($info.version) -join ".")
        if ($version -lt [version]"3.10" -or $version -ge [version]"3.15") { return $null }
        return [pscustomobject]@{
            Exe = [string]$info.exe
            Version = $version
            Bits = [int]$info.bits
            Label = "$Exe $($Prefix -join ' ')".Trim()
        }
    } catch {
        return $null
    }
}

function Find-CompatiblePython {
    $candidates = @(
        @{ Name = "py"; Prefix = @("-3.12") },
        @{ Name = "py"; Prefix = @("-3.13") },
        @{ Name = "py"; Prefix = @("-3.14") },
        @{ Name = "py"; Prefix = @("-3.11") },
        @{ Name = "py"; Prefix = @("-3.10") },
        @{ Name = "python"; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        if ($command.Source -and $command.Source -match "WindowsApps") { continue }
        $info = Get-PythonInfo -Exe $candidate.Name -Prefix $candidate.Prefix
        if ($info) {
            Write-Host "Python compatible: $($info.Exe) ($($info.Version), 64 bits)"
            return $info
        }
    }
    return $null
}

function Install-Python {
    Write-Step "No se encontro un Python compatible (3.10-3.14, 64 bits)"
    Write-Host "Puedes instalar Python 3.12 x64 automaticamente para tu usuario."
    $answer = Read-Host "Continuar con la instalacion? (S/N)"
    if ($answer -notmatch "^(s|si|y|yes)$") {
        throw "Instala Python 3.12 x64 desde $PythonUrl y vuelve a ejecutar setup.bat"
    }

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Probando instalacion con winget"
        & winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements
        Start-Sleep -Seconds 5
        $found = Find-CompatiblePython
        if ($found) { return $found }
        Write-Host "winget no dejo un Python utilizable; se usara el instalador oficial." -ForegroundColor Yellow
    }

    $installer = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    Write-Step "Descargando Python 3.12 x64"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $installer -UseBasicParsing
    Write-Step "Instalando Python 3.12 x64 para el usuario actual"
    $process = Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1" -Wait -PassThru
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    if ($process.ExitCode -ne 0) {
        throw "El instalador de Python termino con codigo $($process.ExitCode)"
    }

    $known = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $known) {
        $info = Get-PythonInfo -Exe $known
        if ($info) { return $info }
    }
    $found = Find-CompatiblePython
    if ($found) { return $found }
    throw "Python se instalo, pero no se encontro. Abre una consola nueva y ejecuta setup.bat."
}

function Ensure-Venv {
    param(
        [string]$Name,
        [pscustomobject]$Python,
        [switch]$Recreate
    )
    $venv = Join-Path $Root ".venv-$Name"
    $pythonExe = Join-Path $venv "Scripts\python.exe"
    if ($Recreate -and (Test-Path $venv)) {
        Write-Step "Eliminando .venv-$Name anterior"
        Remove-Item -Recurse -Force $venv
    }
    if (Test-Path $pythonExe) {
        & $pythonExe -m pip --version > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Ya existe .venv-$Name"
            return $pythonExe
        }
    }
    if (Test-Path $venv) {
        Remove-Item -Recurse -Force $venv
    }

    Write-Step "Creando .venv-$Name"
    & $Python.Exe -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $pythonExe)) {
        if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
        & $Python.Exe -m venv --without-pip $venv
    }
    if (-not (Test-Path $pythonExe)) {
        throw "No se pudo crear .venv-$Name"
    }

    & $pythonExe -m pip --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Instalando pip en .venv-$Name"
        & $pythonExe -m ensurepip --upgrade
        & $pythonExe -m pip --version > $null 2>&1
        if ($LASTEXITCODE -ne 0) {
            $getpip = Join-Path $env:TEMP "get-pip-$Name.py"
            Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip -UseBasicParsing
            & $pythonExe $getpip
            Remove-Item $getpip -Force -ErrorAction SilentlyContinue
        }
    }
    & $pythonExe -m pip --version > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo preparar pip en .venv-$Name"
    }
    return $pythonExe
}

function Invoke-Pip {
    param(
        [string]$PythonExe,
        [string[]]$PipArgs,
        [string]$Label
    )
    Write-Step $Label
    & $PythonExe -m pip @PipArgs
    if ($LASTEXITCODE -ne 0) {
        throw "pip fallo en '$Label' (codigo $LASTEXITCODE)"
    }
}

function New-DesktopShortcut {
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        if (-not $desktop) { return }
        $linkPath = Join-Path $desktop "KittenTTS Local.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($linkPath)
        $shortcut.TargetPath = Join-Path $Root "run.bat"
        $shortcut.WorkingDirectory = $Root
        $shortcut.Description = "KittenTTS Local"
        $shortcut.Save()
        Write-Host "Acceso directo creado: $linkPath"
    } catch {
        Write-Warning "No se pudo crear el acceso directo: $($_.Exception.Message)"
    }
}

$exitCode = 0
try {
    Write-Step "KittenTTS Local: instalacion ($AssetProfile)"
    $pythonInfo = Find-CompatiblePython
    if (-not $pythonInfo) {
        $pythonInfo = Install-Python
    }
    Write-Host "Usando Python $($pythonInfo.Version) en $($pythonInfo.Exe)"

    $env:PYTHONUTF8 = "1"
    $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

    $cppPython = Ensure-Venv -Name "cpp" -Python $pythonInfo -Recreate:$Force
    $pipCommon = @("install", "--no-cache-dir", "--disable-pip-version-check")
    Invoke-Pip -PythonExe $cppPython -PipArgs ($pipCommon + @("--index-url", $CpuIndex, "torch==2.13.0")) -Label "Instalando torch 2.13 CPU"
    Invoke-Pip -PythonExe $cppPython -PipArgs ($pipCommon + @("-r", (Join-Path $Root "requirements\cpp.txt"))) -Label "Instalando interfaz y motor C++"

    $prepPython = $null
    if ($AssetProfile -eq "full") {
        $prepPython = Ensure-Venv -Name "prep" -Python $pythonInfo -Recreate:$Force
        Invoke-Pip -PythonExe $prepPython -PipArgs ($pipCommon + @("--index-url", $CpuIndex, "torch==2.11.0", "torchaudio==2.11.0")) -Label "Instalando torch/torchaudio 2.11 CPU"
        Invoke-Pip -PythonExe $prepPython -PipArgs ($pipCommon + @("-r", (Join-Path $Root "requirements\prep.txt"))) -Label "Instalando preparacion de voces"
    }

    if (-not $SkipAssets) {
        $assetPython = if ($prepPython) { $prepPython } else { $cppPython }
        Write-Step "Descargando assets (puede tardar y ocupar varios GB)"
        & $assetPython (Join-Path $Root "setup_assets.py") --profile $AssetProfile
        if ($LASTEXITCODE -ne 0) {
            throw "La descarga de assets fallo (codigo $LASTEXITCODE)"
        }
    }

    Write-Step "Comprobando la instalacion"
    & $cppPython (Join-Path $Root "scripts\doctor.py") --load
    if ($LASTEXITCODE -ne 0) {
        throw "El diagnostico encontro errores (codigo $LASTEXITCODE)"
    }

    if (-not $NoShortcut) {
        New-DesktopShortcut
    }

    Write-Host ""
    Write-Host "Instalacion completada." -ForegroundColor Green
    Write-Host "Abre 'KittenTTS Local' en el escritorio o ejecuta run.bat."
    Write-Host "Log: $(Join-Path $Root 'logs\setup.log')"
} catch {
    $exitCode = 1
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Revisa el log: $(Join-Path $Root 'logs\setup.log')" -ForegroundColor Yellow
} finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
    }
}

exit $exitCode
