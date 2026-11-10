@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute primeiro instalar_windows.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 (pause & exit /b 1)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name ChessVisionLab app.py
if errorlevel 1 (pause & exit /b 1)
if not exist "dist\engine" mkdir "dist\engine"
xcopy /e /i /y "engine\*" "dist\engine\" >nul
xcopy /e /i /y "extension\*" "dist\extension\" >nul
echo.
echo Pronto: dist\ChessVisionLab.exe
pause
