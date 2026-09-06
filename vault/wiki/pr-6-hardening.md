---
title: "PR #6 — hardening"
tags: [pr, ops]
status: open
updated: 2026-09-01
summary: Claude session lock, a more locked-down device agent, vault-refresh with no extra spend.
---

# PR #6 — `feat/endurece-sesion-agente-vault`

- **`bridge/session_lock.py`** (new): an `fcntl` lock so [[bridge]] and [[telegram]] don't
  run `claude --resume <same session>` at the same time. See [[sesion-claude]].
- **`agents/device_agent.py`:** bind to the Tailscale IP, token via the `X-Jarvis-Token` header,
  `JARVIS_AGENT_ALLOW_SHELL=0`, body ≤ 1 MiB. See [[device-agent]].
- **`bin/vault-refresh`:** skips skills already refreshed today. See [[vault-refresh]].

See [[sesion-claude]] · [[device-agent]] · [[vault-refresh]].
