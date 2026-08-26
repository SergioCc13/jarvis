#!/usr/bin/env python3
"""OpenAI-compatible Whisper STT server (port 2022) for Raspberry Pi.

Uses faster-whisper with int8 quantisation — runs fine on Pi 4 CPU.
Install: pip3 install faster-whisper
"""
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny")
LANGUAGE = os.environ.get("VOICEMODE_WHISPER_LANGUAGE", "es")
PORT = int(os.environ.get("WHISPER_PORT", "2022"))

MODEL = None  # loaded after server binds to avoid "address in use" on restart


def load_model():
    from faster_whisper import WhisperModel
    sys.stderr.write(f"[stt] loading {MODEL_SIZE} model (lang={LANGUAGE})…\n")
    m = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    sys.stderr.write("[stt] model ready\n")
    return m


def _parse_multipart(body: bytes, boundary: bytes) -> dict:
    parts = {}
    for chunk in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in chunk:
            continue
        header_raw, _, content = chunk.partition(b"\r\n\r\n")
        content = content.rstrip(b"\r\n--")
        name = None
        for hline in header_raw.split(b"\r\n"):
            if b'name="' in hline:
                name = hline.split(b'name="')[1].split(b'"')[0].decode()
        if name:
            parts[name] = content
    return parts


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.rstrip("/") != "/v1/audio/transcriptions":
            self.send_response(404)
            self.end_headers()
            return

        if MODEL is None:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'{"error":"model loading"}')
            return

        ct = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        if "boundary=" in ct:
            boundary = ct.split("boundary=")[1].strip().encode()
            parts = _parse_multipart(body, boundary)
            audio_data = parts.get("file", b"")
        else:
            audio_data = body

        if not audio_data:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"no audio"}')
            return

        ext = ".webm"
        if audio_data[:4] == b"RIFF":
            ext = ".wav"
        elif audio_data[:3] == b"ID3" or audio_data[:2] == b"\xff\xfb":
            ext = ".mp3"

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_data)
            tmp = f.name
        try:
            segs, _ = MODEL.transcribe(tmp, language=LANGUAGE)
            text = " ".join(s.text for s in segs).strip()
        finally:
            os.unlink(tmp)

        result = json.dumps({"text": text}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

    def log_message(self, fmt, *args):
        sys.stderr.write("[stt] " + (fmt % args) + "\n")


class _Server(HTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True


if __name__ == "__main__":
    server = _Server(("127.0.0.1", PORT), Handler)
    sys.stderr.write(f"[stt] bound to 127.0.0.1:{PORT}\n")
    MODEL = load_model()
    print(f"STT server ready on 127.0.0.1:{PORT}  model={MODEL_SIZE}  lang={LANGUAGE}")
    server.serve_forever()
