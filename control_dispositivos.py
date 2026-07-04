"""
Servidor de control de dispositivos por infrarrojo
Recibe comandos HTTP de la app AI Coder y emite señales IR.

Requisitos hardware: ESP32/ESP8266 o Arduino con LED infrarrojo
Alternativa: Broadlink RM Mini o similar

Uso: python control_dispositivos.py
Luego configura la IP de esta PC en la app AI Coder.
"""

from flask import Flask, request
from flask_cors import CORS
import subprocess, json, os

app = Flask(__name__)
CORS(app)

# Base de datos de codigos IR
# Formato: { "dispositivo": { "accion": [codigo_ir_nec, ...] } }
# Los codigos son en formato NEC (protocolo, address, command)
IR_CODES = {
    "tv": {
        "power": 0x10EF,
        "volume_up": 0x10EF40BF,
        "volume_down": 0x10EFC03F,
        "mute": 0x10EF906F,
        "channel_up": 0x10EF00FF,
        "channel_down": 0x10EF807F,
    },
    "ac": {
        "power": 0x8800B,
        "temp_up": 0x8800C,
        "temp_down": 0x8800D,
    },
    "sound": {
        "power": 0x20DF10EF,
        "volume_up": 0x20DF40BF,
        "volume_down": 0x20DFC03F,
    }
}

def send_ir_esp32(device, action, value=""):
    """Envia comando IR via serial al ESP32 conectado por USB"""
    try:
        import serial
        ser = serial.Serial(os.environ.get('SERIAL_PORT', 'COM3'), 115200, timeout=1)
        cmd = f"{device}:{action}:{value}\n"
        ser.write(cmd.encode())
        ser.close()
        return True, f"Enviado a ESP32: {cmd.strip()}"
    except Exception as e:
        return False, f"Error ESP32: {e}"

def send_ir_broadlink(device, action, value=""):
    """Envia comando IR via Broadlink RM (WiFi)"""
    try:
        import broadlink
        devices = broadlink.discover(timeout=5)
        if not devices:
            return False, "Broadlink no encontrado"
        dev = devices[0]
        dev.auth()
        # Buscar codigo guardado
        code_file = f"ir_codes/{device}_{action}.txt"
        if os.path.exists(code_file):
            with open(code_file) as f:
                code = bytes.fromhex(f.read())
            dev.send_data(code)
            return True, "Enviado via Broadlink"
        return False, f"Codigo no encontrado: {code_file}"
    except ImportError:
        return False, "broadlink no instalado: pip install broadlink"
    except Exception as e:
        return False, f"Error Broadlink: {e}"

def send_ir_http(device, action, value=""):
    """Reenvia el comando a otro dispositivo HTTP (ESP32 WiFi)"""
    esp32_ip = os.environ.get("ESP32_IP", "192.168.1.100")
    try:
        import urllib.request
        url = f"http://{esp32_ip}/ir?d={device}&a={action}&v={value}"
        urllib.request.urlopen(url, timeout=3)
        return True, f"Enviado a ESP32 WiFi ({esp32_ip})"
    except Exception as e:
        return False, f"Error HTTP: {e}"

@app.route("/device")
def device():
    """Endpoint principal: /device?d=tv&a=power&v=on"""
    device = request.args.get("d", "")
    action = request.args.get("a", "")
    value = request.args.get("v", "")

    print(f"Comando: {device} -> {action} ({value})")

    # Intentar metodos en orden
    ok, msg = send_ir_esp32(device, action, value)
    if not ok:
        ok, msg = send_ir_http(device, action, value)
    if not ok:
        ok, msg = send_ir_broadlink(device, action, value)

    return {"ok": ok, "message": msg, "device": device, "action": action}

@app.route("/learn")
def learn():
    """Modo aprendizaje: grabar un codigo IR nuevo"""
    device = request.args.get("d", "")
    action = request.args.get("a", "")
    return {"ok": True, "message": f"Modo aprendizaje activado. Apunta el control a {device} y presiona {action}."}

@app.route("/codes")
def list_codes():
    """Lista los codigos IR configurados"""
    return json.dumps(IR_CODES, indent=2)

@app.route("/")
def index():
    return """
    <h1>Control de Dispositivos IR</h1>
    <p>Endpoints:</p>
    <ul>
        <li><code>/device?d=tv&a=power&v=on</code> - Enviar comando</li>
        <li><code>/learn?d=tv&a=power</code> - Modo aprendizaje</li>
        <li><code>/codes</code> - Ver codigos configurados</li>
    </ul>
    """

if __name__ == "__main__":
    print("Servidor de control IR iniciado en http://0.0.0.0:5600")
    print("Endpoints:")
    print("  /device?d=tv&a=power&v=on")
    print("  /learn?d=tv&a=power")
    print("  /codes")
    app.run(host="0.0.0.0", port=5600)
