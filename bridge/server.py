#!/usr/bin/env python3
"""Voice bridge: phone mic -> whisper STT -> claude (headless, resumed phone session) -> kokoro TTS -> phone speaker.

Runs as a plain HTTP server on localhost; reached from the phone via
`tailscale serve` HTTPS termination (mic access requires a secure context).

Also acts as the Jarvis hub: device agents on Mac/PC register here via
POST /register, and Jarvis (Claude) can list them with GET /devices.
"""
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from session_lock import claude_session_lock  # noqa: E402

# ── SSE event bus ─────────────────────────────────────────────────────────────
_sse_clients: list[queue.Queue] = []


def _push_event(payload: dict):
    """Push a JSON event to all connected HUD /events clients."""
    dead = []
    for q in _sse_clients:
        try:
            q.put_nowait(payload)
        except queue.Full:
            dead.append(q)
    for q in dead:
        try:
            _sse_clients.remove(q)
        except ValueError:
            pass

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

# ── fotos desde el HUD (POST /chat/image) ────────────────────────────────────
# Varias imágenes = un mensaje: el cliente sube una por request compartiendo
# ?batch_id= y el análisis solo se dispara al llegar la ?total=.
HUD_MEDIA_DIR = os.path.join(BRIDGE_DIR, "hud_media")
_image_batches = {}                 # batch_id -> {"paths": [...], "text": str}
_image_batch_lock = threading.Lock()
_IMG_EXT = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
            "image/heic": ".heic", "image/jpeg": ".jpg", "image/jpg": ".jpg"}

# ── /chat job state ──────────────────────────────────────────────────────
# /chat and /chat/image used to block the HTTP connection for the whole
# ask() call — if the client navigated away or the phone locked mid-request
# the browser killed the connection and the reply was lost, even though the
# server had finished. Now they kick off a background job and return
# immediately; the client polls /chat/result until it's done, which survives
# backgrounding/reloading (fire the message, come back later, like Telegram).
# A single global slot dropped the earlier reply whenever a second message was
# sent before the first finished (the poller for the first then got a 404 —
# "la respuesta se perdió"). Keep the last few jobs, keyed by id.
_job_lock = threading.Lock()
_jobs: dict[str, dict] = {}
_JOBS_MAX = 8


def _job_snapshot(job_id):
    with _job_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def _start_chat_job(prompt):
    job_id = uuid.uuid4().hex
    with _job_lock:
        _jobs[job_id] = {"id": job_id, "status": "pending", "reply": None,
                         "error": None, "ts": time.time()}
        while len(_jobs) > _JOBS_MAX:
            _jobs.pop(min(_jobs, key=lambda k: _jobs[k]["ts"]), None)

    def worker():
        try:
            reply = ask(prompt)
            with _job_lock:
                if job_id in _jobs:
                    _jobs[job_id].update({"status": "done", "reply": reply})
        except Exception as e:
            with _job_lock:
                if job_id in _jobs:
                    _jobs[job_id].update({"status": "error", "error": f"claude failed: {e}"})

    threading.Thread(target=worker, daemon=True).start()
    return job_id

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

# Whisper transcription hints. Language stays Spanish (the user is understood
# better that way); the prompt seeds the decoder with the proper nouns Jarvis
# deals with so they aren't mangled ("Ragavan", "Cardmarket", device names…).
STT_LANGUAGE = os.environ.get("JARVIS_STT_LANGUAGE", "es")
STT_PROMPT = os.environ.get(
    "JARVIS_STT_PROMPT",
    "Conversación en español con Jarvis, el asistente. Puede mencionar: "
    "Cardmarket, Scryfall, Magic, Lorcana, YuGiOh, Pokémon, Ragavan, "
    "Tailscale, Telegram, watchlist, Bitcoin, Ethereum, Claude, Ollama.",
)


def _mp_field(boundary, name, value):
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
    ).encode()


def transcribe(audio_bytes, content_type):
    backend = _pick_backend()
    stt_url = f"http://{backend}:2022/v1/audio/transcriptions"
    boundary = "----jarvisbridgeboundary"
    ext = "webm" if "webm" in content_type else "wav"
    body = (
        _mp_field(boundary, "model", "whisper-1")
        + _mp_field(boundary, "language", STT_LANGUAGE)
        + _mp_field(boundary, "prompt", STT_PROMPT)
        + (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.{ext}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + audio_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        stt_url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["text"].strip()


# ── Fallback chain: Claude → free cloud → Ollama backends ─────────────────────
# JARVIS_CLOUD_URL/KEY/MODEL = optional OpenAI-compatible endpoint (Groq, Gemini,
#                             OpenRouter…) tried when Claude fails, before the
#                             local Ollama backends. Leave URL blank to skip.
# JARVIS_OLLAMA_BACKENDS    = comma-separated Ollama backends (port 11434), in
#                             priority order. Each entry is IP or IP=model, so a
#                             32 GB box can run a bigger tag than an 8 GB one.
#                             Bare IPs use JARVIS_OLLAMA_MODEL (or _MODEL_LOCAL
#                             for 127.0.0.1).
# JARVIS_OLLAMA_MODEL       = model for remote backends (default: qwen2.5:7b)
# JARVIS_OLLAMA_MODEL_LOCAL = model for 127.0.0.1 Pi-local (default: qwen2.5:3b)
CLOUD_URL = os.environ.get("JARVIS_CLOUD_URL", "").strip()
CLOUD_KEY = os.environ.get("JARVIS_CLOUD_KEY", "").strip()
CLOUD_MODEL = os.environ.get("JARVIS_CLOUD_MODEL", "").strip()


def _parse_backends(raw):
    """['1.2.3.4=qwen2.5:32b', '127.0.0.1'] -> [('1.2.3.4', 'qwen2.5:32b'), ('127.0.0.1', None)]"""
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        ip, _, model = item.partition("=")
        out.append((ip.strip(), model.strip() or None))
    return out


_OLLAMA_BACKENDS = _parse_backends(os.environ.get("JARVIS_OLLAMA_BACKENDS", ""))
OLLAMA_MODEL = os.environ.get("JARVIS_OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_MODEL_LOCAL = os.environ.get("JARVIS_OLLAMA_MODEL_LOCAL", "qwen2.5:3b")
OLLAMA_SYSTEM = (
    "Eres Jarvis, un asistente personal de IA. Responde siempre en español, "
    "de forma concisa y directa. Puedes ejecutar tareas en el sistema cuando el "
    "usuario lo pida."
)
_ollama_history = []  # persists for the session
# First call loads the model into RAM (a 7B on CPU can take minutes); the old
# 120 s ceiling made that show up as a silent timeout. keep_alive stops Ollama
# from evicting the model between messages.
OLLAMA_TIMEOUT = int(os.environ.get("JARVIS_OLLAMA_TIMEOUT", "300"))
OLLAMA_KEEP_ALIVE = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m")


def _ollama_tags(ip):
    """Return the set of model names installed on an Ollama backend (empty on failure)."""
    try:
        with urllib.request.urlopen(f"http://{ip}:11434/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        return {m["name"] for m in data.get("models", [])}
    except Exception:
        return set()


def _ollama_model_for(ip, hint=None):
    """Pick a model that actually exists on this backend.

    A reachable port does not mean the configured model was ever pulled; asking
    for a missing model just returns an HTTP 404 that used to surface as a dead
    fallback. Prefer the per-backend hint (IP=model), then the configured tag,
    then any same-family tag, then anything. Returns None only when /api/tags
    succeeded and the backend has no models.
    """
    want = hint or (OLLAMA_MODEL_LOCAL if ip in ("127.0.0.1", "localhost") else OLLAMA_MODEL)
    tags = _ollama_tags(ip)
    if not tags:
        return want  # tags endpoint failed; try the configured model blindly
    if want in tags:
        return want
    base = want.split(":", 1)[0]
    family = sorted(t for t in tags if t.split(":", 1)[0] == base)
    if family:
        return family[0]
    return sorted(tags)[0]


def _ask_ollama(ip, text, model):
    global _ollama_history
    _ollama_history.append({"role": "user", "content": text})
    messages = [{"role": "system", "content": OLLAMA_SYSTEM}] + _ollama_history[-30:]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }).encode()
    req = urllib.request.Request(
        f"http://{ip}:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"ollama {ip} HTTP {e.code}: {detail}") from None
    except Exception as e:
        raise RuntimeError(f"ollama {ip} unreachable: {type(e).__name__}: {e}") from None
    if data.get("error"):
        raise RuntimeError(f"ollama {ip}: {data['error']}")
    reply = (data.get("message") or {}).get("content", "").strip()
    if not reply:
        raise RuntimeError(f"ollama {ip}: empty response ({json.dumps(data)[:200]})")
    _ollama_history.append({"role": "assistant", "content": reply})
    return reply


def ask_claude(text):
    args = ["claude", "-p", text, "--output-format", "json"]
    if CONFIG.get("session_started"):
        args += ["--resume", CONFIG["session_id"]]
    else:
        args += ["--session-id", CONFIG["session_id"]]
    # Serialise with the Telegram bot: both --resume the SAME session id, and
    # two concurrent `claude --resume` can corrupt it.
    with claude_session_lock():
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


_ollama_active = False  # track whether we already notified about the switch
_cloud_active = False


def _ask_cloud(text):
    """One call to an OpenAI-compatible chat endpoint (Groq / Gemini / OpenRouter…)."""
    messages = (
        [{"role": "system", "content": OLLAMA_SYSTEM}]
        + _ollama_history[-30:]
        + [{"role": "user", "content": text}]
    )
    payload = json.dumps({"model": CLOUD_MODEL, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        CLOUD_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {CLOUD_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"cloud HTTP {e.code}: {detail}") from None
    except Exception as e:
        raise RuntimeError(f"cloud unreachable: {type(e).__name__}: {e}") from None
    try:
        reply = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"cloud: bad response ({json.dumps(data)[:200]})") from None
    if not reply:
        raise RuntimeError("cloud: empty response")
    _ollama_history.append({"role": "user", "content": text})
    _ollama_history.append({"role": "assistant", "content": reply})
    return reply


def _cloud_fallback(text, claude_err):
    """Tier between Claude and the local Ollama backends: a free hosted model."""
    global _cloud_active
    if not (CLOUD_URL and CLOUD_KEY and CLOUD_MODEL):
        raise RuntimeError("JARVIS_CLOUD_* not configured")
    sys.stderr.write(
        f"[bridge] Claude failed ({type(claude_err).__name__}: {claude_err}); "
        f"trying cloud ({CLOUD_MODEL})\n"
    )
    # Ask first — only mark the tier "active" (and notify) once it actually
    # replies. Setting the flag before the call meant a failed attempt left
    # it stuck True, silently skipping the switch notice on the next success.
    reply = _ask_cloud(text)
    if not _cloud_active:
        _cloud_active = True
        msg = f"Claude no disponible. Usando {CLOUD_MODEL} (nube)."
        _notify_async("⚠️ " + msg)
        _push_event({"type": "notice", "text": "⚠️ " + msg})
    return reply


def _ollama_fallback(text, claude_err):
    """Walk every configured Ollama backend and return the first real reply.

    The old code stopped at the first backend whose port was open and never
    tried the next one, so a reachable-but-broken backend (missing model, OOM)
    killed the whole fallback. Here every backend gets a turn and, if they all
    fail, the raised error names each failure instead of a bare 502.
    """
    global _ollama_active
    tried = []
    for ip, hint in _OLLAMA_BACKENDS:
        if not _reachable(ip, port=11434):
            tried.append(f"{ip}: port 11434 closed")
            continue
        model = _ollama_model_for(ip, hint)
        if not model:
            tried.append(f"{ip}: no model installed (ollama pull {OLLAMA_MODEL})")
            continue
        where = "Pi" if ip in ("127.0.0.1", "localhost") else ip
        sys.stderr.write(
            f"[bridge] Claude failed ({type(claude_err).__name__}: {claude_err}); "
            f"trying Ollama ({model}) on {ip}\n"
        )
        # Ask first — only mark the tier "active" (and notify) once it actually
        # replies, same reasoning as _cloud_fallback above.
        try:
            reply = _ask_ollama(ip, text, model)
        except Exception as e:
            sys.stderr.write(f"[bridge] Ollama {ip} failed: {e}\n")
            tried.append(str(e))
            continue
        if not _ollama_active:
            _ollama_active = True
            msg = f"Claude no disponible. Usando Ollama ({model}) en {where}."
            _notify_async("⚠️ " + msg)
            _push_event({"type": "notice", "text": "⚠️ " + msg})
        return reply
    raise RuntimeError(
        "Claude failed and no Ollama backend answered — "
        + " | ".join(tried or ["JARVIS_OLLAMA_BACKENDS is empty"])
    )


def ask(text):
    """Claude first; then a free cloud model; then the local Ollama backends."""
    global _ollama_active, _cloud_active
    try:
        reply = ask_claude(text)
        if _ollama_active or _cloud_active:
            _ollama_active = _cloud_active = False
            msg = "Claude disponible de nuevo."
            _notify_async("✅ " + msg)
            _push_event({"type": "notice", "text": "✅ " + msg})
        return reply
    except Exception as claude_err:
        errors = []
        for tier in (_cloud_fallback, _ollama_fallback):
            try:
                return tier(text, claude_err)
            except Exception as e:
                errors.append(str(e))
        fb_err = " | ".join(errors)
        sys.stderr.write(f"[bridge] fallback exhausted: {fb_err}\n")
        _push_event({"type": "notice", "text": "❌ " + fb_err})
        raise RuntimeError(fb_err)


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


# Prepended to the transcript on the voice path only (never /chat, which wants
# full formatting). Kept in Spanish on purpose — the reply must stay Spanish.
VOICE_PROMPT_PREFIX = (
    "[Entrada por voz. Responde en español, en 1 o 2 frases cortas, con tono "
    "natural de conversación hablada. Nada de markdown, listas, tablas ni "
    "emojis. Si hace falta más detalle, resúmelo y di que lo amplías en el chat.]\n\n"
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # emoticons, symbols & pictographs, supplemental
    "\U00002600-\U000027BF"  # misc symbols + dingbats
    "\U00002190-\U000021FF"  # arrows
    "\U00002B00-\U00002BFF"  # misc symbols and arrows
    "\U0000FE0F"             # emoji variation selector
    "]"
)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def for_speech(text, max_sentences=3, max_chars=360):
    """Turn Jarvis's reply into something Kokoro can read aloud cleanly:
    no markdown symbols, no code, no URLs, no emojis, and not too long."""
    if not text:
        return ""
    t = text.replace("\r", "")
    # drop fenced code blocks entirely
    t = re.sub(r"```.*?```", " (código) ", t, flags=re.DOTALL)
    t = re.sub(r"~~~.*?~~~", " (código) ", t, flags=re.DOTALL)
    # links [txt](url) -> txt ; images ![alt](url) -> alt
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    # bare URLs
    t = _URL_RE.sub("un enlace", t)
    # inline code and emphasis markers
    t = t.replace("`", "")
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", t)
    # headings, blockquotes, list bullets at line start
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", "", t, flags=re.MULTILINE)
    # tables -> spoken separators
    t = t.replace("|", ", ")
    t = _EMOJI_RE.sub("", t)
    # symbols Kokoro would spell out awkwardly in Spanish
    for sym, word in (
        ("€", " euros"), ("$", " dólares"), ("%", " por ciento"),
        ("&", " y "), ("°", " grados"), ("~", " aproximadamente "),
    ):
        t = t.replace(sym, word)
    # collapse whitespace / stray punctuation from the newline joins
    t = re.sub(r"\s*\n\s*", ". ", t).strip()
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"([:;,])\s*\.", r"\1", t)
    t = re.sub(r"(\.\s*){2,}", ". ", t)
    if not t:
        return ""
    sentences = _SENT_SPLIT_RE.split(t)
    clipped = " ".join(sentences[:max_sentences]).strip()
    if len(clipped) > max_chars:
        clipped = clipped[:max_chars].rsplit(" ", 1)[0] + "…"
    if clipped != t.strip():
        clipped = clipped.rstrip(".…") + ". Te lo amplío en el chat."
    return clipped


class Handler(BaseHTTPRequestHandler):
    def _bearer_token(self):
        """Token from the Authorization header. Query-string ?token= used to be
        the only option, but it leaks into journalctl/access logs and browser
        history — every endpoint except /events (see _handle_events) now takes
        the token exclusively via header."""
        auth = self.headers.get("Authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

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
        if self._bearer_token() != CONFIG["token"]:
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

        job_id = _start_chat_job(text)
        return self._send_json(202, {"job_id": job_id, "status": "pending"})

    def _handle_chat_image(self):
        # Bytes crudos de imagen en el body, caption en ?text=. Multi-imagen:
        # el cliente sube una por request con ?batch_id= y ?total=; el bridge
        # las guarda en bridge/hud_media/ y, cuando llegan todas, se las pasa a
        # Claude (que las abre con su herramienta de lectura de archivos).
        if self._bearer_token() != CONFIG["token"]:
            return self._send_json(401, {"error": "unauthorized"})

        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = urllib.parse.parse_qs(qs)
        text = (params.get("text") or [""])[0].strip()
        batch_id = (params.get("batch_id") or [""])[0] or uuid.uuid4().hex
        try:
            total = max(1, int((params.get("total") or ["1"])[0]))
        except ValueError:
            total = 1

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return self._send_json(400, {"error": "empty image"})
        image_bytes = self.rfile.read(length)
        ct = self.headers.get("Content-Type", "image/jpeg").split(";")[0].strip().lower()
        ext = _IMG_EXT.get(ct, ".jpg")

        os.makedirs(HUD_MEDIA_DIR, exist_ok=True)
        image_path = os.path.join(HUD_MEDIA_DIR, f"{uuid.uuid4().hex}{ext}")
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        with _image_batch_lock:
            batch = _image_batches.setdefault(batch_id, {"paths": [], "text": ""})
            batch["paths"].append(image_path)
            if text:
                batch["text"] = text
            if len(batch["paths"]) < total:
                return self._send_json(200, {"status": "staged",
                                             "received": len(batch["paths"]), "total": total})
            paths = batch["paths"]
            caption = batch["text"]
            _image_batches.pop(batch_id, None)

        images_block = "\n".join(f"[Imagen adjunta en: {p}]" for p in paths)
        n = len(paths)
        prompt = (
            f"El usuario ha adjuntado {n} imagen{'es' if n != 1 else ''} desde el HUD. "
            "Ábrelas con tu herramienta de lectura de archivos y respóndele en español.\n\n"
            + (f"Mensaje del usuario: {caption}\n\n" if caption else "")
            + images_block
        )
        job_id = _start_chat_job(prompt)
        return self._send_json(202, {"job_id": job_id, "status": "pending"})

    def _handle_chat_result(self):
        if self._bearer_token() != CONFIG["token"]:
            return self._send_json(401, {"error": "unauthorized"})
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        params = urllib.parse.parse_qs(qs)
        job_id = (params.get("job_id") or [""])[0]
        job = _job_snapshot(job_id)
        if not job:
            return self._send_json(404, {"status": "unknown"})
        return self._send_json(200, job)

    def _handle_events(self):
        # Only endpoint that still allows ?token= — the browser's native
        # EventSource API cannot set custom headers, so there's no way for
        # hud/index.html's `new EventSource(url)` to send a Bearer token.
        # Header still takes priority for any future non-browser client.
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        token = self._bearer_token() or urllib.parse.parse_qs(qs).get("token", [""])[0]
        if token != CONFIG["token"]:
            return self._send_json(401, {"error": "unauthorized"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        q: queue.Queue = queue.Queue(maxsize=50)
        _sse_clients.append(q)
        try:
            while True:
                try:
                    payload = q.get(timeout=25)
                    self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": ka\n\n")  # keepalive
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            try:
                _sse_clients.remove(q)
            except ValueError:
                pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/events":
            return self._handle_events()
        if path == "/chat/result":
            return self._handle_chat_result()
        if path == "/version":
            try:
                h = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=JARVIS_DIR, text=True).strip()
            except Exception:
                h = "unknown"
            return self._send_json(200, {"hash": h})
        if path == "/devices":
            if self._bearer_token() != CONFIG["token"]:
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, load_devices())
        return self._send_text(200, "Jarvis voice bridge is running. POST audio to /voice or JSON to /chat, both with 'Authorization: Bearer <token>'.")

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
            if self._bearer_token() != CONFIG["token"]:
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
        if path == "/chat/image":
            return self._handle_chat_image()
        if path not in ("/", "/voice"):
            return self._send_text(404, "not found")

        if self._bearer_token() != CONFIG["token"]:
            return self._send_text(401, "unauthorized")

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return self._send_text(400, "no audio")
        audio_bytes = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "audio/webm")

        t0 = time.perf_counter()
        try:
            transcript = transcribe(audio_bytes, content_type)
        except Exception as e:
            return self._send_text(502, f"stt failed: {e}")
        t_stt = time.perf_counter()

        if not transcript or "[BLANK_AUDIO]" in transcript or "[SILENCIO]" in transcript.upper():
            reply = "No escuché nada, intenta de nuevo."
        else:
            try:
                reply = ask(VOICE_PROMPT_PREFIX + transcript)
            except Exception as e:
                return self._send_text(502, f"claude failed: {e}")
        t_llm = time.perf_counter()

        # Hear a short, clean version; the full answer still lands in the chat.
        spoken = for_speech(reply) or "Hecho."
        try:
            audio = synthesize(spoken)
        except Exception as e:
            return self._send_text(502, f"tts failed: {e}")
        t_tts = time.perf_counter()
        sys.stderr.write(
            f"[voice] stt={t_stt - t0:.1f}s llm={t_llm - t_stt:.1f}s "
            f"tts={t_tts - t_llm:.1f}s | «{transcript[:60]}» -> {len(spoken)} chars\n"
        )

        x_reply = reply if len(reply) < 3500 else reply[:3500] + "…"
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("X-Transcript", urllib.parse.quote(transcript))
        self.send_header("X-Reply", urllib.parse.quote(x_reply))
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
