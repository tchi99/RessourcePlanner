@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-web\Scripts\python.exe" (
    echo L'environnement Python Web .venv-web est introuvable.
    echo Lance Installer_Web.bat avant de demarrer le serveur.
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

echo Demarrage du backend RessourcePlanner en mode API seul...
".venv-web\Scripts\python.exe" -m app.server
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Le serveur s'est arrete avec le code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
