---
title: Ollama fallback
tags: [subsystem, llm]
status: active
updated: 2026-09-02
summary: Tiered chain when claude fails — free cloud, then large remote Ollama, then small local; per-device model.
---

# Ollama fallback

When `claude` is unavailable (session/usage limit, timeout, crash), Jarvis replies via a
**tiered chain**:

```
Claude  →  free cloud (Groq/Gemini/OpenRouter)  →  remote Ollama (large model)  →  local Ollama (small)
```

Config in `bridge/.env`:

- `JARVIS_CLOUD_URL` / `_KEY` / `_MODEL` — an OpenAI-compatible endpoint. Blank = skip the cloud.
- `JARVIS_OLLAMA_BACKENDS` — `:11434` backends in order. Each entry is `IP` or `IP=model`, so a
  32 GB machine runs `qwen2.5-coder:32b` and the 8 GB Pi runs `qwen2.5:3b` from the same
  variable. IPs without `=model` use `JARVIS_OLLAMA_MODEL` (or `_MODEL_LOCAL` for `127.0.0.1`).
  `127.0.0.1` last = last resort.
- `JARVIS_OLLAMA_TIMEOUT` (300 s, cold-loading a 7B), `_KEEP_ALIVE` (30m).

The cloud is the hop that recovers the most quality when Claude's tokens run out but there's
internet; the Ollamas are the insurance for network outages. See [[coste-tokens]].

## Two implementations

- **`bridge/server.py`** (HUD/voice) — `ask()` tries Claude → `_cloud_fallback` → `_ollama_fallback`.
  Announces the tier switch via Telegram/HUD (`_notify_async` + `_push_event`) and reports when
  Claude comes back. [[pr-1-ollama-fallback]] fixed the Ollama path; [[pr-9-fallback-nube]] adds
  the cloud and the per-device model.
- **`bridge/ollama_fallback.py`** (shared module, [[pr-5-telegram-ollama-jobs]]) — used by
  [[telegram]]. Iterates over **every** backend in the same `IP=model` format, checks via
  `/api/tags` that the model exists (hint → configured tag → same family → any). No cloud tier yet.

## Pending ([[ideas-pendientes]])

- Unify: have `server.py` also use `ollama_fallback.py` (and move the cloud tier there).
- A real capability-aware router (the hub picks the highest tier *reachable* per device instead
  of a fixed list).

## Related

[[bridge]] · [[telegram]] · [[coste-tokens]] · [[pr-1-ollama-fallback]] · [[pr-5-telegram-ollama-jobs]] · [[pr-9-fallback-nube]]
