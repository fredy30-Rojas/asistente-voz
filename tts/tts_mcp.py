from fastmcp import FastMCP
import asyncio, edge_tts, os, re, tempfile

mcp = FastMCP("tts")

def clean_markdown(text):
    """Limpia markdown para TTS - mismo que tts_speak.py"""
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

@mcp.tool()
async def hablar(texto: str) -> str:
    """Habla el texto en voz alta usando TTS español"""
    if not texto or len(texto.strip()) < 3:
        return "texto muy corto"

    try:
        clean = clean_markdown(texto).strip()
        if len(clean) > 2000:
            clean = clean[:2000] + "."

        # Generar audio con edge_tts
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name

        comm = edge_tts.Communicate(clean, voice="es-ES-XimenaNeural", rate="-5%")
        await comm.save(mp3_path)

        # Reproducir en thread aparte (sounddevice es sync)
        def play_audio():
            import sounddevice as sd
            import soundfile as sf
            data, samplerate = sf.read(mp3_path)
            sd.play(data, samplerate)
            sd.wait()
            try:
                os.remove(mp3_path)
            except Exception:
                pass

        await asyncio.to_thread(play_audio)
        return "ok"

    except Exception as e:
        return f"error: {e}"

mcp.run()
