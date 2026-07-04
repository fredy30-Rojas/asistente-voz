@echo off
chcp 65001 >nul
echo Iniciando Asistente de Voz...
echo Di "asistente" para activarme. Ctrl+C para salir.
echo.
cd /d "%~dp0"
python asistente_voz.py %*
echo.
echo Asistente cerrado. Hasta luego.
timeout /t 2 /nobreak >nul
