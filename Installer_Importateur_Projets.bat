@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  Installation - Importateur projets ERP
echo =====================================================

where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo.
        echo Python n'est pas installe ou n'est pas dans le PATH.
        echo Installe Python 3.11 ou 3.12 puis relance ce fichier.
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
)

if not exist ".venv-importer\Scripts\python.exe" (
    echo Creation de l'environnement Python de l'importateur...
    %PYTHON_CMD% -m venv .venv-importer
    if errorlevel 1 goto :error
)

call ".venv-importer\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :error
pip install -r requirements-importer.txt
if errorlevel 1 goto :error

echo.
echo Installation terminee.
echo Utilise maintenant Importer_Projets_ERP.bat.
pause
exit /b 0

:error
echo.
echo Une erreur est survenue pendant l'installation de l'importateur.
pause
exit /b 1
