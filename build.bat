@echo off
title Token Helper - Build
echo.
echo  =============================================
echo   Token Helper Building
echo  =============================================
echo.

cd /d "%~dp0"

echo [1/3] Installation des dependances...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR: pip install a echoue.
    pause
    exit /b 1
)

echo.
echo [2/3] Compilation en .exe...
python -m PyInstaller build.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo ERREUR: PyInstaller a echoue.
    pause
    exit /b 1
)

echo.
echo [3/3] Build termine !
echo.
echo  Le fichier exe se trouve dans: dist\TokenHelper.exe
echo.
echo  Appuie sur une touche pour ouvrir le dossier dist...
pause
start dist
