#!/usr/bin/env python3
"""Jarvis notification dispatcher — stdlib only, no pip required.

Supported channels (configure via env vars):
  Discord webhook  → JARVIS_DISCORD_WEBHOOK
  Telegram bot     → JARVIS_TELEGRAM_TOKEN + JARVIS_TELEGRAM_CHAT_ID
  Email (Gmail)    → JARVIS_EMAIL_FROM + JARVIS_EMAIL_PASSWORD

Usage (from Python):
    from bridge.notify import dispatch
    dispatch("Buenos días, Sergio. Tu agenda de hoy...")
    dispatch("Informe", channels=["email"], subject="Jarvis: Mercado")

Usage (from CLI):
    python3 bridge/notify.py "Mensaje de prueba"
    python3 bridge/notify.py --channels discord,telegram "Mensaje"
    python3 bridge/notify.py --channels email --subject "Asunto" "Mensaje"
    python3 bridge/notify.py --no-voice "Texto plano sin voz"
"""
import json
import os
import sys
import urllib.error
import urllib.request

# ── env ─────────────────────────────────────────────────────────────

DISCORD_WEBHOOK  = os.environ.get("JARVIS_DISCORD_WEBHOOK", "")
TELEGRAM_TOKEN   = os.environ.get("JARVIS_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "")
KOKORO_URL       = os.environ.get("VOICEMODE_TTS_URL", "http://127.0.0.1:8880/v1/audio/speech")
TTS_VOICE        = os.environ.get("JARVIS_TTS_VOICE", "af_sky")


def _urlopen(req, timeout=15):
    """urlopen con reintento verificado→sin-verificar (redes con MITM/cert corporativo).

    Igual que hacen send_email() y agents/trading.py._fetch().
    """
    import ssl
    last = None
    for verified in (True, False):
        ctx = ssl.create_default_context()
        if not verified:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.HTTPError:
            raise  # error de aplicación, no de TLS
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if "CERTIFICATE_VERIFY_FAILED" in str(reason) or reason.__class__.__name__ == "SSLError":
                last = e
                continue
            raise
    raise last


# ── discord ──────────────────────────────────────────────────────────

def send_discord(message: str) -> tuple[bool, str]:
    if not DISCORD_WEBHOOK:
        return False, "JARVIS_DISCORD_WEBHOOK not set"
    payload = json.dumps({"content": message, "username": "Jarvis"}).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _urlopen(req, timeout=10)
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
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message}).encode()
    req = urllib.request.Request(
        _tg_url("sendMessage"), data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        _urlopen(req, timeout=10)
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
        _urlopen(req, timeout=30)
        return True, "ok"
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


# ── email ────────────────────────────────────────────────────────────

def send_email(subject: str, body: str, attachments: list[str] | None = None) -> tuple[bool, str]:
    import mimetypes
    import smtplib
    import ssl as ssl_lib
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from_addr = os.environ.get("JARVIS_EMAIL_FROM", "")
    password  = os.environ.get("JARVIS_EMAIL_PASSWORD", "")
    to_addr   = os.environ.get("JARVIS_EMAIL_TO", from_addr)
    smtp_host = os.environ.get("JARVIS_EMAIL_SMTP", "smtp.gmail.com")
    smtp_port = int(os.environ.get("JARVIS_EMAIL_PORT", "587"))

    if not (from_addr and password):
        return False, "JARVIS_EMAIL_FROM / JARVIS_EMAIL_PASSWORD not set"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachments or []:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue  # a missing chart shouldn't sink the whole email
        ctype, _ = mimetypes.guess_type(path)
        maintype, _, subtype = (ctype or "application/octet-stream").partition("/")
        part = MIMEBase(maintype, subtype or "octet-stream")
        part.set_payload(raw)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment",
                        filename=os.path.basename(path))
        msg.attach(part)

    last_err = None
    for verified in (True, False):
        ctx = ssl_lib.create_default_context()
        if not verified:
            ctx.check_hostname = False
            ctx.verify_mode = ssl_lib.CERT_NONE
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(from_addr, password)
                s.sendmail(from_addr, to_addr, msg.as_string())
            return True, f"→ {to_addr}"
        except ssl_lib.SSLError as e:
            last_err = e
            continue
        except Exception as e:
            return False, str(e)
    return False, str(last_err)


# ── dispatcher ───────────────────────────────────────────────────────

def dispatch(
    message: str,
    channels: list[str] | None = None,
    voice_for_telegram: bool = True,
    subject: str = "Jarvis",
    attachments: list[str] | None = None,
) -> dict[str, tuple[bool, str]]:
    """Send message to all configured/requested channels.

    channels: list of "discord", "telegram", "email". None = all configured.
    attachments: file paths to attach (email only; other channels ignore them).
    Returns dict of {channel: (ok, detail)}.
    """
    results: dict[str, tuple[bool, str]] = {}

    if channels is None:
        channels = []
        if DISCORD_WEBHOOK:
            channels.append("discord")
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            channels.append("telegram")
        if os.environ.get("JARVIS_EMAIL_FROM") and os.environ.get("JARVIS_EMAIL_PASSWORD"):
            channels.append("email")

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
        elif ch == "email":
            results["email"] = send_email(subject, message, attachments)
        else:
            results[ch] = (False, f"unknown channel '{ch}'")

    return results


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send a Jarvis notification")
    parser.add_argument("message", nargs="?", help="Message to send")
    parser.add_argument("--channels", "-c", help="Comma-separated: discord,telegram,email")
    parser.add_argument("--no-voice", action="store_true", help="Text-only for Telegram")
    parser.add_argument("--subject", "-s", default="Jarvis", help="Email subject line")
    parser.add_argument("--attach", "-a", action="append", default=[],
                        help="File to attach to the email (repeatable)")
    args = parser.parse_args()

    msg = args.message or (sys.stdin.read().strip() if not sys.stdin.isatty() else None)
    if not msg:
        parser.error("Provide a message as argument or via stdin")

    chs = [c.strip() for c in args.channels.split(",")] if args.channels else None
    results = dispatch(msg, channels=chs, voice_for_telegram=not args.no_voice,
                       subject=args.subject, attachments=args.attach or None)

    for ch, (ok, detail) in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {ch}: {detail}")
    if not results:
        print("  No channels configured. Set JARVIS_DISCORD_WEBHOOK or JARVIS_TELEGRAM_TOKEN.")
