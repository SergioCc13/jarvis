---
title: Watchdog y recordatorios
tags: [subsistema, ops]
status: activo
updated: 2026-09-01
summary: bin/watchdog vigila servicios; bin/check-reminders avisa de recordatorios próximos.
---

# Watchdog y recordatorios

## `bin/watchdog` (cada 5 min)

Comprueba bridge (:8792), proceso del bot de Telegram, y dispositivos (`last_seen` en
`devices.json`, offline >5 min). Alerta por [[notificaciones]] solo en el **cambio** de
estado (guarda `bridge/watchdog_state.json`).

## `bin/check-reminders` (cada 30 min)

Lee `vault/outputs/recordatorios.md`, avisa de los de hoy con hora dentro de la ventana
(−5 a +30 min).

## Arreglos de [[pr-4-bugs-varios]]

- `check-reminders` no guardaba estado → repetía cada recordatorio 2-3 veces. Ahora
  `bridge/reminders_state.json` (una notificación por recordatorio).
- `watchdog.check_bridge` contaba cualquier 4xx como "caído" → ahora solo 5xx/timeout.
- `TimeoutExpired` de `notify.py` abortaba la corrida antes de guardar estado → capturado.

## Relacionado

[[cron]] · [[notificaciones]] · [[pr-4-bugs-varios]]
