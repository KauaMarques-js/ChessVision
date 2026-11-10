@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: Execute primeiro o instalador ChessVisionLab 2.1 para instalar os componentes.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy()" >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERRO: Seu ambiente Python nao consegue abrir janelas Tcl/Tk - init.tcl ausente.
  echo Use o ChessVisionLab-Instalador-Windows-x64-v2.1.exe para reparar automaticamente.
  echo Nao e necessario desinstalar o Python do sistema.
  pause
  exit /b 2
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
