#!/usr/bin/env python3
"""Jarvis device agent — runs on each managed device (Mac, PC, etc.).

On startup, registers with the Pi hub. Then listens for dispatch commands
from Jarvis (Claude) so any device can be controlled remotely over Tailscale.

Usage:
    JARVIS_HUB_URL=http://<pi-tailscale-ip>:8792 \
    JARVIS_DEVICE_NAME=mac-sergio \
    python3 agents/device_agent.py
"""
import json
import os
import socket
import subprocess
import sys
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(AGENT_DIR, "config.json")
PORT = int(os.environ.get("JARVIS_AGENT_PORT", "8793"))
HUB_URL = os.environ.get("JARVIS_HUB_URL", "")
DEVICE_NAME = os.environ.get("JARVIS_DEVICE_NAME", socket.gethostname())
PLATFORM = sys.platform  # darwin | linux | win32


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
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return None


def register_with_hub():
    if not HUB_URL:
        print("[agent] JARVIS_HUB_URL not set — skipping hub registration")
        return
    ip = get_tailscale_ip() or "unknown"
    payload = json.dumps({
        "name": DEVICE_NAME,
        "platform": PLATFORM,
        "ip": ip,
        "port": PORT,
        "token": CONFIG["token"],
        "capabilities": get_capabilities(),
    }).encode()
    hub_token = os.environ.get("JARVIS_HUB_TOKEN", "")
    url = f"{HUB_URL}/register"
    if hub_token:
        url += f"?token={hub_token}"
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"[agent] Registered with hub at {HUB_URL} as '{DEVICE_NAME}'")
    except Exception as e:
        print(f"[agent] Could not register with hub: {e}")


def get_capabilities():
    caps = ["shell", "open_url", "notify", "get_status"]
    if PLATFORM == "darwin":
        caps += ["open_app", "volume", "mute", "screenshot", "sleep"]
    elif PLATFORM == "linux":
        caps += ["open_app", "volume", "sleep"]
    return caps


# ── actions ──────────────────────────────────────────────────────────────────

def execute_action(action, params):
    """Execute a device action. Returns (ok: bool, result: str)."""

    if action == "shell":
        cmd = params.get("cmd", "")
        if not cmd:
            return False, "missing 'cmd'"
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

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
        import urllib.parse
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        token = urllib.parse.parse_qs(qs).get("token", [""])[0]
        return token == CONFIG["token"]

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
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

        try:
            payload = json.loads(self.rfile.read(length))
        except ValueError:
            return self._json(400, {"error": "invalid JSON"})

        action = payload.get("action", "")
        params = payload.get("params", {})

        try:
            ok, result = execute_action(action, params)
        except Exception as e:
            return self._json(500, {"ok": False, "result": str(e)})

        self._json(200, {"ok": ok, "result": result})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[agent:{DEVICE_NAME}] " + (fmt % args) + "\n")


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    register_with_hub()
    print(f"[agent] Device: {DEVICE_NAME} ({PLATFORM})")
    print(f"[agent] Token:  {CONFIG['token']}")
    print(f"[agent] Listening on 0.0.0.0:{PORT}")
    print(f"[agent] Capabilities: {', '.join(get_capabilities())}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
