#!/usr/bin/env python3
"""Voice bridge: phone mic -> whisper STT -> claude (headless, resumed phone session) -> kokoro TTS -> phone speaker.

Runs as a plain HTTP server on localhost; reached from the phone via
`tailscale serve` HTTPS termination (mic access requires a secure context).

Also acts as the Jarvis hub: device agents on Mac/PC register here via
POST /register, and Jarvis (Claude) can list them with GET /devices.
"""
import json
import os
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
WHISPER_URL = os.environ.get("VOICEMODE_STT_URL", "http://127.0.0.1:2022/v1/audio/transcriptions")
KOKORO_URL = os.environ.get("VOICEMODE_TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "af_sky")
PORT = 8792


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


# ── device registry ──────────────────────────────────────────────────────────

def load_devices():
    if os.path.exists(DEVICES_PATH):
        with open(DEVICES_PATH) as f:
            return json.load(f)
    return {}


def save_devices(devices):
    with open(DEVICES_PATH, "w") as f:
        json.dump(devices, f, indent=2)


def register_device(info):
    devices = load_devices()
    name = info.get("name", "unknown")
    devices[name] = {**info, "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    save_devices(devices)
    return name


# ── audio / claude ───────────────────────────────────────────────────────────

def transcribe(audio_bytes, content_type):
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
        WHISPER_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["text"].strip()


def ask_claude(text):
    args = ["claude", "-p", text, "--output-format", "json"]
    if CONFIG.get("session_started"):
        args += ["--resume", CONFIG["session_id"]]
    else:
        args += ["--session-id", CONFIG["session_id"]]
    result = subprocess.run(args, cwd=JARVIS_DIR, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[-2000:]}")
    data = json.loads(result.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude error: {data.get('result')}")
    if not CONFIG.get("session_started"):
        CONFIG["session_started"] = True
        save_config(CONFIG)
    return data["result"]


def synthesize(text):
    payload = json.dumps(
        {"model": "tts-1", "input": text, "voice": TTS_VOICE, "response_format": "mp3"}
    ).encode()
    req = urllib.request.Request(
        KOKORO_URL, data=payload, headers={"Content-Type": "application/json"}
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
            reply = ask_claude(text)
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
                reply = ask_claude(transcript)
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
    print(f"Voice bridge listening on 127.0.0.1:{PORT}")
    print(f"Token: {CONFIG['token']}")
    print(f"Phone session id: {CONFIG['session_id']}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
