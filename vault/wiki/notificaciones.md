---
title: Notifications
tags: [subsystem, network]
status: active
updated: 2026-09-01
summary: bridge/notify.py — Discord / Telegram / email from a single dispatch().
---

# Notifications — `bridge/notify.py`

`dispatch(message, channels=[...], subject=...)`. Channels depend on env: `JARVIS_DISCORD_WEBHOOK`,
`JARVIS_TELEGRAM_TOKEN`+`_CHAT_ID`, `JARVIS_EMAIL_*` (Gmail App Password). `_urlopen` retries
verified→unverified (networks with a corporate MITM).

Used by [[watchdog]], [[seguimiento]], [[mercado]], `bin/morning-brief`, `bin/check-reminders`.

## Fixes from [[pr-4-bugs-varios]]

- `send_telegram`: Telegram caps `sendMessage` at 4096 chars and it failed silently. Now it
  **splits** on line boundaries to ≤4000 and, if Telegram returns an error, gives back code + body.

## Pending

- `send_email` doesn't attach files → added by [[pr-2-mercado-cadencia]] (for the chart).

## Related

[[telegram]] · [[watchdog]] · [[cron]] · [[pr-4-bugs-varios]]
