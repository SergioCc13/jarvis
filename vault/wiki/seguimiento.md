---
title: Watchlist tracking
tags: [subsystem, mercado]
status: active
updated: 2026-09-01
summary: agents/seguimiento.py — indicators + SQLite; LLM only when a ticker trips a signal.
---

# Tracking — `agents/seguimiento.py` / `bin/seguimiento`

Complements [[mercado]]: instead of summarizing everything every day, it computes indicators
and **only calls the LLM for tickers with a signal**. Quiet days: 0 tokens, no notification.

## What it computes

`build_snapshot(symbol)`: price, `chg_1d/5d/20d`, RSI 14 (Wilder), SMA 50/200, distance to
the 52-week high/low, `vol_ratio` (today's volume / 20-day average). 1-year series (Yahoo or CoinGecko).

## Signals (`detect_events`, thresholds `JARVIS_SEG_*`)

1d move ≥4%, 5d ≥8%, volume ×2, RSI ≥75 / ≤25, within <2% of the 52-week high/low,
50/200 moving-average cross (golden / death cross) vs the previous snapshot.

## Store

SQLite at `vault/raw/seguimiento.db`: `snapshots` (history) and `flags` (the signals, with a
`ret` that `bin/seguimiento score` fills in later to check whether the filter got it right).

## Output

Digest in `vault/outputs/seguimiento.md`; [[mercado]] attaches it to its email. Standalone:
`bin/seguimiento scan --notify --email`.

## Related

[[mercado]] · [[coste-tokens]] · [[cron]]
