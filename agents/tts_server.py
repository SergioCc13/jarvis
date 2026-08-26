#!/usr/bin/env python3
"""OpenAI-compatible Piper TTS server (port 8880) for Raspberry Pi.

Wraps the piper CLI to produce MP3 audio from text.
Install:
  bash bin/setup-voice-pi   # downloads piper binary + voice model
Requires: ffmpeg (sudo apt install -y ffmpeg)
"""
import json
import os
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("KOKORO_PORT", "8880"))
JARVIS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER_BIN = os.environ.get("PIPER_BIN", os.path.join(JARVIS_DIR, "bin", "piper"))
PIPER_VOICE = os.environ.get(
    "PIPER_VOICE",
    os.path.join(JARVIS_DIR, "agents", "voice", "es_ES-davefx-medium.onnx"),
)


def _check():
    ok = True
    if not os.path.isfile(PIPER_BIN):
        sys.stderr.write(f"[tts] piper binary not found: {PIPER_BIN}\n")
        ok = False
    if not os.path.isfile(PIPER_VOICE):
        sys.stderr.write(f"[tts] voice model not found: {PIPER_VOICE}\n")
        ok = False
    if ok:
        sys.stderr.write("[tts] piper ready\n")
    return ok


_READY = _check()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.rstrip("/") != "/v1/audio/speech":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        text = (payload.get("input") or "").strip()
        if not text:
            self.send_response(400)
            self.end_headers()
            return

        if not _READY:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":"piper not installed, run bin/setup-voice-pi"}')
            return

        # piper → WAV → ffmpeg → MP3
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_f:
            wav_path = wav_f.name
        mp3_path = wav_path.replace(".wav", ".mp3")
        try:
            subprocess.run(
                [PIPER_BIN, "--model", PIPER_VOICE, "--output_file", wav_path],
                input=text.encode(),
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "4", mp3_path],
                check=True,
                capture_output=True,
                timeout=30,
            )
            with open(mp3_path, "rb") as f:
                audio = f.read()
        finally:
            for p in (wav_path, mp3_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def log_message(self, fmt, *args):
        sys.stderr.write("[tts] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print(f"TTS server on 127.0.0.1:{PORT}  voice={os.path.basename(PIPER_VOICE)}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
