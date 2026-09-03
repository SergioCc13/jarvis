---
title: "Fix — tokens fuera de la query string"
tags: [fix, seguridad]
status: cerrado
updated: 2026-09-03
summary: Bridge, device_agent y HUB_TOKEN dejan de mandar el token por ?token= (salvo /events) — se filtraba en journalctl/logs.
---

# Fix — tokens fuera de la query string

**Motivo:** `?token=...` en la URL queda en texto plano en `journalctl -u jarvis-bridge`
(confirmado en vivo el 2026-09-03) y en cualquier log de acceso. Combinado con
[[device-agent]] (shell remoto arbitrario), una filtración de log daba un camino a
ejecución de comandos sin necesidad de estar en la tailnet.

## Cambios

- **`bridge/server.py`:** nuevo `Handler._bearer_token()` (lee `Authorization: Bearer
  <token>`). Todos los endpoints lo usan — `/chat`, `/chat/image`, `/chat/result`,
  `/devices`, `/register`, `/voice`, `/`. Único endpoint que conserva `?token=` como
  fallback: `/events`, porque el `EventSource` nativo del navegador no puede mandar
  headers propios.
- **`agents/device_agent.py`:** se eliminó el fallback `?token=` que quedaba "por
  compat" — ahora solo header `X-Jarvis-Token`. `_try_register()` manda `HUB_TOKEN`
  como `Authorization: Bearer` en vez de en la URL de `/register`.
- **`hud/index.html`:** los 4 `fetch()` (`/chat`, `/chat/result`, `/chat/image`,
  `/voice`) pasan a header `Authorization`. `/events` se queda igual (ver arriba).
- **`CLAUDE.md`:** ejemplos de `curl` para despachar comandos a dispositivos
  actualizados a `-H "X-Jarvis-Token: ..."` / `-H "Authorization: Bearer ..."`.

## Riesgo residual

`/events` sigue exponiendo el token en la URL — es una limitación real de la API
`EventSource`, no un descuido. El impacto es menor que en los demás endpoints (solo
recibe avisos de estado, no permite ejecutar acciones), pero sigue siendo el mismo
tipo de fuga si alguien lee esos logs.

Ver [[bridge]] · [[device-agent]].
