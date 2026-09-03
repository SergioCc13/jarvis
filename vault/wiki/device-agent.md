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
- **`JARVIS_AGENT_SHELL_PIN`** (2026-09-03): segundo secreto, solo para
  `action:"shell"`, separado del token del dispositivo — hay que mandarlo en
  `params.pin`, comparación con `hmac.compare_digest` (tiempo constante).
  Robar el token solo ya no alcanza para RCE. Auditoría de cada intento
  (correcto o no) en `agents/shell-audit.log`. Recuperación si te olvidás el
  PIN: `GET /pin-recover` (autenticado con el token) te lo manda por email —
  usa `JARVIS_EMAIL_*` propio de `agents/.env`, TLS siempre verificado (sin el
  fallback MITM-tolerante de `bridge/notify.py`, no corresponde para un
  secreto). Blanco = `shell` sigue funcionando solo con el token, como antes.

## Riesgo residual

`shell=True` por HTTP: aceptable solo porque está tras Tailscale y el token ya no
puede filtrarse por URL/logs (ver [[fix-token-query-string]]). Con `JARVIS_AGENT_SHELL_PIN`
configurado, un token filtrado ya no alcanza por sí solo — pero si el PIN se
comparte por el mismo canal que el token (ej. ambos en el mismo mensaje), la
protección extra se pierde. No exponer nunca fuera de la tailnet.

## Relacionado

[[bridge]] · [[pr-6-hardening]]
