@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo L'environnement Python .venv est introuvable.
    echo Lance Installer.bat avant de charger les donnees demo.
    pause
    exit /b 1
)

set "RESOURCEPLANNER_DATABASE_URL=sqlite:///./resourceplanner_server.db"

echo Preparation de la base SQLite locale...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo Echec des migrations Alembic.
    pause
    exit /b 1
)

echo.
echo Chargement des donnees de demonstration...
".venv\Scripts\python.exe" tools\seed_demo_data.py
set EXIT_CODE=%errorlevel%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Le chargement des donnees demo a echoue avec le code %EXIT_CODE%.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo Donnees demo pretes dans resourceplanner_server.db.
echo Tu peux maintenant lancer Lancer_Serveur.bat puis React avec npm run dev.
pause
exit /b 0
