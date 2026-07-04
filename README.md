# Asistente de Voz 🎙️

Asistente de voz con reconocimiento de habla en español para Windows.

## Características

- **Wake word "asistente"** — di "asistente" para activarlo
- **Reconocimiento offline** con Vosk (modelo español ~39 MB)
- **Texto a voz** con edge_tts (voz Ximena, neural)
- **Beep instantáneo** al detectar wake word (winsound)
- **Comandos de voz**: repetir, cancelar, ayuda, salir
- **Timeout automático**: 8 segundos sin hablar → se desactiva
- **Cooldown anti-eco**: evita que el TTS se auto-dispare
- **Modo silencioso** por defecto (sin spam para lectores de pantalla)

## Requisitos

```bash
pip install vosk sounddevice edge_tts
```

## Uso

```bash
python asistente_voz.py
# o con transcripción parcial visible:
python asistente_voz.py --verbose
```

La primera ejecución descarga automáticamente el modelo Vosk español (39 MB).

Di **"asistente"** → beep doble → di tu comando.

## Comandos de voz

| Comando | Acción |
|---------|--------|
| "repetir" / "otra vez" | Repite la última respuesta |
| "cancelar" / "calla" / "silencio" | Detiene la reproducción |
| "ayuda" / "comandos" | Lista los comandos disponibles |
| "salir" / "adiós" | Cierra el asistente |

## Licencia

MIT
