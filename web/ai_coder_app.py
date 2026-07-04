#!/usr/bin/env python
"""
AI Coder - Asistente de escritorio con IA y voz
Escribe tu pregunta, la IA responde y habla la respuesta.
Como Alexa pero con teclado.

Uso: python ai_coder_app.py
"""

import asyncio
import ctypes
import os
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

# Agregar directorio padre al path para importar ai.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ai import preguntar

# ==================== CONFIGURACION ====================
VOICE = "es-ES-XimenaNeural"
RATE = "-5%"
FONT_SIZE = 16
BG_COLOR = "#1a1a2e"
FG_COLOR = "#e0e0e0"
INPUT_BG = "#16213e"
BUTTON_BG = "#f0c040"
BUTTON_FG = "#1a1a2e"


# ==================== TTS ====================
def clean_markdown(text: str) -> str:
    """Limpia markdown para TTS"""
    text = re.sub(r"```[^`]*```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def hablar(texto: str):
    """Habla el texto en un hilo aparte usando edge_tts"""
    clean = clean_markdown(texto).strip()
    if not clean or len(clean) < 3:
        return
    if len(clean) > 2000:
        clean = clean[:2000]

    mp3_path = os.path.join(tempfile.gettempdir(), "ai_coder_tts.mp3")

    async def _tts():
        import edge_tts
        comm = edge_tts.Communicate(clean, voice=VOICE, rate=RATE)
        await asyncio.wait_for(comm.save(mp3_path), timeout=15)

        # Reproducir con MCI (Windows)
        winmm = ctypes.windll.winmm
        alias = "ai_coder_audio"
        r = winmm.mciSendStringW(
            f'open "{mp3_path}" type mpegvideo alias {alias}', None, 0, None
        )
        if r == 0:
            try:
                winmm.mciSendStringW(f"play {alias}", None, 0, None)
                while True:
                    time.sleep(0.2)
                    buf = ctypes.create_unicode_buffer(128)
                    winmm.mciSendStringW(f"status {alias} mode", buf, 128, None)
                    if buf.value != "playing":
                        break
            finally:
                winmm.mciSendStringW(f"close {alias}", None, 0, None)

    def _run():
        try:
            asyncio.run(_tts())
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


# ==================== APP ====================
class AiCoderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Coder")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("700x600")
        self.root.minsize(400, 400)

        self.pensando = False  # evita multiples envios simultaneos

        # Header
        header = tk.Label(
            self.root,
            text="🤖 AI Coder",
            font=("Segoe UI", 22, "bold"),
            bg=BG_COLOR,
            fg=BUTTON_BG,
        )
        header.pack(pady=(15, 5))

        subtitle = tk.Label(
            self.root,
            text="Escribe tu pregunta · Enter para enviar · Esc para limpiar",
            font=("Segoe UI", 11),
            bg=BG_COLOR,
            fg="#888",
        )
        subtitle.pack(pady=(0, 10))

        # Chat area
        self.chat = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            font=("Segoe UI", FONT_SIZE),
            bg=BG_COLOR,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            relief=tk.FLAT,
            borderwidth=0,
            padx=15,
            pady=15,
            state=tk.DISABLED,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        # Input frame
        input_frame = tk.Frame(self.root, bg=BG_COLOR)
        input_frame.pack(fill=tk.X, padx=15, pady=(0, 15))

        self.input_entry = tk.Text(
            input_frame,
            height=3,
            font=("Segoe UI", FONT_SIZE),
            bg=INPUT_BG,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            relief=tk.FLAT,
            borderwidth=0,
            padx=12,
            pady=12,
            wrap=tk.WORD,
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        send_btn = tk.Button(
            input_frame,
            text="Enviar",
            font=("Segoe UI", 14, "bold"),
            bg=BUTTON_BG,
            fg=BUTTON_FG,
            relief=tk.FLAT,
            padx=20,
            pady=10,
            cursor="hand2",
            command=self.enviar,
        )
        send_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # Estado
        self.status = tk.Label(
            self.root,
            text="Listo · Groq + Cerebras",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg="#666",
        )
        self.status.pack(pady=(0, 8))

        # Bindings
        self.root.bind("<Return>", lambda e: self.enviar())
        self.root.bind("<Escape>", lambda e: self.limpiar())
        self.input_entry.bind("<Return>", lambda e: self._on_enter(e))

        # Focus input
        self.input_entry.focus_set()

        # Mensaje inicial
        self._append("AI Coder", "¡Hola! Soy tu asistente con IA. Escribe tu pregunta y te responderé en voz alta.", "system")

    def _on_enter(self, event):
        """Enter envía, Shift+Enter es nueva línea"""
        if not event.state & 0x1:  # Shift no presionado
            self.enviar()
            return "break"

    def _append(self, sender: str, message: str, tag: str = "user"):
        """Agrega mensaje al chat"""
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{sender}: ", ("sender",))
        self.chat.insert(tk.END, f"{message}\n\n", (tag,))
        self.chat.tag_configure("sender", foreground=BUTTON_BG, font=("Segoe UI", FONT_SIZE, "bold"))
        self.chat.tag_configure("user", foreground=FG_COLOR, font=("Segoe UI", FONT_SIZE))
        self.chat.tag_configure("assistant", foreground="#8be9fd", font=("Segoe UI", FONT_SIZE))
        self.chat.tag_configure("system", foreground="#888", font=("Segoe UI", FONT_SIZE, "italic"))
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def enviar(self):
        """Envía la pregunta a la IA"""
        if self.pensando:
            return  # evitar multiples envios simultaneos
        texto = self.input_entry.get("1.0", tk.END).strip()
        if not texto:
            return

        # Mostrar pregunta
        self._append("Tú", texto, "user")
        self.input_entry.delete("1.0", tk.END)
        self.status.configure(text="Pensando...")

        self.pensando = True

        # Consultar IA en hilo aparte
        def _consulta():
            try:
                respuesta = preguntar(texto)
                if respuesta is None:
                    respuesta = "Lo siento, no pude consultar la IA. Verifica tu conexión a internet y las API keys."

                # Mostrar respuesta en UI
                self.root.after(0, lambda: self._append("AI Coder", respuesta, "assistant"))
                self.root.after(0, lambda: self.status.configure(text="Listo · Groq + Cerebras"))

                # Hablar respuesta
                hablar(respuesta)
            finally:
                self.pensando = False

        threading.Thread(target=_consulta, daemon=True).start()

    def limpiar(self):
        """Limpia el chat"""
        self.chat.configure(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.configure(state=tk.DISABLED)
        self._append("AI Coder", "Chat limpio. ¿En qué te ayudo?", "system")

    def run(self):
        """Inicia la app"""
        self.root.mainloop()


if __name__ == "__main__":
    app = AiCoderApp()
    app.run()
