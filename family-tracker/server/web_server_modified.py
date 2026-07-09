#!/usr/bin/env python3
"""
Servidor web de chat Claude 24/7
Accesible desde cualquier navegador — móvil o PC
Audio auto-reproduce sin tocar play
"""

import os
import io
import json
import uuid
import asyncio
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
import edge_tts
from openai import OpenAI
from aiohttp import web
import urllib.request
import requests
import re

# ── Config ──────────────────────────────────────────────
CEREBRAS_KEY = os.environ.get("CEREBRAS_KEY", "CEREBRAS_KEY_PLACEHOLDER")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "GROQ_KEY_PLACEHOLDER")
PORT = int(os.environ.get("PORT", "8080"))
HTTPS_URL = os.environ.get("HTTPS_URL", "https://34-173-169-64.nip.io")
TTS_VOICE = "es-ES-AlvaroNeural"
TTS_RATE = "-5%"

MEMORY_DIR = Path(__file__).parent / "memories"
SYSTEM_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"

# Clientes API gratuitos
cerebras_client = OpenAI(api_key=CEREBRAS_KEY, base_url="https://api.cerebras.ai/v1")
groq_client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1")

# Cadena automatica: prueba uno por uno hasta que funcione
MODEL_CHAIN = [
    ("Cerebras", cerebras_client, "gemma-4-31b", 500),
    ("Groq", groq_client, "llama-3.3-70b-versatile", 500),
]


# Clima Open-Meteo (gratis, sin API key)
CLIMA_CODES = {0:'despejado',1:'poco nublado',2:'nublado',3:'nublado',45:'niebla',51:'llovizna',53:'llovizna',55:'llovizna',61:'lluvia ligera',63:'lluvia',65:'lluvia fuerte',71:'nieve ligera',73:'nieve',75:'nieve fuerte',80:'lluvia fuerte',81:'lluvia intensa',82:'tormenta',95:'tormenta',96:'tormenta granizo',99:'tormenta granizo'}

def get_weather(lat, lon, tz, label):
    try:
        url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code&timezone={tz}'
        req = urllib.request.urlopen(url, timeout=8)
        data = json.loads(req.read())
        c = data['current']
        w = CLIMA_CODES.get(c['weather_code'], 'nublado')
        return f"{label}: {c['temperature_2m']} grados, {w}, humedad {c['relative_humidity_2m']} por ciento"
    except:
        return None

# ── Memories ────────────────────────────────────────────
def load_memories():
    if not MEMORY_DIR.exists():
        return ""
    parts = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        parts.append(f"{f.stem}: {f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)

def load_system_prompt():
    if SYSTEM_PROMPT_FILE.exists():
        return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    return "Eres Claude, asistente de IA. Responde en español."

def build_system_message():
    return f"""{load_system_prompt()}

## Usuario
- Fredy y su esposa
- Fredy tiene ELA, usa control ocular (Tobii + OptiKey)
- Fecha: {datetime.now().strftime('%Y-%m-%d')}

## Memorias
{load_memories()}

## Instrucciones
- Responde SIEMPRE en español
- Sé cálido, servicial, conciso
- Tus respuestas serán leídas en voz alta: no uses emojis ni markdown complejo
"""

# ── Sessions ────────────────────────────────────────────
sessions = {}

def get_or_create_session(sid):
    if sid not in sessions:
        sessions[sid] = {"history": [], "name": "Usuario"}
    return sessions[sid]

def chat(sid, message):
    s = get_or_create_session(sid)
    history = s["history"]

    api_messages = [{"role": "system", "content": build_system_message()}]
    api_messages.extend(history[-10:])
    api_messages.append({"role": "user", "content": message})

    reply = None
    for name, cl, model, max_tok in MODEL_CHAIN:
        try:
            response = cl.chat.completions.create(
                model=model,
                messages=api_messages,
                max_tokens=max_tok,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                reply = content
                print(f"[{name}] OK")
                break
            print(f"[{name}] Respuesta vacia, probando siguiente...")
        except Exception as e:
            print(f"[{name}] Error: {e}")

    if reply is None:
        reply = "Lo siento, no puedo responder ahora. Intenta de nuevo."

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    if len(history) > 20:
        s["history"] = history[-20:]

    return reply

# ── TTS ──────────────────────────────────────────────────
async def texto_a_voz(texto):
    mp3_data = io.BytesIO()
    comunicate = edge_tts.Communicate(texto, TTS_VOICE, rate=TTS_RATE)
    async for chunk in comunicate.stream():
        if chunk["type"] == "audio":
            mp3_data.write(chunk["data"])

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_data.getvalue())
        mp3_path = f.name
    ogg_path = mp3_path.replace(".mp3", ".ogg")

    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "16k",
         "-ar", "16000", "-ac", "1", ogg_path],
        capture_output=True, timeout=30
    )
    with open(ogg_path, "rb") as f:
        ogg_bytes = f.read()
    for p in [mp3_path, ogg_path]:
        if os.path.exists(p):
            os.unlink(p)
    return ogg_bytes

# ── Audio cache ─────────────────────────────────────────
audio_cache = {}  # hash -> base64

# ── GPS: Ubicaciones ────────────────────────────────────
UBICACIONES_FILE = Path(__file__).parent / "ubicaciones.json"

def cargar_ubicaciones():
    """Carga ubicaciones desde JSON. Si no existe, devuelve diccionario vacío."""
    try:
        if UBICACIONES_FILE.exists():
            with open(UBICACIONES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"[GPS] Error cargando ubicaciones: {e}")
        return {}

def guardar_ubicaciones(data):
    """Guarda el diccionario de ubicaciones como JSON."""
    try:
        with open(UBICACIONES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[GPS] Error guardando ubicaciones: {e}")

# ── Redirect HTTP → HTTPS ────────────────────────────────
@web.middleware
async def redirect_http(request, handler):
    """Redirige HTTP directo a HTTPS (respeta proxy de Caddy)"""
    proto = request.headers.get("X-Forwarded-Proto", "")
    if proto != "https":
        path = request.path_qs
        return web.HTTPMovedPermanently(f"{HTTPS_URL}{path}")
    return await handler(request)

# ── Helpers ─────────────────────────────────────────────
def nocache_response(filepath):
    """Sirve archivo con headers anti-caché"""
    return web.FileResponse(
        filepath,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# ── Routes ──────────────────────────────────────────────
async def index(request):
    return nocache_response(Path(__file__).parent / "chat.html")

async def api_chat(request):
    try:
        data = await request.json()
        sid = data.get("sid", str(uuid.uuid4()))
        message = data.get("message", "").strip()
        if not message:
            return web.json_response({"error": "mensaje vacío"}, status=400)

        reply = chat(sid, message)
        ogg = await texto_a_voz(reply)

        return web.json_response({
            "sid": sid,
            "text": reply,
            "audio": ogg.hex()
        })
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)

async def api_audio(request):
    """Entrega el audio como archivo OGG para reproducción directa"""
    try:
        data = await request.json()
        sid = data.get("sid", "anon")
        message = data.get("message", "").strip()
        if not message:
            return web.Response(status=400, text="mensaje vacío")

        reply = chat(sid, message)
        ogg = await texto_a_voz(reply)

        return web.Response(
            body=ogg,
            content_type="audio/ogg",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        return web.Response(status=500, text=str(e)[:300])

# ── API: GPS ─────────────────────────────────────────────
async def api_gps_post(request):
    """POST /api/gps - Recibe ubicación GPS del teléfono"""
    try:
        data = await request.json()
        name = data.get("name", "").strip().lower()
        if not name:
            return web.json_response({"error": "nombre requerido"}, status=400)

        lat = data.get("lat")
        lon = data.get("lon")
        accuracy = data.get("accuracy")
        battery = data.get("battery")
        device = data.get("device")

        # Validar que lat y lon sean numeros
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return web.json_response({"error": "lat y lon deben ser numeros"}, status=400)

        ubicaciones = cargar_ubicaciones()
        ubicaciones[name] = {
            "name": name,
            "lat": lat,
            "lon": lon,
            "accuracy": accuracy,
            "battery": battery,
            "device": device,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        guardar_ubicaciones(ubicaciones)

        print(f"[GPS] Ubicación guardada: {name} ({lat}, {lon})")
        return web.json_response({"ok": True, "name": name})
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)

async def api_gps_get_by_name(request):
    """GET /api/gps/{name} - Obtiene ubicación de una persona"""
    try:
        name = request.match_info.get("name", "").strip().lower()
        ubicaciones = cargar_ubicaciones()

        if name not in ubicaciones:
            return web.json_response({"error": f"No se encontró ubicación para {name}"}, status=404)

        entry = dict(ubicaciones[name])
        lat = entry.get("lat")
        lon = entry.get("lon")

        # Agregar enlace a Google Maps
        if lat is not None and lon is not None:
            entry["maps_url"] = f"https://www.google.com/maps?q={lat},{lon}"

        # Calcular minutos desde última actualización
        ts_str = entry.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                ahora = datetime.now(timezone.utc)
                diff = ahora - ts
                entry["age_minutes"] = round(diff.total_seconds() / 60, 1)
            except:
                entry["age_minutes"] = None

        return web.json_response(entry)
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)

async def api_gps_get_all(request):
    """GET /api/gps - Devuelve todas las ubicaciones actuales"""
    try:
        ubicaciones = cargar_ubicaciones()
        # Filtrar claves internas (que empiezan con _)
        result = {}
        for key, value in ubicaciones.items():
            if not key.startswith("_"):
                entry = dict(value)
                lat = entry.get("lat")
                lon = entry.get("lon")
                if lat is not None and lon is not None:
                    entry["maps_url"] = f"https://www.google.com/maps?q={lat},{lon}"
                ts_str = entry.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        ahora = datetime.now(timezone.utc)
                        diff = ahora - ts
                        entry["age_minutes"] = round(diff.total_seconds() / 60, 1)
                    except:
                        entry["age_minutes"] = None
                result[key] = entry
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)

# ── Dashboard ────────────────────────────────────────────
async def serve_dashboard(request):
    """GET /dashboard - Sirve la página del mapa"""
    dashboard_path = Path(__file__).parent / "dashboard.html"
    if dashboard_path.exists():
        return nocache_response(dashboard_path)
    return web.Response(status=404, text="Dashboard no encontrado")

# ── Transcripción ──────────────────────────────────────
def transcribir_audio(audio_bytes):
    """Convierte audio a texto con Groq Whisper (sin limite de duracion)"""
    ogg_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            ogg_path = f.name
        with open(ogg_path, 'rb') as af:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                files={"file": ("audio.ogg", af, "audio/ogg")},
                data={"model": "whisper-large-v3-turbo", "language": "es"},
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                timeout=60
            )
        if resp.ok:
            return resp.json().get("text", None)
        return None
    except Exception as e:
        print(f"Transcripción error: {e}")
        return None
    finally:
        if ogg_path and os.path.exists(ogg_path):
            os.unlink(ogg_path)

# ── API: Audio message ─────────────────────────────────
async def api_audio_message(request):
    """Recibe audio, transcribe, chatea, devuelve audio"""
    try:
        data = await request.post()
        audio_field = data.get("audio")
        if not audio_field:
            return web.json_response({"error": "audio requerido"}, status=400)

        sid = data.get("sid", str(uuid.uuid4()))
        audio_bytes = audio_field.file.read()

        transcript = transcribir_audio(audio_bytes)
        if not transcript:
            return web.json_response({"error": "No se entendió el audio. Intenta de nuevo."}, status=400)

        reply = chat(sid, transcript)
        ogg = await texto_a_voz(reply)

        return web.json_response({
            "sid": sid,
            "transcript": transcript,
            "text": reply,
            "audio": ogg.hex()
        })
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)

# ── API: Video Analyze ─────────────────────────────────
async def api_video(request):
    """Recibe video, extrae frame, analiza con Groq Vision"""
    video_path = None
    frame_path = None
    try:
        data = await request.post()
        video_field = data.get("video")
        if not video_field:
            return web.json_response({"error": "video requerido"}, status=400)

        video_bytes = video_field.file.read()
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            video_path = f.name
        
        frame_path = video_path + ".jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "2", "-i", video_path, "-vframes", "1", 
             "-f", "image2pipe", "-q:v", "2", "-vcodec", "mjpeg", frame_path],
            capture_output=True, timeout=15, check=False
        )
        
        if not os.path.exists(frame_path) or os.path.getsize(frame_path) < 100:
            return web.json_response({"error": "No se pudo extraer frame"}, status=400)
        
        import base64
        with open(frame_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe este video en una frase corta, en espanol. Si hay TEXTO en la imagen, LEELO. Si ves personas, intenta identificarlas."},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}}
                    ]
                }],
                "max_tokens": 200, "temperature": 0.7
            },
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            timeout=30
        )
        description = resp.json()["choices"][0]["message"]["content"]
        
        return web.json_response({"description": description})
    except Exception as e:
        return web.json_response({"error": str(e)[:300]}, status=500)
    finally:
        for p in [video_path, frame_path]:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass

# ── Static ──────────────────────────────────────────────
async def serve_static(request):
    filename = request.match_info.get("filename", "")
    filepath = (Path(__file__).parent / filename).resolve()
    if not str(filepath).startswith(str(Path(__file__).parent.resolve())):
        return web.Response(status=403, text="Prohibido")
    if filepath.exists() and filepath.is_file():
        return nocache_response(filepath)
    return web.Response(status=404, text="No encontrado")

# ── QR ──────────────────────────────────────────────────
async def serve_qr_png(request):
    qr_path = Path(__file__).parent / "qr.png"
    if qr_path.exists():
        return web.FileResponse(qr_path)
    return web.Response(status=404)

async def qr_whatsapp(request):
    qr_path = Path(__file__).parent / "qr.html"
    if qr_path.exists():
        return web.Response(text=qr_path.read_text(encoding="utf-8"), content_type="text/html")
    return web.Response(text="QR no disponible aun. Espera unos segundos.", status=404)

# ── Background task: Limpiar ubicaciones viejas ──────────
async def limpiar_ubicaciones_viejas():
    """Tarea de fondo: elimina ubicaciones con más de 7 días"""
    while True:
        try:
            await asyncio.sleep(3600)  # Cada hora
            ubicaciones = cargar_ubicaciones()
            ahora = datetime.now(timezone.utc)
            limite = timedelta(days=7)
            a_eliminar = []
            for name, entry in ubicaciones.items():
                ts_str = entry.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ahora - ts > limite:
                            a_eliminar.append(name)
                    except:
                        pass
            if a_eliminar:
                for name in a_eliminar:
                    del ubicaciones[name]
                guardar_ubicaciones(ubicaciones)
                print(f"[GPS] Limpieza: {len(a_eliminar)} ubicaciones antiguas eliminadas")
        except Exception as e:
            print(f"[GPS] Error en limpieza: {e}")

# ── Main ────────────────────────────────────────────────
app = web.Application(middlewares=[redirect_http])
app.router.add_get("/", index)
app.router.add_get("/dashboard", serve_dashboard)
app.router.add_get("/{filename:.*\\.(json|js|png|ico|svg|css)}", serve_static)
app.router.add_get("/qr.html", qr_whatsapp)
app.router.add_post("/api/chat", api_chat)
app.router.add_post("/api/audio", api_audio)
app.router.add_post("/api/audio-message", api_audio_message)
app.router.add_post("/api/video", api_video)
# Nuevas rutas GPS
app.router.add_post("/api/gps", api_gps_post)
app.router.add_get("/api/gps", api_gps_get_all)
app.router.add_get("/api/gps/{name}", api_gps_get_by_name)

# Iniciar tarea de limpieza en background
async def on_startup(app):
    asyncio.create_task(limpiar_ubicaciones_viejas())

app.on_startup.append(on_startup)

if __name__ == "__main__":
    print(f"Claude Web Chat en puerto {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
