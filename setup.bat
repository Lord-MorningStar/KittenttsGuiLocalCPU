@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PS_ARGS="

:parse
if "%~1"=="" goto run
if /I "%~1"=="--runtime-only" (
    set "PS_ARGS=%PS_ARGS% -RuntimeOnly"
) else if /I "%~1"=="--skip-assets" (
    set "PS_ARGS=%PS_ARGS% -SkipAssets"
) else if /I "%~1"=="--force" (
    set "PS_ARGS=%PS_ARGS% -Force"
) else if /I "%~1"=="--no-shortcut" (
    set "PS_ARGS=%PS_ARGS% -NoShortcut"
) else if /I "%~1"=="--help" (
    echo Uso: setup.bat [--runtime-only] [--skip-assets] [--force] [--no-shortcut]
    exit /b 0
) else if /I "%~1"=="-h" (
    echo Uso: setup.bat [--runtime-only] [--skip-assets] [--force] [--no-shortcut]
    exit /b 0
) else (
    set "PS_ARGS=%PS_ARGS% %~1"
)
shift
goto parse

:run
echo.
echo KittenTTS Local - instalador para Windows 10/11
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" %PS_ARGS%
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo La instalacion no termino correctamente.
    echo Revisa: "%~dp0logs\setup.log"
    echo.
    pause
)
exit /b %RC%
