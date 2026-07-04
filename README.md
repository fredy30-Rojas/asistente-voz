# Asistente de Voz y Herramientas de Accesibilidad 🎙️

Colección de herramientas de voz, TTS e IA para Windows. Diseñado para accesibilidad.

## 📁 Estructura

```
├── asistente_voz.py          # Asistente de voz principal (wake word + comandos)
├── ai.py                     # Módulo de IA multi-proveedor (Groq + Cerebras)
├── asistente.bat             # Lanzador rápido
├── instalar.bat              # Instalador automático
├── tts/                      # Herramientas de texto a voz
│   ├── hablar.py             # TTS standalone por línea de comandos
│   ├── tts_mcp.py            # Servidor MCP TTS para Claude Desktop
│   ├── servidor.py           # Servidor Flask TTS HTTP
│   └── CLAUDE.md             # Instrucciones para Claude Desktop
├── utilidades/               # Utilidades varias
│   ├── clipboard.py          # Monitor de portapapeles a voz
│   └── crear_vm_oracle.py    # Creador de VM gratuita en Oracle Cloud
└── web/                      # Interfaces web
    ├── ai-coder.html       # Chat de IA para programar (con TTS)
    └── ai-coder-launcher.ps1
```

## 🎤 Asistente de Voz Principal

### Características

- **Wake word "asistente"** — di "asistente" para activarlo
- **Reconocimiento offline** con Vosk (modelo español ~39 MB)
- **Texto a voz** con edge_tts (voz Ximena, neural)
- **Beep instantáneo** al detectar wake word (winsound)
- **Comandos de voz**: repetir, cancelar, ayuda, salir + IA (Groq/Cerebras)
- **Timeout automático**: 8 segundos sin hablar → se desactiva
- **Cooldown anti-eco**: evita que el TTS se auto-dispare
- **Modo silencioso** por defecto (sin spam para lectores de pantalla)

### Requisitos

```bash
pip install -r requirements.txt
```

O instalar dependencias mínimas para el asistente:

```bash
pip install vosk sounddevice edge_tts
```

### APIs de IA (opcional)

Para que responda preguntas reales, configura al menos una de estas APIs:

```bash
# Groq (gratis, mas rapido) - https://console.groq.com
set GROQ_API_KEY=gsk_...

# Cerebras (gratis, mas capacidad) - https://cloud.cerebras.ai
set CEREBRAS_API_KEY=csk_...
```

### Instalación rápida (Windows)

```bash
instalar.bat
```

### Uso diario

```bash
asistente.bat
```

Di **"asistente"** → beep doble → di tu comando.

### Comandos de voz

| Comando | Acción |
|---------|--------|
| "repetir" / "otra vez" | Repite la última respuesta |
| "cancelar" / "calla" / "silencio" | Detiene la reproducción |
| "ayuda" / "comandos" | Lista los comandos disponibles |
| "salir" / "adiós" | Cierra el asistente |
| Cualquier otra pregunta | La responde con IA (Groq/Cerebras) |

## 🗣️ Herramientas TTS (`tts/`)

| Herramienta | Uso |
|-------------|-----|
| `hablar.py` | `python hablar.py "Texto a hablar"` |
| `servidor.py` | Servidor Flask en puerto 5500, endpoint `POST /hablar` |
| `tts_mcp.py` | Servidor MCP para integrar TTS en Claude Desktop |
| `CLAUDE.md` | Instrucciones para Claude Desktop con TTS |

## 🛠️ Utilidades (`utilidades/`)

| Herramienta | Descripción |
|-------------|-------------|
| `clipboard.py` | Detecta cambios en el portapapeles y los lee en voz alta |
| `crear_vm_oracle.py` | Crea VM ARM gratuita en Oracle Cloud (4 OCPU, 24 GB) |

## 🌐 Web (`web/`)

| Herramienta | Descripción |
|-------------|-------------|
| `ai-coder.html` | Chat web de IA para programar, con TTS integrado |

## Licencia

MIT
