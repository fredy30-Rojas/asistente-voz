import { makeWASocket, useMultiFileAuthState, DisconnectReason, downloadMediaMessage } from "@whiskeysockets/baileys";
import pino from "pino";
import axios from "axios";
import QRCode from "qrcode";
import { writeFileSync, readFileSync, unlinkSync, existsSync, mkdirSync } from "fs";
import { execSync } from "child_process";
import { tmpdir } from "os";
import { join } from "path";

// Cerebras API para texto (rapidisimo)
const CEREBRAS_KEY = process.env.CEREBRAS_KEY || "CEREBRAS_KEY_PLACEHOLDER";
const CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions";
const CEREBRAS_MODEL = "gpt-oss-120b";
// Groq API para audio y vision
const GROQ_KEY = process.env.GROQ_API_KEY || "GROQ_KEY_PLACEHOLDER";
const GROQ_MODEL = "llama-3.3-70b-versatile";
const GROQ_STT_MODEL = "whisper-large-v3-turbo";
const GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct";
const AUTH_DIR = "./auth_info";
const MAX_HISTORY = 30;
const GROQ_DELAY = 3000;
const EDGE_TTS = "/home/fredy/claude-bot-env/bin/edge-tts";
const TTS_VOICE = "es-BO-MarceloNeural";
const AUDIO_DIR = "/tmp/whatsapp_audio";
try { mkdirSync(AUDIO_DIR, { recursive: true }); } catch(e) {}

// GPS Server URL
const GPS_SERVER = "https://34-173-169-64.nip.io";

// ── GPS Query Functions ──────────────────────────────────
// Mapa inverso: apodos → nombre real guardado en el servidor
const NAME_TO_STORED = {
    "neca": "martha",
    "ñeca": "martha",
    "yose": "yoselin",
    "sele": "selena",
    "peloncito": "fernando",
    "guiye": "guillermo",
    "nes": "nestor",
    "tere": "teresa",
    "tucho": "carlos",
};

function resolveStoredName(name) {
    // Si el nombre es un apodo, devolver el nombre real guardado
    return NAME_TO_STORED[name] || name;
}

function handleGpsQuery(text) {
    const patterns = [
        /donde\s+(?:esta|está|anda|and[aá])\s+(.+)/i,
        /dónde\s+(?:esta|está|anda|and[aá])\s+(.+)/i,
        /ubicaci[oó]n\s+(?:de\s+)?(.+)/i,
        /localiza\s+(?:a\s+)?(.+)/i,
        /rastrea\s+(?:a\s+)?(.+)/i,
        /gps\s+(?:de\s+)?(.+)/i,
    ];
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            // Limpiar signos de puntuación y tomar solo la primera palabra como nombre
            let name = match[1].trim().toLowerCase();
            // Quitar puntuación en cualquier posición
            const hasPunctuation = /[¿?!¡.,;:]/.test(name);
            name = name.replace(/[¿?!¡.,;:]/g, '').trim();
            // Si tenía puntuación (parte de una frase), tomar solo la primera palabra.
            // Si no (ej: "tio mario"), conservar el nombre completo.
            if (hasPunctuation) {
                name = name.split(/\s+/)[0];
            }
            if (name && name.length > 1) {
                // Normalizar: convertir apodo a nombre real guardado
                return resolveStoredName(name);
            }
        }
    }
    return null;
}

async function fetchLocation(name) {
    try {
        const encoded = encodeURIComponent(name.toLowerCase());
        const url = GPS_SERVER + "/api/gps/" + encoded;
        const resp = await axios.get(url, { timeout: 10000 });
        if (resp.status === 200) {
            return resp.data;
        }
        return null;
    } catch (e) {
        console.error("[GPS] Error fetching location for " + name + ":", e.message);
        return null;
    }
}

function buildLocationResponse(name, data) {
    // Normalizar nombres
    const nameMap = {
        "martha": "Neca",
        "ñeca": "Martha",
        "neca": "Martha",
        "yoselin": "Yose",
        "yose": "Yoselin",
        "selena": "Sele",
        "sele": "Selena",
        "irene": "Mamá Irene",
        "teresa": "Tere",
        "fernando": "Peloncito",
        "peloncito": "Fernando",
        "guillermo": "Guiye",
        "nestor": "Nes",
        "nés": "Néstor",
        "tucho": "Carlos",
        "carlos": "Tucho",
        "kitty": "Kitty",
        "wanda": "Wanda",
        "ronald": "Ronald",
        "ariel": "Ariel",
        "mario": "Tío Mario",
        "tio mario": "Tío Mario",
        "ocho": "Jorge",
        "jorge": "Ocho",
    };
    const displayName = nameMap[name] || name.charAt(0).toUpperCase() + name.slice(1);

    const age = data.age_minutes;
    const battery = data.battery;
    const mapsUrl = data.maps_url || "";

    let ageText = "";
    if (age != null) {
        if (age < 1) ageText = "ahora mismo";
        else if (age < 60) ageText = "hace " + Math.round(age) + " minutos";
        else ageText = "hace " + Math.round(age / 60) + " horas";
    }

    let batteryText = "";
    if (battery != null) {
        batteryText = ". Batería del teléfono: " + battery + " por ciento";
    }

    let response = displayName + " está aquí";
    if (ageText) response += ". Última ubicación " + ageText;
    response += batteryText;
    if (mapsUrl) response += "\n📍 " + mapsUrl;

    return response;
}

// ── System Prompt ────────────────────────────────────────
const SYSTEM_PROMPT = "Eres Fredy respondiendo por WhatsApp. VIVES EN RUBI, BARCELONA, ESPANA. NO vives en Bolivia. Cuando dices 'aqui' o 'aca' te refieres a Espana. Cuando dices 'alla' o 'por alla' te refieres a Bolivia. COORDENADAS: Tu piso Rubi 41.49N 2.03E (Espana). La Guardia Bolivia 17.89S 63.33W (Sudamerica). 9,500 km de distancia. Responde con frases cortas como un humano por chat. Nunca digas que eres IA o asistente. IMPORTANTE: cuando en un mensaje aparezca [Clima actual: ...] usa ESA temperatura real, NUNCA inventes el clima. Siempre en espanol, sin markdown ni emojis. Cuando alguien te responda, sigue la conversacion con naturalidad. Solo menciona datos personales si te preguntan: eres cristiano, casado con MARTHA, tienes ELA, usas control ocular Tobii 4C. DONDE VIVE CADA UNO (MUY IMPORTANTE): Viven CONTIGO en tu piso en RUBI, ESPANA: MARTHA (tu esposa, le dices Neca) y YOSELIN (Yose, tu hija mayor). Vive CERCA en RUBI, ESPANA: SELENA (Sele, tu hija menor) con ARIEL (su esposo), MIA ALANA (tu nieta bebe) y sus gatos, enfrente de la peluqueria. Viven en BOLIVIA (Santa Cruz / La Guardia): IRENE (tu mama, pelo canoso, te llama Toto), TERESA (tu unica hermana mujer, la mayor), FERNANDO (Peloncito), GUILLERMO (te dice Rorri), NESTOR (te dice Fre). GUILLERMO y FERNANDO viven con tu mama Irene en la casa de tus padres en La Guardia. TERESA vive en su casa en barrio San Jorge. NESTOR vive en su casa en barrio Victoria. TIO MARIO: hermano de tu papa Paulino (fallecido), vive en Santa Cruz, +591 68948058. OCHO (Jorge): padrino civil de tu boda, discoteca y alojamiento en barrio San Jorge La Guardia, quiere volver a Espana, +591 78505604. TUCHO (Carlos Figueroa): vive en Santa Cruz cerca del cuarto anillo, era tu vecino en La Guardia, +591 71662124. KITTY: tu prima (MUJER), vive en La Guardia, hija de Tia Teodora y Almaquio Figueroa, +59170096360. REGLAS DE ORO: 1. Si alguien de Bolivia te manda saludos para Martha o tus hijas, respondes: estan conmigo aqui en Rubi, les doy tus saludos. 2. NUNCA digas que Martha o tus hijas estan en Bolivia. Viven en Espana contigo. 3. Si Tio Mario o alguien pregunta por la familia, dices que todos estan bien AQUI en Espana. 4. Si mencionan 'la mansion' es un lugar de oracion en Santa Cruz, Bolivia. 5. WANDA es tu cuidadora hondurena, auxiliar de enfermeria. RONALD te ayuda con tecnologia. 6. MIA ALANA es tu nieta bebe de 4 meses, pelo negro, ojos oscuros. Si mandan foto de bebe, pregunta si es Mia Alana. ATHENEA es hija de Fernando, tu sobrina. NO es Mia Alana.";

const conversations = new Map();
const MEM_DIR = './conversations';
try { mkdirSync(MEM_DIR, {recursive: true}); } catch(e) {}

function getNumberKey(n) { return n.replace(/[^0-9]/g, ''); }

function loadHistory(n) {
    const key = getNumberKey(n);
    if (!conversations.has(key)) {
        try {
            const f = MEM_DIR + '/' + key + '.json';
            if (existsSync(f)) {
                conversations.set(key, JSON.parse(readFileSync(f, 'utf-8')));
                console.log('[MEM] Cargado:', key);
            } else { conversations.set(key, []); }
        } catch(e) { conversations.set(key, []); }
    }
    return conversations.get(key);
}

function searchHistory(n, query) {
    try {
        const key = getNumberKey(n);
        const f = MEM_DIR + "/" + key + ".json";
        if (!existsSync(f)) return "";
        const all = JSON.parse(readFileSync(f, "utf-8"));
        if (!all || all.length === 0) return "";
        const words = query.toLowerCase().split(/\s+/).filter(w => w.length > 3 && !["hola","como","estas","que","los","las","por","para","una","con","del"].includes(w));
        if (words.length === 0) return "";
        const results = [];
        for (const msg of all) {
            const txt = (msg.text || "").toLowerCase();
            let score = 0;
            for (const w of words) { if (txt.includes(w)) score++; }
            if (score >= 2) { results.push({text: msg.text, time: msg.time, score}); }
        }
        if (results.length > 0) {
            results.sort((a,b) => b.score - a.score);
            const top = results.slice(0, 5);
            return "[Recuerdos encontrados:]\n" + top.map(r => "- " + r.text.substring(0, 200)).join("\n");
        }
    } catch(e) {}
    return "";
}
function saveHistory(n) {
    try {
        const key = getNumberKey(n);
        const h = conversations.get(key);
        if (h && h.length > 0) {
            writeFileSync(MEM_DIR + '/' + key + '.json', JSON.stringify(h.slice(-40)));
        }
    } catch(e) {}
}
function getHistory(n) { return loadHistory(n); }
function addToHistory(n, r, t) { const h = getHistory(n); h.push({role:r, text:t}); if (h.length > MAX_HISTORY*2) h.splice(0,2); saveHistory(n); }


// Open-Meteo clima gratis (sin API key)
const CLIMA_CODES = {0:'despejado',1:'poco nublado',2:'nublado',3:'nublado',45:'niebla',51:'llovizna',53:'llovizna',55:'llovizna',61:'lluvia ligera',63:'lluvia',65:'lluvia fuerte',71:'nieve ligera',73:'nieve',75:'nieve fuerte',80:'lluvia fuerte',81:'lluvia intensa',82:'tormenta',95:'tormenta',96:'tormenta granizo',99:'tormenta granizo'};
async function fetchWeather(lat, lon, tz, label) {
    try {
        const url = 'https://api.open-meteo.com/v1/forecast?latitude=' + lat + '&longitude=' + lon + '&current=temperature_2m,relative_humidity_2m,weather_code&timezone=' + tz;
        const resp = await axios.get(url, { timeout: 8000 });
        const c = resp.data.current;
        const w = CLIMA_CODES[c.weather_code] || 'nublado';
        return label + ': ' + c.temperature_2m + ' grados, ' + w + ', humedad ' + c.relative_humidity_2m + ' por ciento';
    } catch(e) { return null; }
}

// Cadena de modelos: prueba uno por uno automaticamente hasta que funcione
const MODEL_CHAIN = [
    { name: "Cerebras-gemma", url: CEREBRAS_URL, key: CEREBRAS_KEY, model: "gpt-oss-120b", max_tokens: 300, timeout: 15000 },
    { name: "Cerebras-glm", url: CEREBRAS_URL, key: CEREBRAS_KEY, model: "zai-glm-4.7", max_tokens: 500, timeout: 15000 },
    { name: "Cerebras-gpt", url: CEREBRAS_URL, key: CEREBRAS_KEY, model: "gpt-oss-120b", max_tokens: 500, timeout: 15000 },
    { name: "Groq", url: "https://api.groq.com/openai/v1/chat/completions", key: GROQ_KEY, model: GROQ_MODEL, max_tokens: 300, timeout: 20000 },
];

async function callAI(messages) {
    const apiMessages = [{role:"system", content:SYSTEM_PROMPT}, ...messages.map(m => ({role:m.role==="assistant"?"assistant":"user", content:m.text}))];

    for (const cfg of MODEL_CHAIN) {
        try {
            const resp = await axios.post(cfg.url,
                {model: cfg.model, messages: apiMessages, max_tokens: cfg.max_tokens, temperature: 0.7},
                {headers: {"Authorization": "Bearer " + cfg.key, "Content-Type": "application/json"}, timeout: cfg.timeout});
            const content = resp.data?.choices?.[0]?.message?.content;
            if (content && content.trim().length > 0) {
                console.log("[" + cfg.name + "] OK");
                return content;
            }
            console.log("[" + cfg.name + "] Respuesta vacia, probando siguiente...");
        } catch(e) {
            console.error("[" + cfg.name + "]", e.response?.status || e.message);
        }
    }
    return "No puedo responder ahora.";
}

async function analyzeImage(imageBuffer, caption) {
    const base64 = imageBuffer.toString("base64");
    const prompt = caption || "Describe esta imagen en una frase corta, en espanol. Si ves personas, identificalas: mujer mayor pelo canoso=Irene (madre de Fredy), mujer latina pelo oscuro=Martha (esposa, Ñeca), jovenes=Yoselin o Selena (hijas), BEBE de 4 meses con pelo negro y ojos oscuros que no camina=Mia Alana (nieta), nina pequena que ya camina=posiblemente Athenea (sobrina, hija de Peloncito), hombre ayudando=Ronald.";
    try {
        const resp = await axios.post("https://api.groq.com/openai/v1/chat/completions",
            {model: GROQ_VISION_MODEL,
             messages: [{
                role: "user",
                content: [
                    {type: "text", text: prompt},
                    {type: "image_url", image_url: {url: "data:image/jpeg;base64," + base64}}
                ]
             }],
             max_tokens: 200, temperature: 0.7},
            {headers: {"Authorization":"Bearer "+GROQ_KEY,"Content-Type":"application/json"}, timeout: 30000});
        return resp.data.choices[0].message.content;
    } catch(e) { console.error("[Vision]", e.response?.data || e.message); return null; }
}

async function transcribeAudio(audioPath) {
    try {
        const audio = readFileSync(audioPath);
        const boundary = "----WhisperBoundary" + Date.now();
        const header = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.ogg\"\r\nContent-Type: audio/ogg\r\n\r\n";
        const footer = "\r\n--" + boundary + "\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n" + GROQ_STT_MODEL + "\r\n--" + boundary + "\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nes\r\n--" + boundary + "--";
        const body = Buffer.concat([Buffer.from(header), audio, Buffer.from(footer)]);
        const resp = await axios.post("https://api.groq.com/openai/v1/audio/transcriptions", body, {
            headers: { "Authorization": "Bearer " + GROQ_KEY, "Content-Type": "multipart/form-data; boundary=" + boundary },
            timeout: 30000
        });
        return resp.data.text || "";
    } catch(e) {
        console.error("[STT]", e.response?.data || e.message);
        return "";
    }
}

async function textToSpeech(text) {
    const id = Date.now() + "_" + Math.random().toString(36).substring(2,6);
    const tmpFile = join(AUDIO_DIR, "resp_" + id + ".mp3");
    const outFile = join(AUDIO_DIR, "resp_" + id + ".ogg");
    try {
        let cleanText = text.replace(/"/g, "'").replace(/`/g, "'").replace(/\$/g, "").replace(/[;&|]/g, ' ');
        if (cleanText.length > 600) {
            const t = cleanText.substring(0, 600);
            const lastDot = t.lastIndexOf('.');
            const lastComma = t.lastIndexOf(',');
            const lastEx = Math.max(t.lastIndexOf('!'), t.lastIndexOf('?'));
            const cut = Math.max(lastDot, lastComma, lastEx);
            cleanText = cut > 300 ? cleanText.substring(0, cut + 1) : t;
        }
        execSync(EDGE_TTS + " --voice " + TTS_VOICE + " --text \"" + cleanText + "\" --write-media " + tmpFile, {timeout: 30000, stdio: "pipe"});
        if (!existsSync(tmpFile) || readFileSync(tmpFile).length < 100) {
            console.error("[TTS] Archivo MP3 no generado o muy pequeno");
            return null;
        }
        execSync("ffmpeg -y -i " + tmpFile + " -c:a libopus -b:a 16k -ac 1 -ar 16000 -f ogg " + outFile, {timeout: 60000, stdio: "pipe"});
        if (!existsSync(outFile)) {
            console.error("[TTS] Archivo OGG no generado");
            return null;
        }
        const buf = readFileSync(outFile);
        console.log("[TTS] Audio generado:", buf.length, "bytes");
        return buf;
    } catch(e) {
        console.error("[TTS]", e.message);
        return null;
    } finally {
        try { if (existsSync(tmpFile)) unlinkSync(tmpFile); } catch(e) {}
        try { if (existsSync(outFile)) unlinkSync(outFile); } catch(e) {}
    }
}

const CONTACTOS = {
    "gilberto": "5215569782700",
    "gilberto calderon": "5215569782700",
    "wanda": "34602038745",
    "martha": "",
    "irene": "",
    "yoss": "",
    "selena": "",
    "ariel": "",
    "carlos": "",
    "ronald": "",
};

async function processMessage(sock, from, text) {
    const lower = text.toLowerCase().trim(), number = from.replace(/[^0-9]/g, "");
    const MY_NUMBER = "34675315841";

    // ── GPS Query: detectar y responder antes de IA ──
    const gpsName = handleGpsQuery(text);
    if (gpsName) {
        console.log("[GPS] Query detectada para:", gpsName);
        const locationData = await fetchLocation(gpsName);
        if (locationData) {
            const response = buildLocationResponse(gpsName, locationData);
            await sock.sendMessage(from, { text: response });
            console.log("[GPS] Ubicación enviada para:", gpsName);
            return;
        } else {
            // Modificar texto para que IA responda apropiadamente
            text = "[El usuario preguntó por la ubicación GPS de " + gpsName + " pero no hay datos disponibles. Responde diciendo que no sabes dónde está " + gpsName + " y sugiere instalar la app Rastreador Familiar para compartir ubicación.]";
        }
    }

    // Clima: si preguntan, buscar temperatura real
    const climaWords = /temperatura|clima|tiempo|calor|fr[ii]o|lluvia|lloviendo|grados|soleado|nublado|h[uú]medo/i;
    let textWithClima = text;
    if (climaWords.test(text)) {
        try {
            const r = await fetchWeather(41.49, 2.03, 'Europe/Madrid', 'Rubi, Barcelona');
            const g = await fetchWeather(-17.89, -63.33, 'America/La_Paz', 'La Guardia, Bolivia');
            const info = [r, g].filter(Boolean).join('. ');
            if (info) textWithClima = '[Clima actual: ' + info + '] ' + text;
        } catch(e) {}
    }

    // COMANDO: enviar mensaje a otro numero
    const cmdMatch = text.match(/^(\/msg|dile\s+a)\s+(.+?)\s+que\s+(.+)/i);
    if (cmdMatch && number === MY_NUMBER) {
        let target = cmdMatch[2].toLowerCase().trim();
        let msgText = cmdMatch[3];
        let targetNumber = CONTACTOS[target];
        if (!targetNumber && target.startsWith("+")) {
            targetNumber = target.replace(/[^0-9]/g, "");
        }
        if (targetNumber) {
            try {
                await sock.sendMessage(targetNumber + "@s.whatsapp.net", {text: msgText});
                await sock.sendMessage(from, {text: "Enviado a " + cmdMatch[2]});
                console.log("[" + number + "] MSG enviado a " + cmdMatch[2] + ": " + msgText.substring(0, 60));
            } catch(e) {
                await sock.sendMessage(from, {text: "Error al enviar: " + e.message});
            }
        } else {
            await sock.sendMessage(from, {text: "No tengo el numero de " + cmdMatch[2] + ". Dime su numero completo."});
        }
        return;
    }

    // AI CHAT: si Fredy se escribe a si mismo, habla con el asistente
    if (number === MY_NUMBER) {
        addToHistory(number, "user", text);
        const reply = await callAI(getHistory(number));
        addToHistory(number, "assistant", reply);
        await sock.sendMessage(from, {text: reply});
        return;
    }

    // OTROS: obtener nombre del contacto
    let contactName = "";
    try { contactName = await sock.getName(from) || ""; } catch(e) {}
    if (!contactName && from.includes("@s.whatsapp.net")) contactName = from.split("@")[0];
    if (!contactName) contactName = from.split("@")[0];

    const senderInfo = contactName ? "[Mensaje de " + contactName + " (" + number + ")] " : "";

    if (lower === "/start" || lower === "hola") { addToHistory(number,"user",senderInfo + text); const r = "Buenos dias"; addToHistory(number,"assistant",r); await sock.sendMessage(from,{text:r}); return; }
    if (lower === "/reset") { conversations.delete(number); await sock.sendMessage(from,{text:"Listo."}); return; }
    const memSearch = searchHistory(number, textWithClima);
    addToHistory(number,"user", senderInfo + (memSearch ? memSearch + "\n[Mensaje actual:] " : "") + textWithClima);
    const reply = await callAI(getHistory(number));
    addToHistory(number,"assistant",reply);
    await sock.sendMessage(from,{text:reply});
}

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const sock = makeWASocket({
        auth: state,
        logger: pino({ level: "info" }),
        browser: ["Windows", "Chrome", "120.0.0"],
        connectTimeoutMs: 60000,
        keepAliveIntervalMs: 30000,
        markOnlineOnConnect: false
    });
    sock.ev.on("creds.update", saveCreds);
    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;
        if (qr) {
            await QRCode.toFile("/home/fredy/claude-bot/qr.png", qr, { width: 400, margin: 2 });
            writeFileSync("/home/fredy/claude-bot/qr.html", '<html><head><title>QR WhatsApp</title><meta http-equiv=refresh content=15></head><body style="text-align:center;margin-top:30px"><h2>Escanea con WhatsApp</h2><img src=/qr.png width=400 height=400><p>Se actualiza solo</p></body></html>');
            console.log("QR nuevo generado");
        }
        if (connection === "open") { console.log("CONECTADO A WHATSAPP");
    // Saludo diario automatico a la familia (hora Bolivia)
    const FAMILIA_SALUDOS = [
        { nombre: 'Tere', numero: '59179036727', hora: 5, min: 0, dias: [1,2,3,4,5,6] },
        { nombre: 'Tere', numero: '59179036727', hora: 9, min: 0, dias: [0] },
        { nombre: 'Guiye', numero: '59170842494', hora: 9, min: 0, dias: [0,1,2,3,4,5,6] },
        { nombre: 'Peloncito', numero: '59169095959', hora: 9, min: 0, dias: [0,1,2,3,4,5,6] },
        { nombre: 'Nes', numero: '59170821671', hora: 9, min: 0, dias: [0,1,2,3,4,5,6] },
        { nombre: 'Mama', numero: '59170031687', hora: 9, min: 0, dias: [0,1,2,3,4,5,6] },
        { nombre: 'Gilberto', numero: '5215569782700', hora: 11, min: 0, dias: [0,1,2,3,4,5,6] },
    ];
    const sentToday = new Set();
    const sentMonthly = new Set();
    setInterval(() => {
        try {
            const now = new Date();
            const bolivia = new Date(now.toLocaleString('en-US', {timeZone: 'America/La_Paz'}));
            const day = bolivia.getDay();
            const dayOfMonth = bolivia.getDate();
            const mes = bolivia.getMonth();
            const h = bolivia.getHours();
            const m = bolivia.getMinutes();
            const key = day + '-' + h + ':' + m;
            if (sentToday.has(key)) return;
            sentToday.add(key);
            if (sentToday.size > 200) sentToday.clear();
            for (const f of FAMILIA_SALUDOS) {
                if (f.hora === h && f.min === m && f.dias.includes(day)) {
                    sock.sendMessage(f.numero + '@s.whatsapp.net', {text: 'Buenos dias ' + f.nombre}).catch(() => {});
                    console.log('Saludo enviado a ' + f.nombre);
                }
            }
            if (h === 10 && m === 0 && dayOfMonth === 1) {
                const monthlyKey = mes + '-' + dayOfMonth;
                if (!sentMonthly.has(monthlyKey)) {
                    sentMonthly.add(monthlyKey);
                    if (sentMonthly.size > 50) sentMonthly.clear();
                    sock.sendMessage('59171662124@s.whatsapp.net', {text: 'Hola Tucho, solo queria saludarte. Un abrazo.'}).catch(() => {});
                    sock.sendMessage('59170096360@s.whatsapp.net', {text: 'Hola Kitty, solo queria saludarte. Un abrazo.'}).catch(() => {});
                    console.log('Saludo mensual enviado a Tucho y Kitty');
                }
            }
        } catch(e) {}
    }, 60000);
 }
        if (connection === "close") {
            const code = lastDisconnect?.error?.output?.statusCode;
            const msg = lastDisconnect?.error?.message || "sin detalle";
            console.log("DESCONECTADO - code:", code, "msg:", msg);
            const isLoggedOut = code === DisconnectReason.loggedOut;
            if (!isLoggedOut && code) {
                console.log("Reconectando en 5s...");
                setTimeout(startBot, 5000);
            } else {
                console.log("Sesion expirada o error desconocido. Reintentando en 10s...");
                setTimeout(startBot, 10000);
            }
        }
    });
    sock.ev.on("messages.upsert", async ({messages}) => {
        for (const msg of messages) {
            if (!msg.message) continue;
            const from = msg.key.remoteJid;
            if (from.includes("status@broadcast")) continue;
            if (from.includes("@g.us")) continue;
            const chatIsMe = from.includes("34675315841");
            if (msg.key.fromMe && !chatIsMe) continue;
            if (from.includes("@g.us")) continue;

            // Handle audio/voice note
            const audioMsg = msg.message.audioMessage || msg.message.pttMessage;
            if (audioMsg) {
                const sender = from.replace(/@s.whatsapp.net/, "");
                console.log("[" + sender + "] AUDIO recibido");
                try {
                    await sock.sendMessage(from, {react: {text: "🎧", key: msg.key}});
                    const tmpPath = join(AUDIO_DIR, "audio_" + Date.now() + ".ogg");
                    const buf = await downloadMediaMessage(msg, "buffer", {});
                    writeFileSync(tmpPath, buf);
                    console.log("[" + sender + "] Audio descargado:", buf.length, "bytes");
                    const transcript = await transcribeAudio(tmpPath);
                    try { unlinkSync(tmpPath); } catch(e) {}
                    if (!transcript || transcript.trim().length < 2) {
                        await sock.sendMessage(from, {text: "No entendi el audio, puedes escribirlo?"});
                        continue;
                    }
                    console.log("[" + sender + "] Transcrito:", transcript.substring(0, 80));
                    const number = from.replace(/[^0-9]/g, "");

                    // ── GPS Query desde audio ──
                    let audioText = transcript;
                    const gpsName = handleGpsQuery(audioText);
                    if (gpsName) {
                        console.log("[GPS] Query detectada en audio para:", gpsName);
                        const locationData = await fetchLocation(gpsName);
                        if (locationData) {
                            const response = buildLocationResponse(gpsName, locationData);
                            await sock.sendMessage(from, { text: response });
                            continue;
                        } else {
                            // No hay datos GPS, modificar transcript para que la IA responda apropiadamente
                            audioText = "[El usuario preguntó por la ubicación GPS de " + gpsName + " pero no hay datos disponibles. Responde diciendo que no sabes dónde está " + gpsName + " y sugiere instalar la app Rastreador Familiar para compartir ubicación.]";
                        }
                    }

                    addToHistory(number, "user", audioText);
                    const reply = await callAI(getHistory(number));
                    addToHistory(number, "assistant", reply);
                    console.log("[" + sender + "] Respuesta:", reply.substring(0, 80));
                    const audioBuf = await textToSpeech(reply);
                    if (audioBuf) {
                        await sock.sendMessage(from, {audio: audioBuf, mimetype: "audio/ogg; codecs=opus", ptt: true});
                        console.log("[" + sender + "] Audio enviado");
                    } else {
                        await sock.sendMessage(from, {text: reply});
                        console.log("[" + sender + "] Fallback texto enviado");
                    }
                } catch(e) {
                    console.error("[Audio]", e.message);
                    try { await sock.sendMessage(from, {text: "Error al procesar el audio."}); } catch(e2) {}
                }
                continue;
            }

            // Handle image/video
            const imageMsg = msg.message.imageMessage;
            const videoMsg = msg.message.videoMessage;
            if (imageMsg || videoMsg) {
                const sender = from.replace(/@s.whatsapp.net/, "");
                const type = imageMsg ? "IMAGEN" : "VIDEO";
                const caption = (imageMsg || videoMsg).caption || "";
                console.log("[" + sender + "] " + type + " recibido" + (caption ? " - caption: " + caption : ""));
                try {
                    await sock.sendMessage(from, {react: {text: "👁", key: msg.key}});
                    const tmpPath = join(AUDIO_DIR, "media_" + Date.now() + (imageMsg ? ".jpg" : ".mp4"));
                    const buf = await downloadMediaMessage(msg, "buffer", {});
                    writeFileSync(tmpPath, buf);
                    console.log("[" + sender + "] " + type + " descargado:", buf.length, "bytes");
                    
                    let imageBuf = buf;
                    let framePath = null;
                    if (videoMsg) {
                        framePath = tmpPath + ".jpg";
                        try {
                            execSync('ffmpeg -y -i ' + tmpPath + ' -vframes 1 -q:v 2 ' + framePath, {timeout: 15000, stdio: 'pipe'});
                            if (existsSync(framePath)) {
                                imageBuf = readFileSync(framePath);
                                console.log('Frame extraido:', imageBuf.length, 'bytes');
                            }
                        } catch(ffErr) { console.error('ffmpeg error:', ffErr.message); }
                    }
                    
                    const description = await analyzeImage(imageBuf, caption);
                    try { unlinkSync(tmpPath); } catch(e) {}
                    try { if (framePath) unlinkSync(framePath); } catch(e) {}
                    
                    if (!description) {
                        await sock.sendMessage(from, {text: "No pude ver la " + (imageMsg ? "imagen" : "video") + ", describemela."});
                        continue;
                    }
                    console.log("[" + sender + "] Vision:", description.substring(0, 80));
                    const number = from.replace(/[^0-9]/g, "");
                    const contextText = "[El usuario envio un " + (imageMsg ? "foto" : "video") + (caption ? " con texto: " + caption : "") + ". La IA ve: " + description + "] Responde como Fredy a esto.";
                    addToHistory(number, "user", contextText);
                    const reply = await callAI(getHistory(number));
                    addToHistory(number, "assistant", reply);
                    console.log("[" + sender + "] Respuesta:", reply.substring(0, 80));
                    await sock.sendMessage(from, {text: reply});
                } catch(e) {
                    console.error("[" + type + "]", e.message);
                    try { await sock.sendMessage(from, {text: "Error al procesar la " + (imageMsg ? "imagen" : "video") + "."}); } catch(e2) {}
                }
                continue;
            }

            // Handle location/GPS
            const locationMsg = msg.message.locationMessage;
            if (locationMsg) {
                const sender = from.replace(/@s.whatsapp.net/, "");
                const lat = locationMsg.degreesLatitude;
                const lon = locationMsg.degreesLongitude;
                const addr = locationMsg.address || locationMsg.name || "";
                console.log("[" + sender + "] GPS: " + lat + "," + lon + " (" + addr + ")");

                const locFile = '/home/fredy/whatsapp-bot/ubicaciones.json';
                let ubicaciones = {};
                try { ubicaciones = JSON.parse(readFileSync(locFile, 'utf-8')); } catch(e) {}
                ubicaciones[sender] = { lat, lon, addr, time: new Date().toISOString() };
                writeFileSync(locFile, JSON.stringify(ubicaciones, null, 2));

                let pais = "";
                if (lat > 40 && lat < 44 && lon > -4 && lon < 4) pais = "Espana (Rubi/Barcelona)";
                else if (lat < -15 && lat > -20 && lon < -60 && lon > -65) pais = "Bolivia (Santa Cruz/La Guardia)";
                else if (lat > 19 && lat < 33 && lon < -100 && lon > -117) pais = "Mexico";
                else if (lat > 13 && lat < 15 && lon < -87 && lon > -90) pais = "Honduras";
                else pais = "lat:" + lat.toFixed(4) + " lon:" + lon.toFixed(4);

                const number = from.replace(/[^0-9]/g, "");
                const gpsText = "[El usuario compartio su ubicacion GPS: " + addr + " (" + pais + "). Esta en " + pais + ".]";
                addToHistory(number, "user", gpsText);

                const locCaption = (locationMsg.caption || msg.message.extendedTextMessage?.text || "").trim();
                if (locCaption) {
                    addToHistory(number, "user", "[Dice:] " + locCaption);
                }

                const reply = await callAI(getHistory(number));
                addToHistory(number, "assistant", reply);
                await sock.sendMessage(from, {text: reply});
                continue;
            }

            // Handle text
            const text = msg.message.conversation || msg.message.extendedTextMessage?.text || "";
            if (!text) continue;
            const sender = from.replace(/@s.whatsapp.net/, "");
            console.log("[" + sender + "] " + text.substring(0, 60));
            try { await processMessage(sock, from, text); } catch(e) { console.error(e.message); }
        }
    });
}

console.log("WhatsApp Bot iniciando...");
startBot().catch(e => console.error(e));
