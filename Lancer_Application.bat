@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo L'application n'est pas encore installee.
    call Installer.bat
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo L'application s'est arretee avec une erreur.
    pause
)
