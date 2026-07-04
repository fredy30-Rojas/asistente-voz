from flask import Flask, request
from flask_cors import CORS
import asyncio, edge_tts, os, threading

app = Flask(__name__)
CORS(app)

def hablar(texto):
    async def _run():
        c = edge_tts.Communicate(texto, voice="es-ES-AlvaroNeural")
        await c.save("out.mp3")
        os.system("start out.mp3")
    asyncio.run(_run())

@app.route("/hablar", methods=["POST"])
def tts():
    texto = request.json.get("texto","")
    threading.Thread(target=hablar, args=(texto,)).start()
    return {"ok":True}

if __name__=="__main__":
    app.run(port=5500)
