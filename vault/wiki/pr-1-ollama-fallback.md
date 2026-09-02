---
title: "PR #1 — fix ollama-fallback"
tags: [pr, llm]
status: abierto
updated: 2026-09-01
summary: El fallback a Ollama de server.py anunciaba el cambio pero nunca respondía.
---

# PR #1 — `fix/ollama-fallback`

**Problema:** con `claude` sin tokens, el HUD mostraba "Usando Ollama" pero no llegaba respuesta.

**Causa:** `_pick_ollama()` solo hacía `socket.connect` al 11434 (no comprobaba el modelo);
`_ask_ollama` sin `try/except` y sin reintento al siguiente backend; timeout de 120 s corto
para cargar un 7B en frío.

**Fix:** elige un modelo que exista (`/api/tags`), recorre todos los backends, timeout
configurable + `keep_alive`, y si fallan todos lanza un error que nombra cada causa.

Ver [[ollama-fallback]] · [[bridge]].
