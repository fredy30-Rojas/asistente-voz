@echo off
chcp 65001 >nul
title Instalador - Asistente de Voz

echo ============================================
echo   INSTALADOR - ASISTENTE DE VOZ
echo ============================================
echo.

:: 1. Verificar Python
echo [1/5] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado o no esta en PATH.
    echo Instala Python desde https://python.org y marca la opcion "Add to PATH".
    pause
    exit /b 1
)
python --version
echo.

:: 2. Instalar dependencias
echo [2/5] Instalando dependencias Python...
pip install vosk sounddevice edge_tts
if %errorlevel% neq 0 (
    echo ERROR: No se pudieron instalar las dependencias.
    echo Verifica tu conexion a internet e intenta de nuevo.
    pause
    exit /b 1
)
echo.

:: 3. Configurar clave API de Groq (opcional)
echo [3/5] Configurando inteligencia artificial (opcional)...
echo.
echo Para que el asistente responda preguntas reales, necesita una clave API.
echo Puedes obtener una gratis en: https://console.groq.com
echo.
set /p GROQ_KEY="Pega tu clave Groq (o presiona Enter para omitir): "
if not "%GROQ_KEY%"=="" (
    setx GROQ_API_KEY "%GROQ_KEY%" >nul
    if errorlevel 1 (
        echo ADVERTENCIA: No se pudo guardar GROQ_API_KEY permanentemente.
        echo El asistente funcionara sin IA hasta que la configures manualmente.
    ) else (
        echo Clave GROQ_API_KEY configurada permanentemente.
    )
) else (
    echo Sin clave API. El asistente funcionara en modo eco.
)
echo.

:: 4. Descargar modelo Vosk
echo [4/5] Descargando modelo de voz espanol (39 MB)...
echo Esto solo ocurre la primera vez. Espera...
echo.
python asistente_voz.py --download-only
if %errorlevel% neq 0 (
    echo ADVERTENCIA: La descarga del modelo pudo fallar.
    echo Puedes intentar de nuevo ejecutando: python asistente_voz.py --download-only
)
echo.

:: 5. Crear lanzador
echo [5/5] Creando lanzador asistente.bat...
(
echo @echo off
echo chcp 65001 ^>nul
if not "%GROQ_KEY%"=="" (
    echo set GROQ_API_KEY=%GROQ_KEY%
)
echo echo Iniciando Asistente de Voz...
echo echo Di "asistente" para activarme. Ctrl+C para salir.
echo echo.
echo cd /d "%~dp0"
echo python asistente_voz.py %%*
echo echo.
echo echo Asistente cerrado.
echo timeout /t 2 /nobreak ^>nul
) > "asistente.bat"

echo.
echo ============================================
echo   INSTALACION COMPLETA
echo ============================================
echo.
echo Para usar el asistente, ejecuta: asistente.bat
echo.
echo Comandos de voz:
echo   "asistente" - activa la escucha
echo   "repetir"   - repite lo ultimo
echo   "cancelar"  - detiene la reproduccion
echo   "ayuda"     - lista comandos
echo   "salir"     - cierra el asistente
echo.
if "%GROQ_KEY%"=="" (
    echo AVISO: No configuraste clave de IA.
    echo Para agregarla despues: setx GROQ_API_KEY "tu-clave-aqui"
)
echo.
echo Presiona cualquier tecla para salir...
pause >nul
