#!/usr/bin/env python3
"""Jarvis device agent — runs on each managed device (Mac, PC, etc.).

On startup, registers with the Pi hub. Then listens for dispatch commands
from Jarvis (Claude) so any device can be controlled remotely over Tailscale.

Usage:
    JARVIS_HUB_URL=http://<pi-tailscale-ip>:8792 \
    JARVIS_DEVICE_NAME=mac-sergio \
    python3 agents/device_agent.py
"""
import hmac
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(AGENT_DIR, "config.json")
PORT = int(os.environ.get("JARVIS_AGENT_PORT", "8793"))
HUB_URL = os.environ.get("JARVIS_HUB_URL", "")
HUB_TOKEN = os.environ.get("JARVIS_HUB_TOKEN", "")
DEVICE_NAME = os.environ.get("JARVIS_DEVICE_NAME", socket.gethostname())
PLATFORM = sys.platform  # darwin | linux | win32

# This agent runs arbitrary shell over HTTP, so keep the exposure tight:
#   - bind to the Tailscale IP, not 0.0.0.0 (override with JARVIS_AGENT_BIND)
#   - accept the token ONLY via the X-Jarvis-Token header — a query-string
#     ?token= fallback used to exist "for compat" but query strings leak into
#     logs / proxy logs / browser history, and this agent grants full shell,
#     so that fallback was removed rather than kept
#   - JARVIS_AGENT_ALLOW_SHELL=0 disables the raw `shell` action entirely
#   - JARVIS_AGENT_SHELL_PIN, if set, is a second secret (separate from the
#     device token) required in params.pin for action:"shell" specifically —
#     stealing the token alone (e.g. from a leaked log) is no longer enough
#     to get remote code execution. Not required for the other actions.
#   - cap request bodies at 1 MiB
ALLOW_SHELL = os.environ.get("JARVIS_AGENT_ALLOW_SHELL", "1") != "0"
SHELL_PIN = os.environ.get("JARVIS_AGENT_SHELL_PIN", "")
MAX_BODY = 1_048_576

# Same names/behavior as bridge/notify.py's send_email — only used here for
# GET /pin-recover (emails SHELL_PIN to yourself if you forget it). Needs its
# own copy of these vars in *this device's* env, since device_agent doesn't
# share bridge/server.py's process.
EMAIL_FROM = os.environ.get("JARVIS_EMAIL_FROM", "")
EMAIL_PASSWORD = os.environ.get("JARVIS_EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("JARVIS_EMAIL_TO", EMAIL_FROM)
EMAIL_SMTP = os.environ.get("JARVIS_EMAIL_SMTP", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("JARVIS_EMAIL_PORT", "587"))

HEARTBEAT_INTERVAL = 60   # seconds between registration retries / heartbeats


def _send_pin_recovery_email():
    """Emails the current shell PIN to JARVIS_EMAIL_TO. Gated by the device
    token (see Handler.do_GET) — so only someone who already has that token
    can trigger it, and even then the PIN lands in Sergio's own inbox, not
    back to whoever made the request.

    Always verifies the SMTP TLS certificate (no MITM-tolerant fallback like
    bridge/notify.py's send_email uses — fine for routine notifications, not
    for mailing a credential)."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText

    if not (EMAIL_FROM and EMAIL_PASSWORD):
        return False, "JARVIS_EMAIL_FROM / JARVIS_EMAIL_PASSWORD not set on this device"
    if not SHELL_PIN:
        return False, "JARVIS_AGENT_SHELL_PIN not set on this device"

    msg = MIMEText(
        f"PIN de 'shell' para el dispositivo '{DEVICE_NAME}': {SHELL_PIN}\n\n"
        f"Pedido el {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}."
    )
    msg["Subject"] = f"Jarvis: recuperación de PIN — {DEVICE_NAME}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.login(EMAIL_FROM, EMAIL_PASSWORD)
            s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        return True, f"enviado a {EMAIL_TO}"
    except Exception as e:
        return False, str(e)


# ── config ──────────────────────────────────────────────────────────────────

def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    if "token" not in cfg:
        cfg["token"] = uuid.uuid4().hex
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


CONFIG = load_config()


# ── registration ─────────────────────────────────────────────────────────────

def get_tailscale_ip():
    # WSL with mirrored networking has no native `tailscale` binary — only
    # Windows' tailscale.exe, reachable via PATH interop. Without this
    # fallback, a WSL device silently fell through to binding 0.0.0.0 (every
    # interface, LAN included) instead of just the Tailscale IP.
    for binary in ("tailscale", "tailscale.exe"):
        try:
            r = subprocess.run([binary, "ip", "-4"], capture_output=True, text=True, timeout=5)
            ip = r.stdout.strip()
            if ip:
                return ip
        except Exception:
            continue
    return None


def _try_register():
    """Single registration attempt. Returns True on success."""
    ip = get_tailscale_ip() or "unknown"
    payload = json.dumps({
        "name": DEVICE_NAME,
        "platform": PLATFORM,
        "ip": ip,
        "port": PORT,
        "token": CONFIG["token"],
        "capabilities": get_capabilities(),
    }).encode()
    headers = {"Content-Type": "application/json"}
    if HUB_TOKEN:
        headers["Authorization"] = f"Bearer {HUB_TOKEN}"
    req = urllib.request.Request(
        f"{HUB_URL}/register", data=payload,
        headers=headers,
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10)
    return True


def registration_loop():
    """Background thread: retry registration until it succeeds, then heartbeat."""
    if not HUB_URL:
        print("[agent] JARVIS_HUB_URL not set — skipping hub registration")
        return
    registered = False
    while True:
        try:
            _try_register()
            if not registered:
                print(f"[agent] Registered with hub at {HUB_URL} as '{DEVICE_NAME}'")
                registered = True
        except Exception as e:
            if registered:
                print(f"[agent] Hub lost, will retry: {e}")
                registered = False
            else:
                print(f"[agent] Hub not reachable, retrying in {HEARTBEAT_INTERVAL}s: {e}")
        time.sleep(HEARTBEAT_INTERVAL)


def get_capabilities():
    caps = (["shell"] if ALLOW_SHELL else []) + ["open_url", "notify", "get_status"]
    if PLATFORM == "darwin":
        caps += ["open_app", "volume", "mute", "screenshot", "sleep"]
    elif PLATFORM == "linux":
        caps += ["open_app", "volume", "sleep"]
    return caps


# ── actions ──────────────────────────────────────────────────────────────────

AUDIT_LOG_PATH = os.path.join(AGENT_DIR, "shell-audit.log")


def _audit_shell(source_ip, cmd):
    """`shell` is full remote code execution gated only by a token — log every
    invocation (who, from where, what) so misuse is at least visible, even
    though this doesn't prevent it. See vault/wiki/device-agent.md."""
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {source_ip} {cmd!r}\n"
    sys.stderr.write(f"[agent:{DEVICE_NAME}] AUDIT shell from {source_ip}: {cmd!r}\n")
    try:
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(line)
    except OSError:
        pass


def execute_action(action, params):
    """Execute a device action. Returns (ok: bool, result: str)."""

    if action == "shell":
        if not ALLOW_SHELL:
            return False, "shell deshabilitado (JARVIS_AGENT_ALLOW_SHELL=0)"
        if SHELL_PIN and not hmac.compare_digest(str(params.get("pin", "")), SHELL_PIN):
            return False, "PIN incorrecto o ausente (params.pin) — ver JARVIS_AGENT_SHELL_PIN"
        cmd = params.get("cmd", "")
        if not cmd:
            return False, "missing 'cmd'"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[:20000]

    if action == "open_app":
        app = params.get("app", "")
        if not app:
            return False, "missing 'app'"
        if PLATFORM == "darwin":
            r = subprocess.run(["open", "-a", app], capture_output=True, text=True)
        else:
            r = subprocess.run(["gtk-launch", app], capture_output=True, text=True)
        return r.returncode == 0, r.stderr.strip() or "ok"

    if action == "open_url":
        url = params.get("url", "")
        if not url:
            return False, "missing 'url'"
        cmd = ["open", url] if PLATFORM == "darwin" else ["xdg-open", url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0, "ok"

    if action == "volume":
        level = params.get("level")
        if level is None:
            return False, "missing 'level' (0-100)"
        if PLATFORM == "darwin":
            r = subprocess.run(
                ["osascript", "-e", f"set volume output volume {int(level)}"],
                capture_output=True, text=True,
            )
            return r.returncode == 0, "ok"
        return False, "volume not supported on this platform"

    if action == "mute":
        muted = params.get("muted", True)
        if PLATFORM == "darwin":
            val = "true" if muted else "false"
            r = subprocess.run(
                ["osascript", "-e", f"set volume output muted {val}"],
                capture_output=True, text=True,
            )
            return r.returncode == 0, "ok"
        return False, "mute not supported on this platform"

    if action == "notify":
        title = params.get("title", "Jarvis")
        message = params.get("message", "")
        if PLATFORM == "darwin":
            script = f'display notification "{message}" with title "{title}"'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            return r.returncode == 0, "ok"
        return False, "notify not supported on this platform"

    if action == "screenshot":
        path = params.get("path", "/tmp/jarvis_screenshot.png")
        if PLATFORM == "darwin":
            r = subprocess.run(["screencapture", "-x", path], capture_output=True, text=True)
            return r.returncode == 0, path
        return False, "screenshot not supported on this platform"

    if action == "sleep":
        if PLATFORM == "darwin":
            subprocess.Popen(["pmset", "sleepnow"])
            return True, "sleeping"
        elif PLATFORM == "linux":
            subprocess.Popen(["systemctl", "suspend"])
            return True, "sleeping"
        return False, "sleep not supported on this platform"

    if action == "get_status":
        info = {
            "name": DEVICE_NAME,
            "hostname": socket.gethostname(),
            "platform": PLATFORM,
            "capabilities": get_capabilities(),
        }
        if PLATFORM == "darwin":
            bat = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
            info["battery"] = bat.stdout.strip().split("\n")[-1].strip()
            apps = subprocess.run(
                ["osascript", "-e",
                 "tell application \"System Events\" to get name of every process whose background only is false"],
                capture_output=True, text=True,
            )
            info["running_apps"] = [a.strip() for a in apps.stdout.strip().split(",")]
        return True, json.dumps(info, ensure_ascii=False)

    return False, f"unknown action: '{action}'"


# ── HTTP handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def _auth(self):
        # Header only — see the module-level comment on why the old
        # query-string ?token= fallback was removed rather than kept.
        token = self.headers.get("X-Jarvis-Token", "")
        return bool(token) and token == CONFIG["token"]

    def _json(self, code, obj):
        # No CORS headers: nothing in this repo calls /execute or /status from
        # browser JS (only curl/Bash, which CORS doesn't apply to anyway), and
        # this endpoint grants full shell — no reason to open that door.
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if not self._auth():
            return self._json(401, {"error": "unauthorized"})
        if path == "/status":
            ok, result = execute_action("get_status", {})
            return self._json(200, {"ok": ok, "result": json.loads(result) if ok else result})
        if path == "/pin-recover":
            ok, result = _send_pin_recovery_email()
            return self._json(200 if ok else 500, {"ok": ok, "result": result})
        self._json(200, {
            "device": DEVICE_NAME,
            "platform": PLATFORM,
            "capabilities": get_capabilities(),
        })

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/execute":
            return self._json(404, {"error": "not found"})

        if not self._auth():
            return self._json(401, {"error": "unauthorized"})

        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return self._json(400, {"error": "empty body"})
        if length > MAX_BODY:
            return self._json(413, {"error": "body too large"})

        try:
            payload = json.loads(self.rfile.read(length))
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})

        action = payload.get("action", "")
        params = payload.get("params", {})

        if action == "shell":
            _audit_shell(self.client_address[0], params.get("cmd", ""))

        try:
            ok, result = execute_action(action, params)
        except Exception as e:
            return self._json(500, {"ok": False, "result": str(e)})

        self._json(200, {"ok": ok, "result": result})

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[agent:{DEVICE_NAME}] " + (fmt % args) + "\n")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # bind to the Tailscale interface, not every interface, when we can
    bind = os.environ.get("JARVIS_AGENT_BIND") or get_tailscale_ip() or "0.0.0.0"
    print(f"[agent] Device: {DEVICE_NAME} ({PLATFORM})")
    print(f"[agent] Token:  {CONFIG['token']}")
    print(f"[agent] Listening on {bind}:{PORT}"
          + ("" if bind != "0.0.0.0" else "  (todas las interfaces — set JARVIS_AGENT_BIND)"))
    print(f"[agent] shell action: {'on' if ALLOW_SHELL else 'OFF'}")
    print(f"[agent] Capabilities: {', '.join(get_capabilities())}")
    threading.Thread(target=registration_loop, daemon=True).start()
    ThreadingHTTPServer((bind, PORT), Handler).serve_forever()
