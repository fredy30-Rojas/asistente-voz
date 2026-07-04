@echo off
chcp 65001 >nul
title AI Coder - Servidor Movil

echo ============================================
echo   AI CODER - Acceso desde movil
echo ============================================
echo.
echo   Servidor iniciado en el puerto 8766
echo.
echo   📱 Abre esto en tu movil:
echo.
echo   http://192.168.0.22:8766/ai-coder.html
echo.
echo   ⚠️  El PC y el movil deben estar en la misma WiFi
echo   🛑  Cierra esta ventana para detener el servidor
echo ============================================
echo.

cd /d "%~dp0"
python -m http.server 8766
