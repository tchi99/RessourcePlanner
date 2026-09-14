@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  Installation - Planification MO V1 ^(legacy^)
echo =====================================================

where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo.
        echo Python n'est pas installe ou n'est pas dans le PATH.
        echo Installe Python 3.11 ou 3.12 depuis python.org puis relance ce fichier.
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
)

if not exist ".venv\Scripts\python.exe" (
    echo Creation de l'environnement Python...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

call ".venv\Scripts\activate.bat"

echo Mise a jour de pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

echo Installation des dependances V1 validees...
pip install -r requirements-legacy.txt -c constraints-release.txt
if errorlevel 1 goto :error

echo.
echo Installation terminee.
echo Tu peux maintenant utiliser Lancer_Application.bat
pause
exit /b 0

:error
echo.
echo Une erreur est survenue pendant l'installation.
pause
exit /b 1
