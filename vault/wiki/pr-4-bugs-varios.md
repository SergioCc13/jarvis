---
title: "PR #4 — assorted bugs"
tags: [pr, ops]
status: open
updated: 2026-09-01
summary: Duplicate reminders, Telegram >4096, fragile watchdog, uncaught timeouts.
---

# PR #4 — `fix/bugs-recordatorios-telegram-watchdog`

From a review of `bin/` + `bridge/` + `agents/`:

1. `bin/check-reminders` repeated every reminder every 30 min → `bridge/reminders_state.json`.
2. `notify.send_telegram` failed silently at >4096 chars → splits into ≤4000 + a real error.
3. `watchdog.check_bridge` reported a false "down" on 4xx → only 5xx/timeout now.
4. A `TimeoutExpired` from `notify.py` aborted watchdog/reminders before `save_state` → now caught.
5. `seguimiento.llm_digest` crashed with `price` None.

See [[watchdog]] · [[notificaciones]] · [[seguimiento]].
