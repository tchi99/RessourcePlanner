@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo  Installation - RessourcePlanner Web / SQL
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

where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo Node.js est requis pour construire le frontend React.
    echo Installe Node.js 22 puis relance ce fichier.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo.
    echo npm est introuvable. Reinstalle Node.js avec npm.
    pause
    exit /b 1
)

if not exist ".venv-web\Scripts\python.exe" (
    echo Creation de l'environnement Python Web isole...
    %PYTHON_CMD% -m venv .venv-web
    if errorlevel 1 goto :error
)

call ".venv-web\Scripts\activate.bat"

echo Mise a jour de pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

echo Installation des dependances Web / SQL...
pip install -r requirements-server.txt -c constraints-release.txt
if errorlevel 1 goto :error

echo Installation des dependances React...
pushd frontend
npm install --no-audit --no-fund
if errorlevel 1 (
    popd
    goto :error
)

echo Construction du frontend React de production...
npm run build
if errorlevel 1 (
    popd
    goto :error
)
popd

if not exist "frontend\dist\index.html" (
    echo.
    echo Le build React n'a pas produit frontend\dist\index.html.
    goto :error
)

echo.
echo Installation Web terminee.
echo Utilise maintenant Lancer_Web.bat.
pause
exit /b 0

:error
echo.
echo Une erreur est survenue pendant l'installation Web.
pause
exit /b 1
