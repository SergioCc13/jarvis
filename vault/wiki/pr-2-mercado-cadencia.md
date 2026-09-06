---
title: "PR #2 — market: weekly + daily"
tags: [pr, mercado]
status: open
updated: 2026-09-01
summary: Multi-agent on Mondays only, quick daily; + real dates and a scores chart.
---

# PR #2 — `feat/mercado-semanal-completo-diario-rapido`

- **Cadence:** `bin/analiza` full on **Mondays**, `--rapido` (1 call) the rest of the week.
  Cron in `bin/install-pi`.
- **Real dates:** wires in `agents/calendar_data.py` (official FOMC + Yahoo earnings) and
  **overwrites** the "Próximo evento relevante" line in the final block. `--rapido` also
  gets the Fed date.
- **Chart:** `agents/charts.py --scores` attached to the email. `bridge/notify.send_email` and
  `dispatch` accept `attachments`; `bin/install-pi` installs `python3-matplotlib`.

Touches the cron lines in `bin/install-pi` → merge before touching [[cron]].

See [[mercado]] · [[seguimiento]] · [[coste-tokens]].
