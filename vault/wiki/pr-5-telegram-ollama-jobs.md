---
title: "PR #5 — Telegram→Ollama + jobs"
tags: [pr, llm]
status: open
updated: 2026-09-01
summary: Telegram falls back to Ollama when out of tokens; the bridge keeps the last 8 jobs instead of 1.
---

# PR #5 — `feat/telegram-ollama-fallback-y-jobs-multiples`

- **`bridge/ollama_fallback.py`** (new, shared): iterates over every backend, verifies the
  model, 300 s timeout. `bridge/telegram_bot.py` uses it when `claude` fails / times out /
  won't start / returns empty / prints a limit message. Before: `(error claude: ...)` and nothing more.
- **`bridge/server.py`:** `_job` was a single global slot → a 2nd message lost the 1st one's
  reply (404 "the reply was lost"). Now a dict of the last 8, looked up by id.

Independent of [[pr-1-ollama-fallback]]. When merging both: unify `server.py` to use
`ollama_fallback.py` ([[ideas-pendientes]]).

See [[telegram]] · [[ollama-fallback]] · [[bridge]].
