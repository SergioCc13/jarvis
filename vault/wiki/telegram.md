---
title: Telegram bot
tags: [subsystem, network]
status: active
updated: 2026-09-01
summary: bridge/telegram_bot.py — long-poll; each message goes to claude -p, replies by voice or text.
---

# Telegram bot — `bridge/telegram_bot.py`

Long-polling against the Telegram API. Only serves `JARVIS_TELEGRAM_CHAT_ID`. Each
message → `ask_claude` → reply as a voice note (Kokoro) or text (`JARVIS_TG_VOICE=0`).

## `ask_claude`

`claude -p --output-format json --resume <session_id>` — the **same** session as the
[[bridge]] → coordinated by [[sesion-claude]].

## Ollama fallback ([[pr-5-telegram-ollama-jobs]])

Before: out of tokens it replied `(error claude: ...)` and nothing else. Now it tries
[[ollama-fallback]] when `claude` exits with an error, times out, won't start, returns empty
or prints a limit message. Prefixes `⚠️ Usando Ollama`.

## Pending

- The loop blocks for up to 120 s per message (processes no others meanwhile).
- It doesn't understand incoming voice notes (text only).

## Related

[[bridge]] · [[ollama-fallback]] · [[sesion-claude]] · [[notificaciones]]
