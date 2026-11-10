@echo off
setlocal
cd /d "%~dp0"
echo.
echo =========================================
echo   ChessVision Lab 1.1 - instalacao Windows
echo =========================================
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 (
  echo ERRO: instale Python 3.11 ou mais recente do python.org
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy()" >nul 2>&1
if errorlevel 1 (
  echo ERRO: este Python foi instalado sem o Tcl/Tk. O import tkinter nao e suficiente.
  echo Execute ChessVisionLab-Instalador-Windows-x64-v2.1.exe para reparo isolado.
  pause
  exit /b 2
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERRO: dependencias Python nao instaladas. Verifique a internet.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_stockfish19.ps1"
if errorlevel 1 (
  echo ERRO: Stockfish 19 nao foi instalado automaticamente.
  echo Baixe em https://stockfishchess.org/download/ e extraia em engine\
  echo Depois execute DIAGNOSTICAR_WINDOWS.bat para verificar.
  pause
  exit /b 1
)
echo.
echo Instalacao concluida. Verificando componentes...
".venv\Scripts\python.exe" diagnostico.py
if errorlevel 1 (
  echo ERRO: falha no autoteste. Verifique diagnostico_resultado.txt
  pause
  exit /b 1
)
echo.
echo Tudo pronto. Execute ABRIR_CHESSVISION.bat
pause
