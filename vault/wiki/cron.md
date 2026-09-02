---
title: Cron de la Pi
tags: [subsistema, ops]
status: activo
updated: 2026-09-01
summary: Qué corre y cuándo en la Raspberry Pi; lo instala bin/install-pi.
---

# Cron de la Pi

Bloque `# === Jarvis ===` en el crontab, instalado/actualizado por `bin/install-pi`.

| Cuándo | Job | Nota |
|---|---|---|
| `*/5 * * * *` | `bin/auto-update` | git pull + reinicio de servicios afectados |
| `*/5 * * * *` | `bin/watchdog` | ver [[watchdog]] |
| `*/30 * * * *` | `bin/check-reminders` | ver [[watchdog]] |
| `30 7 * * *` | `bin/vault-refresh` | ver [[vault-refresh]] |
| `0 8 * * *` | `bin/morning-brief` | resumen matutino |
| `0 8 * * *` | `bin/seguimiento` | ver [[seguimiento]] |
| `0 7 * * *` (hoy) → lunes/rápido | `bin/analiza` | ver [[mercado]] · lo cambia [[pr-2-mercado-cadencia]] |
| `0 18 * * 5` | `bin/seguimiento score` | diagnóstico del filtro |

## Pendiente ([[ideas-pendientes]])

Varios jobs chocan a las `0 8` (brief + seguimiento) y cerca de las 7 → escalonar 2-3 min
para no reventar el rate-limit de Yahoo/CoinGecko. Aparcado hasta mergear [[pr-2-mercado-cadencia]]
(toca las mismas líneas de `bin/install-pi`).

## Relacionado

[[mercado]] · [[seguimiento]] · [[watchdog]] · [[vault-refresh]]
