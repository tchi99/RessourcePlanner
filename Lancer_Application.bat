@echo off
setlocal
cd /d "%~dp0"

echo ATTENTION : Lancer_Application.bat est maintenant un alias de compatibilite V1 LEGACY.
echo Utilise Lancer_Web.bat pour le runtime Web / SQL cible.
echo.

call Lancer_Application_Legacy.bat
exit /b %errorlevel%
