"""
Servidor de control de dispositivos por infrarrojo
Recibe comandos HTTP de la app AI Coder y emite senales IR.

Dispositivos soportados:
  tv, ac, sound, fan, light, proyector, dvd, heat, cortina

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

# Base de datos de codigos IR (valores placeholder - calibrar con tu control)
IR_CODES = {
    "tv": {
        "power": "0x10EF",
        "on": "0x10EF",
        "off": "0x10EF",
        "volume_up": "0x10EF40BF",
        "volume_down": "0x10EFC03F",
        "mute": "0x10EF906F",
        "channel_up": "0x10EF00FF",
        "channel_down": "0x10EF807F",
        "input": "0x10EFD02F",
        "menu": "0x10EFC23D",
        "back": "0x10EF3AC5",
        "home": "0x10EFBA45",
        "netflix": "0x10EF728D",
        "youtube": "0x10EF52AD",
    },
    "ac": {
        "power": "0x8800B",
        "on": "0x8800B",
        "off": "0x8800B",
        "temp_up": "0x8800C",
        "temp_down": "0x8800D",
        "mode_cool": "0x880010",
        "mode_heat": "0x880020",
        "mode_fan": "0x880030",
        "mode_dry": "0x880040",
        "mode_auto": "0x880050",
        "fan_auto": "0x880110",
        "fan_low": "0x880120",
        "fan_med": "0x880130",
        "fan_high": "0x880140",
        "swing": "0x880200",
    },
    "sound": {
        "power": "0x20DF10EF",
        "on": "0x20DF10EF",
        "off": "0x20DF10EF",
        "volume_up": "0x20DF40BF",
        "volume_down": "0x20DFC03F",
        "mute": "0x20DF906F",
        "input": "0x20DFD02F",
        "bass_up": "0x20DF08F7",
        "bass_down": "0x20DF8877",
        "next": "0x20DF02FD",
        "prev": "0x20DF827D",
        "play": "0x20DF22DD",
        "pause": "0x20DFA25D",
    },
    "fan": {
        "power": "0x30DF10EF",
        "on": "0x30DF10EF",
        "off": "0x30DF10EF",
        "speed_1": "0x30DF40BF",
        "speed_2": "0x30DFC03F",
        "speed_3": "0x30DF20DF",
        "oscillate": "0x30DF609F",
        "timer": "0x30DFE01F",
    },
    "light": {
        "power": "0x40DF10EF",
        "on": "0x40DF10EF",
        "off": "0x40DF10EF",
        "brightness_up": "0x40DF40BF",
        "brightness_down": "0x40DFC03F",
        "color_red": "0x40DF00FF",
        "color_blue": "0x40DF807F",
        "color_green": "0x40DF40AF",
        "color_white": "0x40DFC03A",
        "color_warm": "0x40DF20D0",
        "mode_flash": "0x40DFA05F",
        "mode_strobe": "0x40DF6090",
        "mode_fade": "0x40DFE010",
    },
    "proyector": {
        "power": "0x50DF10EF",
        "on": "0x50DF10EF",
        "off": "0x50DF10EF",
        "source": "0x50DF40BF",
        "freeze": "0x50DFC03F",
        "blank": "0x50DF20DF",
    },
    "dvd": {
        "power": "0x60DF10EF",
        "on": "0x60DF10EF",
        "off": "0x60DF10EF",
        "play": "0x60DF40BF",
        "pause": "0x60DFC03F",
        "stop": "0x60DF20DF",
        "next": "0x60DFA05F",
        "prev": "0x60DF609F",
        "eject": "0x60DFE01F",
    },
    "heat": {
        "power": "0x70DF10EF",
        "on": "0x70DF10EF",
        "off": "0x70DF10EF",
        "temp_high": "0x70DF40BF",
        "temp_low": "0x70DFC03F",
        "mode_low": "0x70DF20DF",
        "mode_med": "0x70DFA05F",
        "mode_high": "0x70DF609F",
    },
    "cortina": {
        "open": "0x80DF10EF",
        "close": "0x80DF40BF",
        "stop": "0x80DFC03F",
    },
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

    # Buscar el codigo IR
    code = None
    if device in IR_CODES:
        # Buscar combinacion exacta accion_valor
        key = f"{action}_{value}" if value else action
        if key in IR_CODES[device]:
            code = IR_CODES[device][key]
        elif action in IR_CODES[device]:
            code = IR_CODES[device][action]

    if code:
        print(f"  Codigo IR: {code}")
    else:
        print(f"  Sin codigo IR para {device}/{action}/{value}")

    # Intentar metodos en orden
    ok, msg = send_ir_esp32(device, action, value)
    if not ok:
        ok, msg = send_ir_http(device, action, value)
    if not ok:
        ok, msg = send_ir_broadlink(device, action, value)

    return {"ok": ok, "message": msg, "device": device, "action": action, "code": code}

@app.route("/learn")
def learn():
    """Modo aprendizaje: grabar un codigo IR nuevo"""
    device = request.args.get("d", "")
    action = request.args.get("a", "")
    return {"ok": True, "message": f"Modo aprendizaje para {device}/{action}. Apunta el control y presiona el boton."}

@app.route("/codes")
def list_codes():
    """Lista los codigos IR y dispositivos configurados"""
    devices = {}
    for dev, actions in IR_CODES.items():
        devices[dev] = list(actions.keys())
    return {"devices": devices, "codes": IR_CODES}

@app.route("/")
def index():
    html = "<h1>Control de Dispositivos IR</h1><p>Dispositivos soportados:</p><ul>"
    for dev, actions in IR_CODES.items():
        html += f"<li><b>{dev}</b>: {', '.join(actions.keys())}</li>"
    html += "</ul><p>Endpoints:</p><ul>"
    html += "<li><code>/device?d=tv&a=power&v=on</code> - Enviar comando</li>"
    html += "<li><code>/learn?d=tv&a=power</code> - Modo aprendizaje</li>"
    html += "<li><code>/codes</code> - Ver codigos configurados</li></ul>"
    return html

if __name__ == "__main__":
    print("Servidor de control IR iniciado en http://0.0.0.0:5600")
    print("Dispositivos:", ", ".join(IR_CODES.keys()))
    app.run(host="0.0.0.0", port=5600)
