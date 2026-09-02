---
title: Coste de tokens
tags: [decision, llm]
status: vivo
updated: 2026-09-01
summary: Prioridad del proyecto — minimizar consumo de cuota; preferir stdlib a llamadas LLM.
---

# Coste de tokens

Preocupación recurrente de Sergio: **vigilar el consumo de cuota** y preferir siempre la
vía barata.

## Dónde se va

| Sitio | Antes | Ahora |
|---|---|---|
| [[mercado]] multi-agente | ~127 `claude -p` **cada día** | solo lunes; `--rapido` = 1 llamada ([[pr-2-mercado-cadencia]]) |
| [[vault-refresh]] | 4 `claude -p` cada mañana | omite los ya frescos ([[pr-6-hardening]]) |
| [[seguimiento]] | — | ya llama al LLM solo si hay señal |
| Sin tokens | error mudo | cae a [[ollama-fallback]] |

## Regla al extender Jarvis

Preferir helpers deterministas de stdlib a llamadas al LLM. Mantener el multi-agente
**opt-in**. Cada `claude -p` arranca con ~15k tokens de contexto de Claude Code antes del
prompt, así que lo caro es el **número de invocaciones**, no el prompt.

Ver [[mercado]] · [[ollama-fallback]] · [[vault-refresh]].
