#!/usr/bin/env python3
"""Jarvis Telegram bot — bidirectional conversation via long-polling.

Reads JARVIS_TELEGRAM_TOKEN and JARVIS_TELEGRAM_CHAT_ID from env.
Each incoming message is passed to `claude -p` and the reply is sent
back as a voice note (if Kokoro is running) or plain text.

Run on the Pi:
    source bridge/.env && python3 bridge/telegram_bot.py

Add JARVIS_TG_VOICE=0 to bridge/.env to force text-only replies.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ollama_fallback  # noqa: E402  (bridge/ollama_fallback.py)
from session_lock import claude_session_lock  # noqa: E402  (bridge/session_lock.py)

TOKEN          = os.environ.get("JARVIS_TELEGRAM_TOKEN", "")
ALLOWED_ID     = int(os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "0") or 0)
KOKORO_URL     = os.environ.get("VOICEMODE_TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
TTS_VOICE      = os.environ.get("JARVIS_TTS_VOICE", "af_sky")
VOICE_REPLIES  = os.environ.get("JARVIS_TG_VOICE", "1") == "1"
POLL_TIMEOUT   = 30  # seconds for long-poll

BRIDGE_DIR   = os.path.dirname(os.path.abspath(__file__))
JARVIS_DIR   = os.path.dirname(BRIDGE_DIR)
CONFIG_PATH  = os.path.join(BRIDGE_DIR, "config.json")


# ── Telegram helpers ──────────────────────────────────────────────────

def _tg_post(method, payload=None, data=None, content_type="application/json", timeout=35):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": content_type},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_updates(offset=None):
    params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    return _tg_post("getUpdates", params, timeout=POLL_TIMEOUT + 10)


def send_typing(chat_id):
    try:
        _tg_post("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def send_text(chat_id, text):
    _tg_post("sendMessage", {"chat_id": chat_id, "text": text})


def send_voice(chat_id, mp3_bytes):
    boundary = "----jarvistgvoice"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="voice"; filename="reply.mp3"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + mp3_bytes + f"\r\n--{boundary}--\r\n".encode()
    _tg_post(
        "sendVoice",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}",
        timeout=40,
    )


# ── local services ────────────────────────────────────────────────────

def _load_cfg():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _save_cfg(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# Frases que `claude -p` emite por stdout cuando NO ha respondido (límite de
# sesión/uso). Mismo criterio que agents/analistas.py.
_LIMIT_MARKERS = ("session limit", "usage limit", "hit your limit", "quota",
                  "rate limit", "resets ", "please try again later")


def _ollama_reply(message, why):
    """Try the offline Ollama fallback. Returns a formatted reply or None."""
    if not ollama_fallback.available():
        return None
    try:
        reply, model, ip = ollama_fallback.ask(message)
    except Exception as e:
        print(f"[tg] Ollama también falló: {e}")
        return None
    where = "Pi" if ip in ("127.0.0.1", "localhost") else ip
    print(f"[tg] Claude no disponible ({why}) → Ollama {model} @ {ip}")
    return f"⚠️ Claude no disponible. Uso Ollama ({model}) en {where}.\n\n{reply}"


def ask_claude(message):
    """Pass message to claude -p using the shared bridge session.
    Falls back to a local Ollama backend if claude is unavailable."""
    cfg = _load_cfg()
    session_id = cfg.get("session_id")
    started    = cfg.get("session_started", False)

    args = ["claude", "-p", message, "--output-format", "json"]
    if session_id and started:
        args += ["--resume", session_id]
    elif session_id:
        args += ["--session-id", session_id]

    try:
        # one `claude --resume <session>` at a time (the HUD bridge shares it)
        with claude_session_lock():
            result = subprocess.run(
                args, cwd=JARVIS_DIR, capture_output=True, text=True, timeout=120,
            )
    except TimeoutError as e:
        return _ollama_reply(message, f"sesión ocupada: {e}") or f"(ocupado: {e})"
    except subprocess.TimeoutExpired:
        return _ollama_reply(message, "timeout") or "(claude: timeout, y sin Ollama disponible)"
    except OSError as e:
        return _ollama_reply(message, f"no se pudo lanzar claude: {e}") or f"(error claude: {e})"

    low = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode != 0 or any(m in low for m in _LIMIT_MARKERS):
        why = (result.stderr or result.stdout or "código " + str(result.returncode))[-200:]
        return _ollama_reply(message, why) or f"(error claude: {result.stderr[-300:] or result.stdout[-300:]})"

    try:
        data  = json.loads(result.stdout)
        reply = data.get("result", "").strip()
    except Exception:
        reply = result.stdout.strip()

    if not reply:
        return _ollama_reply(message, "respuesta vacía") or "(sin respuesta)"

    # Mark session as started so future calls use --resume
    if session_id and not started and reply:
        cfg["session_started"] = True
        _save_cfg(cfg)

    return reply


def synthesize(text):
    """Generate MP3 via local Kokoro. Returns None if unavailable."""
    payload = json.dumps({
        "model": "tts-1", "input": text,
        "voice": TTS_VOICE, "response_format": "mp3",
    }).encode()
    req = urllib.request.Request(
        KOKORO_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception:
        return None


# ── message handler ───────────────────────────────────────────────────

def handle(msg):
    chat_id = msg["chat"]["id"]
    text    = msg.get("text", "").strip()

    if chat_id != ALLOWED_ID:
        print(f"[tg] mensaje ignorado de chat desconocido: {chat_id}")
        return

    if not text:
        return

    if text.lower() in ("/start", "/help", "hola", "start"):
        send_text(chat_id, "Jarvis online. ¿En qué puedo ayudarte?")
        return

    print(f"[tg] → {text[:80]}")
    send_typing(chat_id)

    reply = ask_claude(text)
    print(f"[tg] ← {reply[:80]}")

    if VOICE_REPLIES:
        mp3 = synthesize(reply)
        if mp3:
            send_voice(chat_id, mp3)
            return

    send_text(chat_id, reply)


# ── main loop ─────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        sys.exit("ERROR: JARVIS_TELEGRAM_TOKEN no configurado en bridge/.env")
    if not ALLOWED_ID:
        sys.exit("ERROR: JARVIS_TELEGRAM_CHAT_ID no configurado en bridge/.env")

    print(f"[tg] Bot iniciado — escuchando mensajes de chat_id={ALLOWED_ID}")

    offset = None
    while True:
        try:
            result = get_updates(offset=offset)
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle(update["message"])
        except KeyboardInterrupt:
            print("[tg] Detenido.")
            break
        except urllib.error.URLError as e:
            print(f"[tg] Red: {e} — reintentando en 10s")
            time.sleep(10)
        except Exception as e:
            print(f"[tg] Error: {e} — reintentando en 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
