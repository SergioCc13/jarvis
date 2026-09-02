---
title: "PR #2 — mercado: semanal + diario"
tags: [pr, mercado]
status: abierto
updated: 2026-09-01
summary: Multi-agente solo los lunes, rápido a diario; + fechas reales y gráfico de puntuaciones.
---

# PR #2 — `feat/mercado-semanal-completo-diario-rapido`

- **Cadencia:** `bin/analiza` completo los **lunes**, `--rapido` (1 llamada) el resto.
  Cron en `bin/install-pi`.
- **Fechas reales:** cablea `agents/calendar_data.py` (FOMC oficial + resultados Yahoo) y
  **sobrescribe** la línea "Próximo evento relevante" del bloque final. El `--rapido` también
  recibe la fecha de la Fed.
- **Gráfico:** `agents/charts.py --scores` adjunto al email. `bridge/notify.send_email` y
  `dispatch` aceptan `attachments`; `bin/install-pi` instala `python3-matplotlib`.

Toca las líneas del cron de `bin/install-pi` → mergear antes de tocar [[cron]].

Ver [[mercado]] · [[seguimiento]] · [[coste-tokens]].
