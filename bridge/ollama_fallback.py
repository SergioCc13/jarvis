#!/usr/bin/env python3
"""Offline LLM fallback: reply from a local Ollama backend when `claude` is
unavailable (session/usage limit, timeout, crash).

Shared by bridge/telegram_bot.py (and available to bridge/server.py). Stdlib only.

Config (bridge/.env), same names bridge/server.py already documents:
  JARVIS_OLLAMA_BACKENDS    comma-separated IPs running Ollama on :11434,
                            in priority order (put 127.0.0.1 last)
  JARVIS_OLLAMA_MODEL       model for remote backends   (default qwen2.5:7b)
  JARVIS_OLLAMA_MODEL_LOCAL model for 127.0.0.1/localhost (default qwen2.5:3b)
  JARVIS_OLLAMA_TIMEOUT     seconds to wait for the reply (default 300 — a
                            cold 7B load can take minutes)
  JARVIS_OLLAMA_KEEP_ALIVE  how long Ollama keeps the model resident (default 30m)
"""
import json
import os
import socket
import urllib.error
import urllib.request

_IPS = [ip.strip() for ip in os.environ.get("JARVIS_OLLAMA_BACKENDS", "").split(",") if ip.strip()]
MODEL       = os.environ.get("JARVIS_OLLAMA_MODEL", "qwen2.5:7b")
MODEL_LOCAL = os.environ.get("JARVIS_OLLAMA_MODEL_LOCAL", "qwen2.5:3b")
TIMEOUT     = int(os.environ.get("JARVIS_OLLAMA_TIMEOUT", "300"))
KEEP_ALIVE  = os.environ.get("JARVIS_OLLAMA_KEEP_ALIVE", "30m")
SYSTEM      = ("Eres Jarvis, un asistente personal de IA. Responde siempre en "
              "español, de forma concisa y directa.")

_history = []  # persists for the life of the process


def available() -> bool:
    """True if at least one Ollama backend is configured."""
    return bool(_IPS)


def _reachable(ip, port=11434, timeout=2):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _tags(ip):
    """Model names installed on a backend, or empty set if /api/tags fails."""
    try:
        with urllib.request.urlopen(f"http://{ip}:11434/api/tags", timeout=5) as r:
            return {m["name"] for m in json.loads(r.read()).get("models", [])}
    except Exception:
        return set()


def _model_for(ip):
    """A model that actually exists on this backend (configured tag → same
    family → anything). A reachable port does not mean the model was pulled."""
    want = MODEL_LOCAL if ip in ("127.0.0.1", "localhost") else MODEL
    tags = _tags(ip)
    if not tags:
        return want  # /api/tags failed; try the configured model blindly
    if want in tags:
        return want
    base = want.split(":", 1)[0]
    family = sorted(t for t in tags if t.split(":", 1)[0] == base)
    return family[0] if family else sorted(tags)[0]


def ask(text, keep_history=True):
    """Return (reply, model, ip) from the first working Ollama backend.

    Raises RuntimeError naming every backend failure if none can answer.
    """
    global _history
    tried = []
    for ip in _IPS:
        if not _reachable(ip):
            tried.append(f"{ip}: puerto 11434 cerrado")
            continue
        model = _model_for(ip)
        msgs = [{"role": "system", "content": SYSTEM}]
        if keep_history:
            msgs += _history[-30:]
        msgs.append({"role": "user", "content": text})
        payload = json.dumps({
            "model": model, "messages": msgs, "stream": False,
            "keep_alive": KEEP_ALIVE,
        }).encode()
        req = urllib.request.Request(
            f"http://{ip}:11434/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            tried.append(f"{ip} ({model}): HTTP {e.code} {e.read().decode(errors='replace')[:120]}")
            continue
        except Exception as e:
            tried.append(f"{ip} ({model}): {type(e).__name__}: {e}")
            continue
        if data.get("error"):
            tried.append(f"{ip} ({model}): {data['error']}")
            continue
        reply = (data.get("message") or {}).get("content", "").strip()
        if not reply:
            tried.append(f"{ip} ({model}): respuesta vacía")
            continue
        if keep_history:
            _history.append({"role": "user", "content": text})
            _history.append({"role": "assistant", "content": reply})
        return reply, model, ip

    raise RuntimeError("ningún backend Ollama respondió — "
                       + " | ".join(tried or ["JARVIS_OLLAMA_BACKENDS vacío"]))


if __name__ == "__main__":  # quick manual test: python3 bridge/ollama_fallback.py "hola"
    import sys
    q = " ".join(sys.argv[1:]) or "Di 'hola' en una palabra."
    if not available():
        sys.exit("JARVIS_OLLAMA_BACKENDS no configurado")
    try:
        reply, model, ip = ask(q, keep_history=False)
        print(f"[{model} @ {ip}] {reply}")
    except RuntimeError as e:
        sys.exit(str(e))
