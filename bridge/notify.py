#!/usr/bin/env python3
"""Jarvis notification dispatcher — stdlib only, no pip required.

Supported channels (configure via env vars):
  Discord webhook  → JARVIS_DISCORD_WEBHOOK
  Telegram bot     → JARVIS_TELEGRAM_TOKEN + JARVIS_TELEGRAM_CHAT_ID
  Twilio call      → TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN +
                     TWILIO_PHONE_FROM + TWILIO_PHONE_TO

Usage (from Python):
    from bridge.notify import dispatch
    dispatch("Buenos días, Sergio. Tu agenda de hoy...")

Usage (from CLI):
    python3 bridge/notify.py "Mensaje de prueba"
    python3 bridge/notify.py --channels discord,telegram "Mensaje"
    python3 bridge/notify.py --channels call "Texto para la llamada"
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── env ─────────────────────────────────────────────────────────────

DISCORD_WEBHOOK      = os.environ.get("JARVIS_DISCORD_WEBHOOK", "")
TELEGRAM_TOKEN       = os.environ.get("JARVIS_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID     = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "")
TWILIO_SID           = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN         = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM          = os.environ.get("TWILIO_PHONE_FROM", "")
TWILIO_TO            = os.environ.get("TWILIO_PHONE_TO", "")
KOKORO_URL           = os.environ.get("VOICEMODE_TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
TTS_VOICE            = os.environ.get("JARVIS_TTS_VOICE", "af_sky")


# ── discord ──────────────────────────────────────────────────────────

def send_discord(message: str) -> tuple[bool, str]:
    if not DISCORD_WEBHOOK:
        return False, "JARVIS_DISCORD_WEBHOOK not set"
    payload = json.dumps({
        "content": message,
        "username": "Jarvis",
    }).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True, "ok"
    except urllib.error.HTTPError as e:
        return False, f"Discord HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, str(e)


# ── telegram ─────────────────────────────────────────────────────────

def _tg_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


def send_telegram(message: str) -> tuple[bool, str]:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "JARVIS_TELEGRAM_TOKEN or JARVIS_TELEGRAM_CHAT_ID not set"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }).encode()
    req = urllib.request.Request(
        _tg_url("sendMessage"), data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def send_telegram_voice(mp3_bytes: bytes, caption: str = "") -> tuple[bool, str]:
    """Send an MP3 as a Telegram voice note."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Telegram not configured"
    boundary = "----jarvistgbound"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{TELEGRAM_CHAT_ID}\r\n'
        + (f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n' if caption else "")
        + f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="voice"; filename="brief.mp3"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + mp3_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        _tg_url("sendVoice"), data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        return True, "ok"
    except Exception as e:
        return False, str(e)


# ── twilio call ──────────────────────────────────────────────────────

def make_call(message: str, lang: str = "es-ES") -> tuple[bool, str]:
    """Call TWILIO_PHONE_TO and speak `message` via TTS."""
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
        return False, "Twilio not fully configured (need SID, TOKEN, FROM, TO)"
    safe_msg = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    twiml = (
        f'<Response>'
        f'<Say language="{lang}" voice="Polly.Lucia">{safe_msg}</Say>'
        f'</Response>'
    )
    data = urllib.parse.urlencode({
        "To": TWILIO_TO,
        "From": TWILIO_FROM,
        "Twiml": twiml,
    }).encode()
    auth = base64.b64encode(f"{TWILIO_SID}:{TWILIO_TOKEN}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Calls.json",
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            sid = json.loads(resp.read()).get("sid", "?")
            return True, f"call {sid}"
    except urllib.error.HTTPError as e:
        return False, f"Twilio HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return False, str(e)


# ── kokoro TTS (local) ───────────────────────────────────────────────

def synthesize(text: str) -> bytes | None:
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


# ── dispatcher ───────────────────────────────────────────────────────

def dispatch(
    message: str,
    channels: list[str] | None = None,
    voice_for_telegram: bool = True,
) -> dict[str, tuple[bool, str]]:
    """Send message to all configured/requested channels.

    channels: list of "discord", "telegram", "call". None = all configured.
    Returns dict of {channel: (ok, detail)}.
    """
    results: dict[str, tuple[bool, str]] = {}

    # Decide which channels to use
    if channels is None:
        channels = []
        if DISCORD_WEBHOOK:
            channels.append("discord")
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            channels.append("telegram")
        if all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
            channels.append("call")

    for ch in channels:
        if ch == "discord":
            results["discord"] = send_discord(message)

        elif ch == "telegram":
            if voice_for_telegram:
                mp3 = synthesize(message)
                if mp3:
                    results["telegram"] = send_telegram_voice(mp3, caption="Jarvis · brief")
                else:
                    results["telegram"] = send_telegram(message)
            else:
                results["telegram"] = send_telegram(message)

        elif ch == "call":
            results["call"] = make_call(message)

        else:
            results[ch] = (False, f"unknown channel '{ch}'")

    return results


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send a Jarvis notification")
    parser.add_argument("message", nargs="?", help="Message to send")
    parser.add_argument("--channels", "-c", help="Comma-separated: discord,telegram,call")
    parser.add_argument("--no-voice", action="store_true", help="Text-only for Telegram")
    args = parser.parse_args()

    msg = args.message or (sys.stdin.read().strip() if not sys.stdin.isatty() else None)
    if not msg:
        parser.error("Provide a message as argument or via stdin")

    chs = [c.strip() for c in args.channels.split(",")] if args.channels else None
    results = dispatch(msg, channels=chs, voice_for_telegram=not args.no_voice)

    for ch, (ok, detail) in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {ch}: {detail}")
    if not results:
        print("  No channels configured. Set JARVIS_DISCORD_WEBHOOK, JARVIS_TELEGRAM_TOKEN, or Twilio vars.")
