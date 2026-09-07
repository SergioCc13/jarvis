---
title: Watchdog and reminders
tags: [subsystem, ops]
status: active
updated: 2026-09-01
summary: bin/watchdog watches services; bin/check-reminders warns about upcoming reminders.
---

# Watchdog and reminders

## `bin/watchdog` (every 5 min)

Checks the bridge (:8792), the Telegram bot process, and devices (`last_seen` in
`devices.json`, offline >20 min — raised from 5 min so a brief network hiccup doesn't spam a
notification). Alerts via [[notificaciones]] only on a state **change**
(stores `bridge/watchdog_state.json`).

## `bin/check-reminders` (every 30 min)

Reads `vault/outputs/recordatorios.md`, warns about today's reminders whose time falls in
the window (−5 to +30 min).

## Fixes from [[pr-4-bugs-varios]]

- `check-reminders` didn't persist state → repeated every reminder 2-3 times. Now
  `bridge/reminders_state.json` (one notification per reminder).
- `watchdog.check_bridge` counted any 4xx as "down" → now only 5xx/timeout.
- A `TimeoutExpired` from `notify.py` aborted the run before saving state → now caught.

## Related

[[cron]] · [[notificaciones]] · [[pr-4-bugs-varios]]
