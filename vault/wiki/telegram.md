---
title: Bot de Telegram
tags: [subsistema, red]
status: activo
updated: 2026-09-01
summary: bridge/telegram_bot.py — long-poll; cada mensaje va a claude -p, responde por voz o texto.
---

# Bot de Telegram — `bridge/telegram_bot.py`

Long-polling contra la API de Telegram. Solo atiende a `JARVIS_TELEGRAM_CHAT_ID`. Cada
mensaje → `ask_claude` → respuesta como nota de voz (Kokoro) o texto (`JARVIS_TG_VOICE=0`).

## `ask_claude`

`claude -p --output-format json --resume <session_id>` — la **misma** sesión que el
[[bridge]] → coordinado por [[sesion-claude]].

## Fallback a Ollama ([[pr-5-telegram-ollama-jobs]])

Antes: sin tokens respondía `(error claude: ...)` y punto. Ahora prueba [[ollama-fallback]]
cuando `claude` sale con error, hace timeout, no arranca, devuelve vacío o emite un
mensaje de límite. Prefija `⚠️ Usando Ollama`.

## Pendiente

- El bucle se bloquea hasta 120 s por mensaje (no procesa otros mientras).
- No entiende notas de voz entrantes (solo texto).

## Relacionado

[[bridge]] · [[ollama-fallback]] · [[sesion-claude]] · [[notificaciones]]
