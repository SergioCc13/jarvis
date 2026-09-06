---
title: Market analysis
tags: [subsystem, mercado]
status: active
updated: 2026-09-01
summary: bin/analiza — full multi-agent report on Mondays, quick (1 call) daily.
---

# Market analysis — `bin/analiza`

Generates the **"Jarvis: Mercado"** email (+ Telegram). Data from `agents/trading.py` (Yahoo /
CoinGecko, stdlib, no pip); indicators from [[seguimiento]] (`build_snapshot`).

## Two modes ([[pr-2-mercado-cadencia]])

| When | Command | Cost |
|---|---|---|
| **Monday** | `bin/analiza` | multi-agent, ~127 `claude -p` calls, ~20-40 min |
| **Rest** | `bin/analiza --rapido` | **1 call**, 180-word summary |

## Multi-agent engine — `agents/analistas.py`

Per asset, a chain of 6 roles (technical → context → bull → bear → trader → risk), each role
re-feeding the previous work in the prompt (hence the cost). Final block per asset:
Score 0-100, Recommendation, Horizon, entry/exit, next event, rationale. Then a portfolio
role writes the "Visión de cartera". `--patch` retries only the failed assets.

## Dates and chart (previously unused, wired in [[pr-2-mercado-cadencia]])

- `agents/calendar_data.py`: the **real date** of the next Fed meeting (official 2026 FOMC) +
  Yahoo earnings/dividends. The "Próximo evento relevante" line is **overwritten** with this;
  the LLM no longer invents it.
- `agents/charts.py --scores`: a 0-100 bar chart attached to the email (0 tokens; needs
  `python3-matplotlib`).

## Related

[[seguimiento]] · [[coste-tokens]] · [[cron]] · [[pr-2-mercado-cadencia]]
