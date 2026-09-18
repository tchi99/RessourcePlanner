@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  Verification - RessourcePlanner Web
echo =====================================================

if not exist ".venv-web\Scripts\python.exe" (
    echo L'environnement Web .venv-web est introuvable.
    echo Lance Installer_Web.bat avant cette verification.
    pause
    exit /b 1
)

echo Verification de l'installation isolee...
".venv-web\Scripts\python.exe" tools\check_installed_web.py
if errorlevel 1 (
    echo.
    echo L'installation Web n'est pas conforme.
    pause
    exit /b 1
)

if not defined RESOURCEPLANNER_BASE_URL set "RESOURCEPLANNER_BASE_URL=http://127.0.0.1:8000"

echo.
echo Smoke du serveur deja demarre : %RESOURCEPLANNER_BASE_URL%
echo Si le serveur n'est pas lance, ouvre Lancer_Web.bat dans une autre console.
".venv-web\Scripts\python.exe" tools\smoke_running_web.py --base-url "%RESOURCEPLANNER_BASE_URL%"
if errorlevel 1 (
    echo.
    echo Le smoke Web a echoue.
    pause
    exit /b 1
)

echo.
echo Verification Web reussie.
pause
exit /b 0
