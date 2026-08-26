@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement Python .venv est introuvable.
    echo Lance Installer.bat avant de demarrer le serveur.
    pause
    exit /b 1
)

echo Demarrage du backend RessourcePlanner...
".venv\Scripts\python.exe" -m app.server
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Le serveur s'est arrete avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
