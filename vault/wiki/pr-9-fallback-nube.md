---
title: "PR #9 — cloud fallback"
tags: [pr, llm]
status: open
updated: 2026-09-02
summary: Adds a free-cloud tier (Groq/Gemini/OpenRouter) before Ollama, plus per-device model selection.
---

# PR #9 — `feat/fallback-nube-y-modelo-por-dispositivo`

- **`bridge/server.py`:** `ask()` now tries Claude → `_cloud_fallback` (new) → `_ollama_fallback`.
  `_cloud_fallback` calls an OpenAI-compatible endpoint (`JARVIS_CLOUD_URL` / `_KEY` / `_MODEL`);
  blank config skips the tier entirely.
- **Per-device model in `JARVIS_OLLAMA_BACKENDS`:** each backend entry can now be `IP=model`,
  so a 32 GB machine runs `qwen2.5-coder:32b` and the 8 GB Pi `qwen2.5:3b` off the same
  variable. See [[ollama-fallback]].
- Tier switches still announce over Telegram/HUD (`_notify_async` + `_push_event`) and notify
  when Claude comes back.

Only implemented in `bridge/server.py` so far — `bridge/ollama_fallback.py` (the shared module
used by [[telegram]], from [[pr-5-telegram-ollama-jobs]]) doesn't have a cloud tier yet; unifying
the two is tracked in [[ideas-pendientes]].

See [[ollama-fallback]] · [[bridge]] · [[coste-tokens]].
