---
title: "PR #5 — Telegram→Ollama + jobs"
tags: [pr, llm]
status: abierto
updated: 2026-09-01
summary: Telegram cae a Ollama sin tokens; el bridge guarda los últimos 8 jobs en vez de 1.
---

# PR #5 — `feat/telegram-ollama-fallback-y-jobs-multiples`

- **`bridge/ollama_fallback.py`** (nuevo, compartido): recorre todos los backends, verifica
  el modelo, timeout 300 s. `bridge/telegram_bot.py` lo usa cuando `claude` falla / timeout /
  no arranca / vacío / mensaje de límite. Antes: `(error claude: ...)` y punto.
- **`bridge/server.py`:** `_job` era una ranura global → un 2º mensaje perdía la respuesta
  del 1º (404 "la respuesta se perdió"). Ahora dict de los últimos 8, buscado por id.

Independiente del [[pr-1-ollama-fallback]]. Al mergear ambos: unificar `server.py` para usar
`ollama_fallback.py` ([[ideas-pendientes]]).

Ver [[telegram]] · [[ollama-fallback]] · [[bridge]].
