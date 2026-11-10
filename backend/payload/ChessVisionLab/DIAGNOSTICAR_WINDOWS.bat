@echo off
setlocal
cd /d "%~dp0"
echo.
echo ======================================
echo   ChessVision Lab - TESTE INTEGRADO
echo ======================================
if not exist ".venv\Scripts\python.exe" (
  echo ERRO: Execute instalar_windows.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
  echo ERRO: um dos testes Python falhou.
  pause
  exit /b 1
)
where node >nul 2>nul
if not errorlevel 1 (
  node tests\test_reader.js
  if errorlevel 1 (pause & exit /b 1)
  node tests\test_background.js
  if errorlevel 1 (pause & exit /b 1)
) else (
  echo Node.js nao instalado. Testes JS opcionais nao executados.
)
".venv\Scripts\python.exe" diagnostico.py
if errorlevel 1 (
  echo.
  echo FALHA NO DIAGNOSTICO - leia diagnostico_resultado.txt
  pause
  exit /b 1
)
echo.
echo TODOS OS TESTES DISPONIVEIS FORAM APROVADOS.
pause
