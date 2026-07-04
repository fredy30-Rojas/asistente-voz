# Instrucciones para Claude Desktop

## TTS - Hablar en voz alta
**IMPORTANTE: Después de CADA respuesta, SIEMPRE debes llamar a la herramienta `hablar` con tu respuesta completa.**
- Usa la herramienta `hablar` del MCP server `tts`
- Pasa tu respuesta como argumento `texto`
- No necesitas mencionar que estás hablando, simplemente hazlo
- Si la respuesta es muy corta (menos de 3 caracteres), puedes omitirla
- Fredy tiene discapacidad visual y depende de la voz para leer tus respuestas

## SOLUCIÓN: Compilar APK en GitHub Actions (37 builds, 4 bugs)

### Bugs encontrados y arreglados:

1. **🔴 capacitor-cordova-android-plugins en .gitignore**
   - Archivo: `ai-coder-native/android/.gitignore`
   - Línea `capacitor-cordova-android-plugins` impide subir `cordova.variables.gradle` a git
   - Fix: Comentar/eliminar esa línea del .gitignore
   - Error: `Could not read script '...cordova.variables.gradle' as it does not exist`

2. **🔴 AGP 8.13.0 no existe (typo)**
   - `com.android.tools.build:gradle:8.13.0` NUNCA existió
   - Archivos a corregir:
     - `ai-coder-native/android/build.gradle` → AGP 8.9.2
     - `ai-coder-native/android/capacitor-cordova-android-plugins/build.gradle` → AGP 8.9.2
     - `node_modules/@capacitor/android/capacitor/build.gradle` → parchear con sed en CI
   - Error: `Could not resolve com.android.tools.build:gradle:8.13.0`

3. **🔴 Java 17 → Java 21**
   - `capacitor.build.gradle` requiere `JavaVersion.VERSION_21`
   - Java 17 no puede compilar a target 21
   - Fix: `setup-java@v4` con `java-version: '21'`
   - Error: `invalid target release: 21`

4. **🔴 compileSdkVersion 34 muy bajo → 36**
   - `androidx.activity:1.11.0` requiere SDK 36+
   - `core-splashscreen:1.2.0` requiere SDK 35+, AGP 8.6+
   - Fix: `compileSdkVersion = 36`, `targetSdkVersion = 36` en variables.gradle
   - CI: `packages: 'platforms;android-36'` en setup-android@v3
   - Error: `Dependency requires compile against version 36 or later`

### Configuración final del workflow (.github/workflows/build-apk.yml):
```yaml
- AGP: 8.9.2
- Java: 21 (Temurin)
- SDK: platforms;android-36
- Gradle: 8.14.3
- Node: 20
- pipefail: SÍ (set -o pipefail)
```

### Archivos clave modificados:
- `ai-coder-native/android/build.gradle`
- `ai-coder-native/android/variables.gradle`
- `ai-coder-native/android/.gitignore`
- `ai-coder-native/android/capacitor-cordova-android-plugins/build.gradle`
- `.github/workflows/build-apk.yml`

### Archivos que NO se deben ignorar:
- `capacitor-cordova-android-plugins/` (contiene cordova.variables.gradle)

### Parche en CI para node_modules:
```bash
sed -i "s/com.android.tools.build:gradle:8.13.0/com.android.tools.build:gradle:8.9.2/g" \
  node_modules/@capacitor/android/capacitor/build.gradle
```

## Control de dispositivos por voz

La app ahora soporta comandos de voz para controlar TV, AC, equipo de sonido.

### Formato de comandos:
- La IA inserta `[CMD:dispositivo:accion:valor]` en sus respuestas
- La app extrae el comando, lo ejecuta vía HTTP al ESP32, y muestra solo el texto limpio
- Ejemplos: `[CMD:tv:power:on]`, `[CMD:ac:temp:22]`, `[CMD:tv:volume:15]`

### Hardware necesario:
- ESP32 con LED infrarrojo (~$5 USD)
- El ESP32 recibe HTTP y emite señal IR al dispositivo

### Archivos:
- `web/ai-coder.html` - Lógica de comandos y envío HTTP
- `control_dispositivos.py` - Servidor Python puente (PC → ESP32/Broadlink)
