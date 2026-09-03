---
title: Agente de dispositivo
tags: [subsistema, red]
status: activo
updated: 2026-09-01
summary: agents/device_agent.py — HTTP :8793 en cada equipo; ejecuta acciones (shell, apps, volumen…).
---

# Agente de dispositivo — `agents/device_agent.py`

Corre en Mac/PC. Al arrancar se registra en el hub ([[bridge]] `/register`) y hace heartbeat
cada 60 s. Expone `POST /execute` para que Jarvis controle el equipo por Tailscale.

## Acciones (`execute_action`)

`shell` (arbitrario), `open_app`, `open_url`, `volume`, `mute`, `notify`, `screenshot`,
`sleep`, `get_status` (batería, apps). Capacidades según plataforma.

## Endurecimiento ([[pr-6-hardening]])

- Bind a la **IP de Tailscale** en vez de `0.0.0.0` (`JARVIS_AGENT_BIND` para forzar).
- Token **solo** por cabecera `X-Jarvis-Token` (2026-09-03: se quitó el fallback
  `?token=` que quedaba "por compat" — la query string se filtra a logs, ver
  [[fix-token-query-string]]). `_try_register()` manda `HUB_TOKEN` igual, por header.
- **`JARVIS_AGENT_ALLOW_SHELL=0`** desactiva `shell` del todo.
- Cuerpo POST ≤ 1 MiB; salida de shell recortada a 20k.

## Riesgo residual

`shell=True` por HTTP: aceptable solo porque está tras Tailscale y el token ya no
puede filtrarse por URL/logs (ver [[fix-token-query-string]]). No exponer nunca fuera.

## Relacionado

[[bridge]] · [[pr-6-hardening]]
