---
title: Fallback a Ollama
tags: [subsistema, llm]
status: activo
updated: 2026-09-01
summary: LLM local cuando claude no responde — recorre backends, verifica modelo, timeout largo.
---

# Fallback a Ollama

Cuando `claude` no está disponible (límite de sesión/uso, timeout, crash), responder desde
un Ollama local. Config en `bridge/.env`: `JARVIS_OLLAMA_BACKENDS` (IPs :11434 en orden,
`127.0.0.1` al final), `JARVIS_OLLAMA_MODEL` (`qwen2.5:7b`), `..._MODEL_LOCAL` (`qwen2.5:3b`),
`..._TIMEOUT` (300 s, carga en frío de un 7B), `..._KEEP_ALIVE` (30m).

## Dos implementaciones

- **`bridge/server.py`** (HUD/voz) — [[pr-1-ollama-fallback]] lo arregla: antes solo miraba
  el puerto (no el modelo) y no reintentaba en otro backend, así que anunciaba el cambio y
  nunca respondía.
- **`bridge/ollama_fallback.py`** (módulo compartido, [[pr-5-telegram-ollama-jobs]]) — lo usa
  [[telegram]]. Recorre **todos** los backends, comprueba con `/api/tags` que el modelo
  exista (tag configurado → misma familia → cualquiera), y si fallan todos lanza un error
  que nombra cada causa.

## Pendiente ([[ideas-pendientes]])

Unificar: que `server.py` use también `ollama_fallback.py`. Hacer tras mergear #1 y #5.

## Relacionado

[[bridge]] · [[telegram]] · [[coste-tokens]] · [[pr-1-ollama-fallback]] · [[pr-5-telegram-ollama-jobs]]
