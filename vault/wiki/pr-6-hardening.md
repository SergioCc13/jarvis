---
title: "PR #6 — endurecimiento"
tags: [pr, ops]
status: abierto
updated: 2026-09-01
summary: Lock de sesión Claude, agente de dispositivo más cerrado, vault-refresh sin gasto extra.
---

# PR #6 — `feat/endurece-sesion-agente-vault`

- **`bridge/session_lock.py`** (nuevo): lock `fcntl` para que [[bridge]] y [[telegram]] no
  hagan `claude --resume <misma sesión>` a la vez. Ver [[sesion-claude]].
- **`agents/device_agent.py`:** bind a IP de Tailscale, token por cabecera `X-Jarvis-Token`,
  `JARVIS_AGENT_ALLOW_SHELL=0`, cuerpo ≤ 1 MiB. Ver [[device-agent]].
- **`bin/vault-refresh`:** omite skills ya frescos hoy. Ver [[vault-refresh]].

Ver [[sesion-claude]] · [[device-agent]] · [[vault-refresh]].
