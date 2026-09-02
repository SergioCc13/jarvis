---
title: Seguimiento de watchlist
tags: [subsistema, mercado]
status: activo
updated: 2026-09-01
summary: agents/seguimiento.py — indicadores + SQLite; LLM solo si un ticker dispara señal.
---

# Seguimiento — `agents/seguimiento.py` / `bin/seguimiento`

Complementa a [[mercado]]: en vez de resumir todo cada día, calcula indicadores y **solo
llama al LLM para los tickers con señal**. Días tranquilos: 0 tokens, no notifica.

## Qué calcula

`build_snapshot(symbol)`: precio, `chg_1d/5d/20d`, RSI 14 (Wilder), SMA 50/200, distancia a
máx/mín 52 s, `vol_ratio` (vol hoy / media 20 d). Series de 1 año (Yahoo o CoinGecko).

## Señales (`detect_events`, umbrales `JARVIS_SEG_*`)

Movimiento 1d ≥4 %, 5d ≥8 %, volumen ×2, RSI ≥75 / ≤25, a <2 % de máx/mín 52 s,
cruce de medias 50/200 (golden / death cross) vs el snapshot anterior.

## Almacén

SQLite en `vault/raw/seguimiento.db`: `snapshots` (histórico) y `flags` (las señales, con
`ret` que rellena luego `bin/seguimiento score` para ver si el filtro acierta).

## Salida

Digest en `vault/outputs/seguimiento.md`; [[mercado]] lo adjunta a su email. Standalone:
`bin/seguimiento scan --notify --email`.

## Relacionado

[[mercado]] · [[coste-tokens]] · [[cron]]
