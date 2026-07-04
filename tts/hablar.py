#!/usr/bin/env python
"""
Habla texto en voz alta usando edge-tts (voz española).
Uso: python hablar.py "Texto a hablar"
"""

import sys, asyncio, re, tempfile, os

VOICE = "es-ES-XimenaNeural"
RATE = "-5%"

def clean_markdown(text: str) -> str:
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

async def speak(text: str):
    clean = clean_markdown(text)
    if not clean or len(clean) < 3:
        return
    if len(clean) > 2000:
        clean = clean[:2000] + "."
    
    import edge_tts
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = tmp.name
    
    comm = edge_tts.Communicate(clean, voice=VOICE, rate=RATE)
    await comm.save(mp3_path)
    
    import sounddevice as sd
    import soundfile as sf
    data, samplerate = sf.read(mp3_path)
    sd.play(data, samplerate)
    sd.wait()
    try:
        os.remove(mp3_path)
    except Exception:
        pass

if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else ""
    if not text:
        text = sys.stdin.read().strip()
    if text:
        asyncio.run(speak(text))
