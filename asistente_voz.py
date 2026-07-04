#!/usr/bin/env python
"""
Asistente de Voz - Reconocimiento de voz con wake word + TTS
Usa Vosk (STT) y edge_tts (TTS) - completamente offline y en espanol.

Uso: python asistente_voz.py
     python asistente_voz.py --verbose   (muestra transcripcion parcial)
Di "asistente" para activarlo, luego di tu comando.
"""

import asyncio
import ctypes
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import urllib.request
import winsound
import zipfile

import sounddevice as sd
import edge_tts
from vosk import Model, KaldiRecognizer
from ai import preguntar

# ==================== CONFIGURACION ====================
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vosk-model-es")
WAKE_WORD = "asistente"
VOICE = "es-ES-XimenaNeural"
RATE = "-5%"
SAMPLE_RATE = 16000
COMMAND_TIMEOUT = 8       # segundos antes de cancelar escucha de comando
COOLDOWN_MS = 700         # ms de silencio post-TTS para evitar auto-trigger

VERBOSE = "--verbose" in sys.argv
DOWNLOAD_ONLY = "--download-only" in sys.argv  # solo descargar modelo y salir


# ==================== BEEP ACCESIBILIDAD ====================
def beep(freq=1000, duration=150):
    """Sonido instantaneo local - sin latencia de red"""
    try:
        winsound.Beep(freq, duration)
    except Exception:
        pass  # algunos sistemas no soportan Beep


def beep_wake():
    """Doble beep agudo: wake word detectada"""
    beep(880, 80)
    time.sleep(0.05)
    beep(1100, 120)


def beep_error():
    """Beep grave: error"""
    beep(400, 300)


def beep_ok():
    """Beep simple: operacion completada"""
    beep(800, 100)


def beep_thinking():
    """Beep agudo corto: pensando / consultando IA"""
    beep(1200, 80)
    time.sleep(0.06)
    beep(1400, 60)


# ==================== DESCARGA DEL MODELO ====================
def download_model():
    """Descarga y extrae el modelo Vosk espanol (~39 MB)"""
    if os.path.exists(MODEL_DIR) and os.path.isdir(MODEL_DIR):
        return

    print("ATENCION: Descargando modelo de voz espanol (39 MB).")
    print("Esto solo ocurre la primera vez. Por favor espere...")
    beep(600, 200)

    zip_path = MODEL_DIR + ".zip"

    try:
        urllib.request.urlretrieve(MODEL_URL, zip_path)
        print("Extrayendo modelo...")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(os.path.dirname(MODEL_DIR))

        extracted = os.path.join(os.path.dirname(MODEL_DIR), "vosk-model-small-es-0.42")
        if os.path.exists(extracted):
            os.rename(extracted, MODEL_DIR)

        print("Modelo listo.")
        beep_ok()

    except Exception as e:
        print(f"Error descargando modelo: {e}")
        beep_error()
        _cleanup_partial(zip_path)
        sys.exit(1)
    finally:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass


def _cleanup_partial(zip_path):
    """Limpia archivos parciales si la descarga falla"""
    import shutil
    for path in [zip_path, MODEL_DIR]:
        try:
            if os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        except Exception:
            pass
    extracted = os.path.join(os.path.dirname(MODEL_DIR), "vosk-model-small-es-0.42")
    try:
        if os.path.exists(extracted):
            shutil.rmtree(extracted)
    except Exception:
        pass


# ==================== LIMPIEZA DE TEXTO ====================
def clean_markdown(text: str) -> str:
    """Limpia markdown para TTS - mismo que hablar.py"""
    text = re.sub(r"```[^`]*```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^[-:\s|]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ==================== REPRODUCTOR TTS ====================
class TTSPlayer:
    """Reproductor TTS thread-safe con cooldown anti-eco"""

    def __init__(self):
        self._lock = threading.Lock()
        self._playback_lock = threading.Lock()  # evita colision MCI
        self._speaking = False
        self._cooldown_until = 0.0
        self._last_response = ""
        self._stop_requested = False

    @property
    def speaking(self):
        with self._lock:
            return self._speaking

    @speaking.setter
    def speaking(self, value):
        with self._lock:
            self._speaking = value

    @property
    def in_cooldown(self):
        with self._lock:
            return time.time() < self._cooldown_until

    def _start_cooldown(self):
        with self._lock:
            self._cooldown_until = time.time() + (COOLDOWN_MS / 1000.0)

    @property
    def last_response(self):
        with self._lock:
            return self._last_response

    @last_response.setter
    def last_response(self, value):
        with self._lock:
            self._last_response = value

    def request_stop(self):
        """Pedir que se detenga la reproduccion actual"""
        with self._lock:
            self._stop_requested = True

    def _is_stop_requested(self):
        with self._lock:
            return self._stop_requested

    def _clear_stop(self):
        with self._lock:
            self._stop_requested = False

    async def _tts_async(self, texto: str):
        """Genera audio con edge_tts y reproduce con API nativa de Windows"""
        if not texto or len(texto.strip()) < 3:
            return

        # Lock de reproduccion: evita que dos hilos usen MCI al mismo tiempo
        with self._playback_lock:
            await self._tts_playback(texto)

    async def _tts_playback(self, texto: str):
        """Reproduccion real con MCI (ya dentro del lock)"""
        clean = clean_markdown(texto).strip()
        if len(clean) > 2000:
            clean = clean[:2000] + "."

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name

        try:
            comm = edge_tts.Communicate(clean, voice=VOICE, rate=RATE)
            await comm.save(mp3_path)

            # API nativa MCI de Windows: reproduce MP3 sin ventanas
            if sys.platform == "win32":
                winmm = ctypes.windll.winmm
                r = winmm.mciSendStringW(
                    f'open "{mp3_path}" type mpegvideo alias tts_audio',
                    None, 0, None
                )
                if r == 0:
                    try:
                        # Lanzar reproduccion y verificar que inicio
                        r2 = winmm.mciSendStringW('play tts_audio', None, 0, None)
                        if r2 == 0:
                            # Polling para poder detectar stop_requested
                            while True:
                                time.sleep(0.2)
                                if self._is_stop_requested():
                                    winmm.mciSendStringW('stop tts_audio', None, 0, None)
                                    break
                                buf = ctypes.create_unicode_buffer(128)
                                winmm.mciSendStringW('status tts_audio mode', buf, 128, None)
                                if buf.value != "playing":
                                    break
                        else:
                            raise RuntimeError(f"MCI play failed: {r2}")
                    finally:
                        winmm.mciSendStringW('close tts_audio', None, 0, None)
                else:
                    # Fallback: abrir con reproductor por defecto de Windows
                    print("  Aviso: codec MCI no disponible, usando reproductor del sistema...")
                    try:
                        os.startfile(mp3_path)
                        # Esperar aproximado: 1.2 seg por cada 100 caracteres
                        time.sleep(min(len(clean) * 0.012, 30))
                    except Exception:
                        beep_error()
            else:
                # Linux/Mac: usar ffplay si esta disponible
                import subprocess
                try:
                    subprocess.run(
                        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path],
                        timeout=120, check=True
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    # Fallback: abrir con reproductor por defecto del sistema
                    try:
                        os.startfile(mp3_path)
                    except Exception:
                        pass

        except Exception as e:
            if VERBOSE:
                print(f"  Error TTS: {e}")
            beep_error()
        finally:
            try:
                os.remove(mp3_path)
            except Exception:
                pass

    def hablar(self, texto: str):
        """Wrapper sync para TTS"""
        self._clear_stop()
        asyncio.run(self._tts_async(texto))

    def hablar_en_hilo(self, texto: str) -> threading.Thread | None:
        """Ejecuta TTS en hilo aparte, maneja flags de estado"""

        # Si ya esta hablando, no acumular
        if self.speaking:
            return None

        def _run():
            self.speaking = True
            try:
                self.hablar(texto)
            finally:
                self.speaking = False
                self._start_cooldown()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t


# ==================== COMANDOS ====================
def process_command(text: str, tts: TTSPlayer) -> tuple:
    """
    Procesa el comando de voz y retorna (accion, respuesta).
    accion: "responder", "repetir", "cancelar", "ayuda", "salir", "desconocido"
    """
    text_lower = text.lower().strip()

    # Comando: cancelar / callar
    # Usar lista de palabras exactas (no substrings como 'preparar')
    cancel_words = ["cancelar", "calla", "callate", "silencio"]
    tokens = text_lower.split()
    if any(w in tokens for w in cancel_words):
        was_speaking = tts.speaking
        tts.request_stop()
        if was_speaking:
            return ("cancelar", "De acuerdo, me callo.")
        else:
            return ("cancelar_silent", "")

    # Comando: repetir
    if any(word in text_lower for word in ["repetir", "repite", "otra vez", "de nuevo", "que dijiste"]):
        last = tts.last_response
        if last:
            return ("repetir", last)
        else:
            return ("repetir", "No tengo nada que repetir todavia.")

    # Comando: ayuda
    if any(word in text_lower for word in ["ayuda", "comandos", "que puedes hacer", "que sabes hacer"]):
        return ("ayuda",
            "Puedes decir: asistente para activarme. Luego: "
            "repetir, para repetir lo ultimo. "
            "cancelar, para que me calle. "
            "ayuda, para escuchar esto. "
            "salir, para terminar."
        )

    # Comando: salir
    if any(word in text_lower for word in ["salir", "adios", "terminar", "cerrar"]):
        return ("salir", "Hasta luego.")

    # Comando desconocido: preguntar a la IA
    return ("ia", text)


# ==================== ASISTENTE PRINCIPAL ====================
def main():
    print("ASISTENTE DE VOZ")
    print("Di 'asistente' para activarme. Ctrl+C para salir.")
    if not VERBOSE:
        print("(modo silencioso - usa --verbose para ver transcripcion)")

    # Descargar modelo si es necesario
    download_model()

    # Modo --download-only: salir tras descargar modelo
    if DOWNLOAD_ONLY:
        print("Modelo descargado. Ejecuta sin --download-only para usar el asistente.")
        return

    # Cargar modelo Vosk
    print("Cargando modelo...")
    model = Model(MODEL_DIR)
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetWords(False)

    q = queue.Queue()
    tts = TTSPlayer()

    # Estados
    listening_for_command = False
    wake_time = 0.0

    def audio_callback(indata, frames, time_info, status):
        """Callback de sounddevice: recibe audio del microfono"""
        if status and VERBOSE:
            print(f"  Audio: {status}", flush=True)
        q.put(bytes(indata))

    print("Listo.\n")

    # Abrir microfono
    try:
        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=8000,
            dtype='int16',
            channels=1,
            callback=audio_callback
        )
        stream.start()
    except sd.PortAudioError as e:
        print(f"ERROR: No se pudo abrir el microfono.")
        print(f"Detalle: {e}")
        print("Verifica que tienes un microfono conectado en Windows.")
        beep_error()
        sys.exit(1)

    try:
        while True:
            try:
                data = q.get(timeout=0.3)
            except queue.Empty:
                # Timeout de comando
                if listening_for_command and (time.time() - wake_time) > COMMAND_TIMEOUT:
                    listening_for_command = False
                    print("Tiempo agotado.")
                    tts.hablar_en_hilo("No te he escuchado.")
                continue

            # Cooldown post-TTS: ignorar eco
            if tts.in_cooldown:
                while not q.empty():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
                continue

            # TTS en progreso: ignorar audio (evitar eco)
            if tts.speaking:
                while not q.empty():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break
                continue

            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get('text', '').strip().lower()

                if not text:
                    continue

                if listening_for_command:
                    # El usuario dio un comando
                    listening_for_command = False
                    print(f"Comando: {text}")

                    action, response = process_command(text, tts)
                    tts.last_response = response

                    if action == "salir":
                        print("Saliendo...")
                        tts.hablar(response)
                        break
                    elif action == "repetir":
                        tts.hablar_en_hilo(response)
                    elif action == "cancelar":
                        tts.hablar_en_hilo(response)
                    elif action == "cancelar_silent":
                        pass  # no decir nada si no habia TTS activo
                    elif action == "ayuda":
                        tts.hablar_en_hilo(response)
                    elif action == "ia":
                        # Preguntar a la IA en un hilo aparte
                        print(f"Pregunta: {text}")
                        beep_thinking()

                        def ia_worker(pregunta):
                            respuesta = preguntar(pregunta)
                            if respuesta is None:
                                respuesta = "Lo siento, no pude consultar la inteligencia artificial. Verifica tu conexion a internet."
                            tts.last_response = respuesta
                            print(f"IA: {respuesta}")
                            tts.hablar_en_hilo(respuesta)

                        threading.Thread(target=ia_worker, args=(text,), daemon=True).start()
                    else:
                        # responder / eco (no deberia llegar aqui con IA)
                        print(f"Respuesta: {response}")
                        tts.hablar_en_hilo(response)

                elif WAKE_WORD in text:
                    print("Despertado.")
                    # Drenar cola y resetear recognizer
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                    rec.Reset()
                    # Activar flag speaking ANTES del beep para que el
                    # audio capturado durante el beep sea ignorado
                    listening_for_command = True
                    wake_time = time.time()
                    tts_thread = tts.hablar_en_hilo("Dime")
                    time.sleep(0.05)  # dar tiempo al hilo de activar speaking
                    beep_wake()

            else:
                # Resultado parcial (mientras habla) - solo en verbose
                if VERBOSE and listening_for_command:
                    partial = json.loads(rec.PartialResult()).get('partial', '').strip().lower()
                    if partial:
                        print(f"\r   Escuchando: {partial}...", end="", flush=True)

    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        stream.stop()
        stream.close()
        print("Hasta luego.")
        beep(400, 100)


if __name__ == "__main__":
    main()
