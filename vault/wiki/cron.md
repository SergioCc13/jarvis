---
title: Pi cron
tags: [subsystem, ops]
status: active
updated: 2026-09-01
summary: What runs and when on the Raspberry Pi; installed by bin/install-pi.
---

# Pi cron

A `# === Jarvis ===` block in the crontab, installed/updated by `bin/install-pi`.

| When | Job | Note |
|---|---|---|
| `*/5 * * * *` | `bin/auto-update` | git pull + restart of affected services |
| `*/5 * * * *` | `bin/watchdog` | see [[watchdog]] |
| `*/30 * * * *` | `bin/check-reminders` | see [[watchdog]] |
| `30 7 * * *` | `bin/vault-refresh` | see [[vault-refresh]] |
| `0 8 * * *` | `bin/morning-brief` | morning summary |
| `0 8 * * *` | `bin/seguimiento` | see [[seguimiento]] |
| `0 7 * * *` (today) → Monday/quick | `bin/analiza` | see [[mercado]] · changed by [[pr-2-mercado-cadencia]] |
| `0 18 * * 5` | `bin/seguimiento score` | filter diagnostic |

## Pending ([[ideas-pendientes]])

Several jobs collide at `0 8` (brief + seguimiento) and near 7 → stagger them 2-3 min apart so
they don't blow Yahoo/CoinGecko's rate limit. Parked until [[pr-2-mercado-cadencia]] merges
(it touches the same `bin/install-pi` lines).

## Related

[[mercado]] · [[seguimiento]] · [[watchdog]] · [[vault-refresh]]
