#!/usr/bin/env python
"""
Modulo de IA multi-proveedor para el asistente de voz.
Soporta Groq y Cerebras con fallback automatico.

Proveedores:
- Groq:   gratuito, ultra-rapido (30 RPM, 1K TPM)
- Cerebras: gratuito, mayor capacidad (5 RPM, 30K TPM)

Uso:
    from ai import preguntar
    respuesta = preguntar("Cual es la capital de Francia?")
"""

import json
import os
import urllib.request

# ==================== CONFIGURACION ====================

# Claves API - configurar como variables de entorno o aqui
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")

# Modelos
GROQ_MODEL = "llama-3.3-70b-versatile"
CEREBRAS_MODEL = "zai-glm-4.7"

# Endpoints (ambos OpenAI-compatibles)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# Timeout HTTP (segundos)
HTTP_TIMEOUT = 15

# System prompt en espanol
SYSTEM_PROMPT = (
    "Eres un asistente de voz llamado Asistente. "
    "Responde de forma directa, concisa, natural y hablada. "
    "No uses listas largas, markdown, ni codigo. "
    "Maximo 3 oraciones por respuesta. "
    "Habla en espanol latino neutro."
)



# ==================== PROVEEDORES ====================

def _call_api(url: str, api_key: str, model: str, question: str) -> str | None:
    """Llama a una API OpenAI-compatible y retorna la respuesta"""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        "temperature": 0.7,
        "max_tokens": 256,
        "stream": False
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "asistente-voz/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            # Manejar errores de API (rate limit, auth, etc.)
            if "error" in data:
                print(f"  [AI] Error API: {data['error']}")
                return None
            if "choices" not in data or len(data["choices"]) == 0:
                print(f"  [AI] Respuesta inesperada: {raw[:200]}")
                return None
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [AI] Error: {e}")
        return None


def ask_groq(question: str) -> str | None:
    """Consulta a Groq (rapido, 1K TPM)"""
    if not GROQ_API_KEY:
        return None
    return _call_api(GROQ_URL, GROQ_API_KEY, GROQ_MODEL, question)


def ask_cerebras(question: str) -> str | None:
    """Consulta a Cerebras (mayor capacidad, 30K TPM)"""
    if not CEREBRAS_API_KEY:
        return None
    return _call_api(CEREBRAS_URL, CEREBRAS_API_KEY, CEREBRAS_MODEL, question)


# ==================== FUNCION PRINCIPAL ====================

def preguntar(question: str) -> str | None:
    """
    Envia una pregunta a la IA con fallback:
    Groq primero (mas rapido), Cerebras si Groq falla.
    Retorna la respuesta o None si ambos fallan.
    """
    # Intentar Groq primero (mas rapido, mejor para voz)
    if GROQ_API_KEY:
        respuesta = ask_groq(question)
        if respuesta:
            return respuesta
        print("  [AI] Groq fallo, intentando Cerebras...")

    # Fallback: Cerebras
    if CEREBRAS_API_KEY:
        respuesta = ask_cerebras(question)
        if respuesta:
            return respuesta

    # Ambos fallaron
    print("  [AI] Ningun proveedor disponible.")
    return None


# ==================== AUTO-TEST ====================
if __name__ == "__main__":
    print("Probando modulo AI...")
    print(f"  Groq API key: {'Configurada' if GROQ_API_KEY else 'FALTA'}")
    print(f"  Cerebras API key: {'Configurada' if CEREBRAS_API_KEY else 'FALTA'}")

    if GROQ_API_KEY or CEREBRAS_API_KEY:
        result = preguntar("Dime un dato curioso en una oracion.")
        print(f"  Respuesta: {result}")
    else:
        print("  No hay claves API configuradas. Configura GROQ_API_KEY o CEREBRAS_API_KEY.")
