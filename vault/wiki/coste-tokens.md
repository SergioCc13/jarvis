---
title: Token cost
tags: [decision, llm]
status: living
updated: 2026-09-01
summary: Project priority — minimize quota usage; prefer stdlib over LLM calls.
---

# Token cost

Sergio's recurring concern: **watch quota usage** and always prefer the cheap path.

## Where it goes

| Place | Before | Now |
|---|---|---|
| [[mercado]] multi-agent | ~127 `claude -p` **every day** | Mondays only; `--rapido` = 1 call ([[pr-2-mercado-cadencia]]) |
| [[vault-refresh]] | 4 `claude -p` every morning | skips the ones already fresh ([[pr-6-hardening]]) |
| [[seguimiento]] | — | already calls the LLM only when there's a signal |
| Out of tokens | silent error | falls back to [[ollama-fallback]] |

## Rule when extending Jarvis

Prefer deterministic stdlib helpers over LLM calls. Keep the multi-agent path **opt-in**.
Each `claude -p` starts with ~15k tokens of Claude Code context before the prompt, so the
expensive part is the **number of invocations**, not the prompt.

See [[mercado]] · [[ollama-fallback]] · [[vault-refresh]].
