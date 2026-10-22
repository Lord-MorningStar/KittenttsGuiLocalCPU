@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv-cpp\Scripts\python.exe" (
    echo.
    echo KittenTTS Local no esta instalado todavia.
    echo Ejecuta setup.bat primero.
    echo.
    pause
    exit /b 1
)
set "PYTHONUTF8=1"
set "GRADIO_ANALYTICS_ENABLED=False"
".venv-cpp\Scripts\python.exe" app.py %*
if errorlevel 1 (
    echo.
    echo La aplicacion termino con un error. Revisa logs\app.log
    echo.
    pause
)
