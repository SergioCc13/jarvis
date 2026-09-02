---
title: Bridge
tags: [subsistema, red]
status: activo
updated: 2026-09-01
summary: Servidor HTTP hub en el puerto 8792 — voz, chat, registro de dispositivos y SSE.
---

# Bridge — `bridge/server.py`

Servidor HTTP plano (`ThreadingHTTPServer`) en `127.0.0.1:8792`. El teléfono llega por
`tailscale serve` (termina HTTPS; el micro necesita contexto seguro). Todo autentica con
`?token=` contra `bridge/config.json`.

## Rutas

| Ruta | Qué hace |
|---|---|
| `POST /voice` (o `/` tras tailscale serve) | audio → STT Whisper → [[sesion-claude]] → TTS Kokoro → mp3 |
| `POST /chat`, `POST /chat/image` | lanza job en background, devuelve `job_id` (202) |
| `GET /chat/result?job_id=` | poll del job (sobrevive a recargar la pestaña) |
| `GET /events` | SSE hacia el [[hud]] (avisos, p. ej. cambio a Ollama) |
| `POST /register`, `GET /devices` | registro de [[device-agent]]s |
| `GET /version` | hash de git |

## Piezas

- **Backends de voz** (`JARVIS_VOICE_BACKENDS`): IPs Tailscale con Whisper :2022 y Kokoro
  :8880 en orden de prioridad; `127.0.0.1` como último recurso. Elección cacheada 60 s.
- **Jobs de `/chat`**: `_start_chat_job` + hilo worker. Antes era **una ranura global** →
  un 2º mensaje perdía la respuesta del 1º. [[pr-5-telegram-ollama-jobs]] lo pasa a dict de 8.
- **Fallback a Ollama**: si `claude` falla, responde desde [[ollama-fallback]].
- **`ask_claude`** hace `claude -p --resume <session_id>` compartido → ver [[sesion-claude]].

## Relacionado

[[hud]] · [[telegram]] · [[device-agent]] · [[notificaciones]] · [[ollama-fallback]]
