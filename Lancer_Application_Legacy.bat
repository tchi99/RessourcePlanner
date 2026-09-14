@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  Planification MO V1 - LEGACY NiceGUI / Excel
echo =====================================================
echo Ce lanceur est conserve uniquement pendant la transition.
echo Pour le runtime cible, utilise Lancer_Web.bat.
echo.

if not exist ".venv\Scripts\python.exe" (
    echo L'application V1 legacy n'est pas encore installee.
    call Installer.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo L'application V1 legacy s'est arretee avec une erreur.
    pause
)
