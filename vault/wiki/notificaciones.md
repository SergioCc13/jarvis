---
title: Notificaciones
tags: [subsistema, red]
status: activo
updated: 2026-09-01
summary: bridge/notify.py — Discord / Telegram / email desde un solo dispatch().
---

# Notificaciones — `bridge/notify.py`

`dispatch(mensaje, channels=[...], subject=...)`. Canales según env: `JARVIS_DISCORD_WEBHOOK`,
`JARVIS_TELEGRAM_TOKEN`+`_CHAT_ID`, `JARVIS_EMAIL_*` (Gmail App Password). `_urlopen` reintenta
verificado→sin-verificar (redes con MITM corporativo).

Lo usan [[watchdog]], [[seguimiento]], [[mercado]], `bin/morning-brief`, `bin/check-reminders`.

## Arreglos de [[pr-4-bugs-varios]]

- `send_telegram`: Telegram corta `sendMessage` en 4096 chars y fallaba mudo. Ahora
  **trocea** por líneas a ≤4000 y, si Telegram responde error, devuelve código + cuerpo.

## Pendiente

- `send_email` no adjunta ficheros → lo añade [[pr-2-mercado-cadencia]] (para el gráfico).

## Relacionado

[[telegram]] · [[watchdog]] · [[cron]] · [[pr-4-bugs-varios]]
