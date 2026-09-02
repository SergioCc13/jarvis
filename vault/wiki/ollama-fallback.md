---
title: Fallback a Ollama
tags: [subsistema, llm]
status: activo
updated: 2026-09-02
summary: Cadena escalonada cuando claude falla — nube gratis, luego Ollama remoto grande, luego local pequeño; modelo por dispositivo.
---

# Fallback a Ollama

Cuando `claude` no está disponible (límite de sesión/uso, timeout, crash), Jarvis responde
por una **cadena escalonada**:

```
Claude  →  nube gratis (Groq/Gemini/OpenRouter)  →  Ollama remoto (modelo grande)  →  Ollama local (pequeño)
```

Config en `bridge/.env`:

- `JARVIS_CLOUD_URL` / `_KEY` / `_MODEL` — endpoint OpenAI-compatible. Blanco = saltar la nube.
- `JARVIS_OLLAMA_BACKENDS` — backends `:11434` en orden. Cada entrada es `IP` o `IP=modelo`,
  así una máquina de 32 GB corre `qwen2.5-coder:32b` y la Pi de 8 GB `qwen2.5:3b` con la
  misma variable. Las IP sin `=modelo` usan `JARVIS_OLLAMA_MODEL` (o `_MODEL_LOCAL` para
  `127.0.0.1`). `127.0.0.1` al final = último recurso.
- `JARVIS_OLLAMA_TIMEOUT` (300 s, carga en frío de un 7B), `_KEEP_ALIVE` (30m).

La nube es el salto que más calidad recupera cuando se acaban los tokens de Claude pero hay
internet; los Ollama son el seguro para cortes de red. Ver [[coste-tokens]].

## Dos implementaciones

- **`bridge/server.py`** (HUD/voz) — `ask()` prueba Claude → `_cloud_fallback` → `_ollama_fallback`.
  Anuncia el cambio de tier por Telegram/HUD (`_notify_async` + `_push_event`) y avisa cuando
  Claude vuelve. [[pr-1-ollama-fallback]] arregló el Ollama; [[pr-9-fallback-nube]] añade la
  nube y el modelo por dispositivo.
- **`bridge/ollama_fallback.py`** (módulo compartido, [[pr-5-telegram-ollama-jobs]]) — lo usa
  [[telegram]]. Recorre **todos** los backends con el mismo formato `IP=modelo`, comprueba con
  `/api/tags` que el modelo exista (hint → tag configurado → misma familia → cualquiera). No
  tiene tier de nube todavía.

## Pendiente ([[ideas-pendientes]])

- Unificar: que `server.py` use también `ollama_fallback.py` (y llevar ahí el tier de nube).
- Router capability-aware real (que el hub elija el tier más alto *alcanzable* por dispositivo
  en vez de una lista fija).

## Relacionado

[[bridge]] · [[telegram]] · [[coste-tokens]] · [[pr-1-ollama-fallback]] · [[pr-5-telegram-ollama-jobs]] · [[pr-9-fallback-nube]]
