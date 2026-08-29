#!/usr/bin/env python3
"""Voice bridge: phone mic -> whisper STT -> claude (headless, resumed phone session) -> kokoro TTS -> phone speaker.

Runs as a plain HTTP server on localhost; reached from the phone via
`tailscale serve` HTTPS termination (mic access requires a secure context).

Also acts as the Jarvis hub: device agents on Mac/PC register here via
POST /register, and Jarvis (Claude) can list them with GET /devices.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
JARVIS_DIR = os.environ.get("JARVIS_DIR", os.path.dirname(BRIDGE_DIR))
CONFIG_PATH = os.path.join(BRIDGE_DIR, "config.json")
DEVICES_PATH = os.path.join(BRIDGE_DIR, "devices.json")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "ef_dora")
PORT = 8792

# Load bridge/.env so JARVIS_VOICE_BACKENDS and other vars are available
def _load_env():
    env_file = os.path.join(BRIDGE_DIR, ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()

# ── voice backend selection ───────────────────────────────────────────────────
# JARVIS_VOICE_BACKENDS = comma-separated Tailscale IPs of devices running
# Whisper (port 2022) and Kokoro/Piper (port 8880), in priority order.
# Pi's own services (127.0.0.1) are always the last fallback.
_BACKEND_IPS = [
    ip.strip()
    for ip in os.environ.get("JARVIS_VOICE_BACKENDS", "").split(",")
    if ip.strip()
] + ["127.0.0.1"]

_backend_cache = {"ip": None, "ts": 0}
_BACKEND_TTL = 60  # re-check every 60 s


def _reachable(ip, port=2022, timeout=2):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pick_backend():
    """Return the first reachable IP (STT port 2022). Cached for 60 s."""
    now = time.time()
    if _backend_cache["ip"] and now - _backend_cache["ts"] < _BACKEND_TTL:
        return _backend_cache["ip"]
    for ip in _BACKEND_IPS:
        if _reachable(ip):
            if ip != _backend_cache["ip"]:
                sys.stderr.write(f"[bridge] voice backend → {ip}\n")
            _backend_cache.update({"ip": ip, "ts": now})
            return ip
    _backend_cache.update({"ip": "127.0.0.1", "ts": now})
    return "127.0.0.1"


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    changed = False
    if "token" not in cfg:
        cfg["token"] = uuid.uuid4().hex
        changed = True
    if "session_id" not in cfg:
        cfg["session_id"] = str(uuid.uuid4())
        cfg["session_started"] = False
        changed = True
    if changed:
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


CONFIG = load_config()

# Write token to HUD so the dashboard can connect without manual token entry
def _write_hud_config():
    hud_dir = os.path.join(JARVIS_DIR, "hud")
    os.makedirs(hud_dir, exist_ok=True)
    with open(os.path.join(hud_dir, "jarvis-config.js"), "w") as f:
        f.write(f'window.__JARVIS_TOKEN = "{CONFIG["token"]}";\n')

_write_hud_config()


# ── device registry ──────────────────────────────────────────────────────────

def load_devices():
    if os.path.exists(DEVICES_PATH):
        with open(DEVICES_PATH) as f:
            return json.load(f)
    return {}


def save_devices(devices):
    with open(DEVICES_PATH, "w") as f:
        json.dump(devices, f, indent=2)


def _notify_async(message):
    """Fire-and-forget notification (non-blocking)."""
    env_file = os.path.join(BRIDGE_DIR, ".env")
    env = dict(os.environ)
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    subprocess.Popen(
        [sys.executable, os.path.join(BRIDGE_DIR, "notify.py"), "--no-voice", message],
        env=env,
    )


def register_device(info):
    devices = load_devices()
    name = info.get("name", "unknown")
    now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    prev = devices.get(name)
    is_new = prev is None
    is_reconnect = False
    if prev and prev.get("last_seen"):
        try:
            import datetime as _dt
            last_dt = _dt.datetime.strptime(prev["last_seen"], "%Y-%m-%dT%H:%M:%SZ")
            elapsed_min = (_dt.datetime.utcnow() - last_dt).total_seconds() / 60
            if elapsed_min > 5:
                is_reconnect = True
        except Exception:
            pass

    devices[name] = {**info, "last_seen": now_str}
    save_devices(devices)

    if is_new:
        _notify_async(f"🟢 Nuevo dispositivo conectado: {name} ({info.get('platform','?')})")
    elif is_reconnect:
        _notify_async(f"🟢 Dispositivo reconectado: {name}")

    return name


# ── audio / claude ───────────────────────────────────────────────────────────

def transcribe(audio_bytes, content_type):
    backend = _pick_backend()
    stt_url = f"http://{backend}:2022/v1/audio/transcriptions"
    boundary = "----jarvisbridgeboundary"
    ext = "webm" if "webm" in content_type else "wav"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.{ext}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + audio_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        stt_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["text"].strip()


# ── Ollama fallback ───────────────────────────────────────────────────────────
# JARVIS_OLLAMA_BACKENDS = comma-separated Tailscale IPs running Ollama (port 11434)
# JARVIS_OLLAMA_MODEL    = model to use (default: qwen2.5:7b)
_OLLAMA_IPS = [
    ip.strip()
    for ip in os.environ.get("JARVIS_OLLAMA_BACKENDS", "").split(",")
    if ip.strip()
]
OLLAMA_MODEL = os.environ.get("JARVIS_OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_SYSTEM = (
    "Eres Jarvis, un asistente personal de IA. Responde siempre en español, "
    "de forma concisa y directa. Puedes ejecutar tareas en el sistema cuando el "
    "usuario lo pida."
)
_ollama_history = []  # persists for the session


def _pick_ollama():
    """Return first reachable Ollama IP, or None."""
    for ip in _OLLAMA_IPS:
        if _reachable(ip, port=11434):
            return ip
    return None


def _ask_ollama(ip, text):
    global _ollama_history
    _ollama_history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": OLLAMA_SYSTEM}] + _ollama_history[-30:]
    payload = json.dumps({"model": OLLAMA_MODEL, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        f"http://{ip}:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    reply = data["message"]["content"].strip()
    _ollama_history.append({"role": "assistant", "content": reply})
    return reply


def ask_claude(text):
    args = ["claude", "-p", text, "--output-format", "json"]
    if CONFIG.get("session_started"):
        args += ["--resume", CONFIG["session_id"]]
    else:
        args += ["--session-id", CONFIG["session_id"]]
    result = subprocess.run(args, cwd=JARVIS_DIR, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[-2000:]}")
    data = json.loads(result.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude error: {data.get('result')}")
    if not CONFIG.get("session_started"):
        CONFIG["session_started"] = True
        save_config(CONFIG)
    return data["result"]


def ask(text):
    """Try Claude first; fall back to Ollama if Claude fails."""
    try:
        return ask(text)
    except Exception as e:
        ollama_ip = _pick_ollama()
        if ollama_ip:
            sys.stderr.write(f"[bridge] Claude failed ({type(e).__name__}), falling back to Ollama on {ollama_ip}\n")
            return f"[Ollama/{OLLAMA_MODEL}] " + _ask_ollama(ollama_ip, text)
        raise


def synthesize(text):
    backend = _pick_backend()
    tts_url = f"http://{backend}:8880/v1/audio/speech"
    payload = json.dumps(
        {"model": "tts-1", "input": text, "voice": TTS_VOICE, "response_format": "mp3"}
    ).encode()
    req = urllib.request.Request(
        tts_url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


class Handler(BaseHTTPRequestHandler):
    def _send_text(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_chat(self):
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = urllib.parse.parse_qs(qs)
        token = (params.get("token") or [""])[0]
        if token != CONFIG["token"]:
            return self._send_json(401, {"error": "unauthorized"})

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return self._send_json(400, {"error": "empty request"})
        try:
            payload = json.loads(self.rfile.read(length))
            text = (payload.get("text") or "").strip()
        except (ValueError, AttributeError):
            return self._send_json(400, {"error": "expected JSON body with a 'text' field"})
        if not text:
            return self._send_json(400, {"error": "empty text"})

        try:
            reply = ask(text)
        except Exception as e:
            return self._send_json(502, {"error": f"claude failed: {e}"})

        return self._send_json(200, {"reply": reply})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/devices":
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            token = urllib.parse.parse_qs(qs).get("token", [""])[0]
            if token != CONFIG["token"]:
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, load_devices())
        return self._send_text(200, "Jarvis voice bridge is running. POST audio to /voice?token=... or JSON to /chat?token=...")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        # tailscale serve's --set-path=/voice strips that prefix before
        # forwarding, so proxied requests arrive here as "/"; direct/local
        # requests (e.g. curl testing) still use "/voice". "/chat" is routed
        # separately (see set-path=/chat in bin/jarvis) so it never collides
        # with the stripped "/" used by the voice path.
        path = self.path.split("?")[0]

        if path == "/register":
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            reg_token = urllib.parse.parse_qs(qs).get("token", [""])[0]
            if reg_token != CONFIG["token"]:
                return self._send_json(401, {"error": "unauthorized"})
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return self._send_json(400, {"error": "empty body"})
            try:
                info = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send_json(400, {"error": "invalid JSON"})
            name = register_device(info)
            sys.stderr.write(f"[bridge] Device registered: {name}\n")
            return self._send_json(200, {"ok": True, "name": name})

        if path == "/chat":
            return self._handle_chat()
        if path not in ("/", "/voice"):
            return self._send_text(404, "not found")

        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = urllib.parse.parse_qs(qs)
        token = (params.get("token") or [""])[0]
        if token != CONFIG["token"]:
            return self._send_text(401, "unauthorized")

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return self._send_text(400, "no audio")
        audio_bytes = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "audio/webm")

        try:
            transcript = transcribe(audio_bytes, content_type)
        except Exception as e:
            return self._send_text(502, f"stt failed: {e}")

        if not transcript or "[BLANK_AUDIO]" in transcript or "[SILENCIO]" in transcript.upper():
            reply = "No escuché nada, intenta de nuevo."
        else:
            try:
                reply = ask(transcript)
            except Exception as e:
                return self._send_text(502, f"claude failed: {e}")

        try:
            audio = synthesize(reply)
        except Exception as e:
            return self._send_text(502, f"tts failed: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("X-Transcript", urllib.parse.quote(transcript))
        self.send_header("X-Reply", urllib.parse.quote(reply))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "X-Transcript, X-Reply")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def log_message(self, fmt, *args):
        sys.stderr.write("[bridge] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print(f"Voice bridge listening on 0.0.0.0:{PORT}")
    print(f"Token: {CONFIG['token']}")
    print(f"Phone session id: {CONFIG['session_id']}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
