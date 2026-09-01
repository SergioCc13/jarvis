---
title: vault-refresh
tags: [subsistema, ops]
status: activo
updated: 2026-09-01
summary: bin/vault-refresh regenera vault/outputs/*.md con skills de voz antes del brief.
---

# vault-refresh — `bin/vault-refresh`

Antes del `morning-brief`, corre los skills de voz de Jarvis (`plan`, `habitos`,
`recordatorios`, `inbox`) para dejar `vault/outputs/*.md` frescos, que es lo que enseña
el [[hud]].

Cada skill es una llamada `claude -p`.

## Arreglo de [[pr-6-hardening]]

**Omite** el skill cuyo `vault/outputs/<skill>.md` ya sea de hoy → 0-4 llamadas menos si el
cron se repite. `--force` regenera todo. (`date -r` funciona en macOS y GNU.)

## Relacionado

[[cron]] · [[coste-tokens]] · [[wiki-como-funciona]]
