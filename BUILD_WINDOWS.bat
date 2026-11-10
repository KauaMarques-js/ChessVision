@echo off
cd /d "%~dp0"
where node >nul 2>nul || (echo Instale o Node.js LTS e tente novamente. & pause & exit /b 1)
where go >nul 2>nul || (echo Instale Go 1.25 ou superior e tente novamente. & pause & exit /b 1)
call npm ci
if errorlevel 1 goto erro
call npm run build:helper
if errorlevel 1 goto erro
call npm test
if errorlevel 1 goto erro
call npm run dist:win
if errorlevel 1 goto erro
echo Instalador criado na pasta release.
pause
exit /b 0
:erro
echo Falha na compilacao. Confira a mensagem acima.
pause
exit /b 1
