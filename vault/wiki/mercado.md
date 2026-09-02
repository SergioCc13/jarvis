---
title: Análisis de mercado
tags: [subsistema, mercado]
status: activo
updated: 2026-09-01
summary: bin/analiza — informe completo multi-agente los lunes, rápido (1 llamada) a diario.
---

# Análisis de mercado — `bin/analiza`

Genera el email **"Jarvis: Mercado"** (+ Telegram). Datos de `agents/trading.py` (Yahoo /
CoinGecko, stdlib, sin pip); indicadores de [[seguimiento]] (`build_snapshot`).

## Dos modos ([[pr-2-mercado-cadencia]])

| Cuándo | Comando | Coste |
|---|---|---|
| **Lunes** | `bin/analiza` | multi-agente, ~127 llamadas `claude -p`, ~20-40 min |
| **Resto** | `bin/analiza --rapido` | **1 llamada**, resumen de 180 palabras |

## Motor multi-agente — `agents/analistas.py`

Por activo, cadena de 6 roles (técnico → contexto → alcista → bajista → trader → riesgo),
cada rol re-manda el trabajo previo en el prompt (de ahí el coste). Bloque final por activo:
Puntuación 0-100, Recomendación, Plazo, entrada/salida, próximo evento, justificación. Luego
un rol de cartera escribe la "Visión de cartera". `--patch` reintenta solo los activos fallidos.

## Fechas y gráfico (antes sin usar, cableado en [[pr-2-mercado-cadencia]])

- `agents/calendar_data.py`: **fecha real** de la próxima Fed (FOMC 2026 oficial) +
  resultados/dividendos de Yahoo. La línea "Próximo evento relevante" se **sobrescribe**
  con esto; el LLM ya no la inventa.
- `agents/charts.py --scores`: gráfico de barras 0-100 adjunto al email (0 tokens; necesita
  `python3-matplotlib`).

## Relacionado

[[seguimiento]] · [[coste-tokens]] · [[cron]] · [[pr-2-mercado-cadencia]]
