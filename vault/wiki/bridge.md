---
title: Bridge
tags: [subsystem, network]
status: active
updated: 2026-09-01
summary: Hub HTTP server on port 8792 — voice, chat, device registration and SSE.
---

# Bridge — `bridge/server.py`

A plain HTTP server (`ThreadingHTTPServer`) on `127.0.0.1:8792`. The phone reaches it via
`tailscale serve` (which terminates HTTPS; the mic needs a secure context). Everything
authenticates against `bridge/config.json` with an `Authorization: Bearer <token>` header —
except `/events`, which still accepts `?token=` because the browser's native `EventSource`
can't send custom headers (fixed 2026-09-03, [[fix-token-query-string]]).

## Routes

| Route | What it does |
|---|---|
| `POST /voice` (or `/` behind tailscale serve) | audio → Whisper STT → [[sesion-claude]] → Kokoro TTS → mp3 |
| `POST /chat`, `POST /chat/image` | starts a background job, returns `job_id` (202) |
| `GET /chat/result?job_id=` | poll the job (survives a tab reload) |
| `GET /events` | SSE to the [[hud]] (notices, e.g. switch to Ollama) |
| `POST /register`, `GET /devices` | [[device-agent]] registration |
| `GET /version` | git hash |

## Pieces

- **Voice backends** (`JARVIS_VOICE_BACKENDS`): Tailscale IPs with Whisper :2022 and Kokoro
  :8880 in priority order; `127.0.0.1` as the last resort. Choice cached for 60 s.
- **`/chat` jobs**: `_start_chat_job` + a worker thread. It used to be **one global slot** →
  a 2nd message lost the 1st one's reply. [[pr-5-telegram-ollama-jobs]] moves it to a dict of 8.
- **Ollama fallback**: if `claude` fails, it replies from [[ollama-fallback]].
- **`ask_claude`** runs a shared `claude -p --resume <session_id>` → see [[sesion-claude]].

## Related

[[hud]] · [[telegram]] · [[device-agent]] · [[notificaciones]] · [[ollama-fallback]]
