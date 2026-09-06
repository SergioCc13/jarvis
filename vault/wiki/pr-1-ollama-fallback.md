---
title: "PR #1 — fix ollama-fallback"
tags: [pr, llm]
status: open
updated: 2026-09-01
summary: server.py's Ollama fallback announced the switch but never actually replied.
---

# PR #1 — `fix/ollama-fallback`

**Problem:** with `claude` out of tokens, the HUD showed "Using Ollama" but no reply ever arrived.

**Cause:** `_pick_ollama()` only did a `socket.connect` to 11434 (it never checked the model);
`_ask_ollama` had no `try/except` and no retry against the next backend; the 120 s timeout was
too short to load a 7B model cold.

**Fix:** pick a model that actually exists (`/api/tags`), iterate over every backend, configurable
timeout + `keep_alive`, and if all of them fail raise an error that names each cause.

See [[ollama-fallback]] · [[bridge]].
