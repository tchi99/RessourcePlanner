@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-importer\Scripts\python.exe" (
    echo L'environnement .venv-importer est introuvable.
    echo Lance Installer_Importateur_Projets.bat avant d'utiliser l'importateur.
    pause
    exit /b 1
)

if not defined RESOURCEPLANNER_DATABASE_URL (
    set "RESOURCEPLANNER_DATABASE_URL=sqlite:///./resourceplanner_server.db"
)

".venv-importer\Scripts\python.exe" tools\import_erp_projects.py --gui
set EXIT_CODE=%errorlevel%
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
