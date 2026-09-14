@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  RessourcePlanner Web / SQL
echo =====================================================

if not exist ".venv-web\Scripts\python.exe" (
    echo L'environnement Web .venv-web est introuvable.
    echo Lance Installer_Web.bat avant de demarrer l'application Web.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo Le build React frontend\dist est introuvable.
    echo Relance Installer_Web.bat pour reconstruire le frontend.
    pause
    exit /b 1
)

if not exist "frontend\dist\assets" (
    echo Le build React est incomplet : frontend\dist\assets est introuvable.
    echo Relance Installer_Web.bat pour reconstruire le frontend.
    pause
    exit /b 1
)

set "LOCAL_SQLITE_MODE=0"
if not defined RESOURCEPLANNER_DATABASE_URL (
    set "RESOURCEPLANNER_DATABASE_URL=sqlite:///./resourceplanner_server.db"
    set "LOCAL_SQLITE_MODE=1"
    echo Aucune URL de base de donnees definie.
    echo Utilisation de la base SQLite locale : resourceplanner_server.db
)

if "%LOCAL_SQLITE_MODE%"=="1" (
    echo Verification des migrations de la base locale...
    ".venv-web\Scripts\python.exe" -m alembic upgrade head
    if errorlevel 1 (
        echo.
        echo Echec des migrations Alembic.
        pause
        exit /b 1
    )
)

set "RESOURCEPLANNER_FRONTEND_DIST=%CD%\frontend\dist"

if not defined RESOURCEPLANNER_PORT set "DISPLAY_PORT=8000"
if defined RESOURCEPLANNER_PORT set "DISPLAY_PORT=%RESOURCEPLANNER_PORT%"

echo.
echo Demarrage de RessourcePlanner Web...
echo Interface : http://127.0.0.1:%DISPLAY_PORT%/
echo API       : http://127.0.0.1:%DISPLAY_PORT%/api/v1/
echo Sante     : http://127.0.0.1:%DISPLAY_PORT%/health
echo.

".venv-web\Scripts\python.exe" -m app.server
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Le runtime Web s'est arrete avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
