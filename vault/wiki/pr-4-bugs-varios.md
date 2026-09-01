---
title: "PR #4 — bugs varios"
tags: [pr, ops]
status: abierto
updated: 2026-09-01
summary: Recordatorios duplicados, Telegram >4096, watchdog frágil, timeouts sin capturar.
---

# PR #4 — `fix/bugs-recordatorios-telegram-watchdog`

De una revisión de `bin/` + `bridge/` + `agents/`:

1. `bin/check-reminders` repetía cada recordatorio cada 30 min → `bridge/reminders_state.json`.
2. `notify.send_telegram` fallaba mudo con >4096 chars → trocea a ≤4000 + error real.
3. `watchdog.check_bridge` daba falso "caído" con 4xx → solo 5xx/timeout.
4. `TimeoutExpired` de `notify.py` abortaba watchdog/reminders antes de `save_state` → capturado.
5. `seguimiento.llm_digest` petaba con `price` None.

Ver [[watchdog]] · [[notificaciones]] · [[seguimiento]].
