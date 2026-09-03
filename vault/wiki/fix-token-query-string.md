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

## Segunda vuelta (2026-09-03, misma sesión) — CORS, ticket de /events, auditoría

- **CORS:** `bridge/server.py` y `agents/device_agent.py` mandaban
  `Access-Control-Allow-Origin: *` en todo. Ahora `bridge/server.py` solo refleja
  el `Origin` si está en `JARVIS_ALLOWED_ORIGINS` (o, sin configurar, si termina en
  `.ts.net`); `device_agent.py` directamente dejó de mandar cabeceras CORS —
  nada del repo lo llama desde JS de navegador, solo `curl`/Bash.
- **`/events`:** ya no acepta el token real por `?token=`. `hud/index.html` primero
  pide un ticket de un solo uso vía `GET /events/ticket` (autenticado con el
  header de siempre) y recién con eso abre el `EventSource`. El ticket expira en
  30s o al primer uso — si se filtra a un log, ya no sirve para nada.
- **Auditoría en `device_agent`:** cada `action: "shell"` queda registrado (IP de
  origen + comando) en `agents/shell-audit.log` (gitignored) y por stderr. No
  evita el abuso, pero lo hace visible.

## Riesgo residual (sin tocar)

- `agents/device_agent.py` sigue siendo shell remoto arbitrario por diseño —
  aceptado y documentado en [[device-agent]]. Alternativas evaluadas y no
  aplicadas: quitar `shell` y dejar solo acciones con nombre, aprobación humana
  antes de ejecutar, o (la más sólida) restringir por ACL de Tailscale qué
  dispositivos pueden alcanzar el puerto 8793 — esto último requiere acceso a la
  consola de admin de Tailscale, fuera del alcance de este repo.
- Whisper/Kokoro (voicemode, no es código de este repo) escuchan en `0.0.0.0`
  sin ningún token — confirmado en vivo en esta PC (Kokoro `:8880`). Alcanzable
  no solo desde la tailnet sino desde cualquiera en la misma red WiFI/LAN.
  Mitigación real: regla de firewall (Windows/macOS/Linux según el dispositivo)
  que solo permita esos puertos desde el rango de Tailscale — no aplicado, es un
  cambio de sistema en vivo que hay que decidir con cuidado, no algo para tocar
  sin más.
- Modelo de confianza de `bin/auto-update`: hace `git reset --hard origin/main`
  sin ninguna verificación y ahora sí reinicia los servicios de forma fiable — si
  se compromete la cuenta de GitHub `SergioCc13`, el código llega y se ejecuta
  solo en ≤5 min. Mitigación fuera de este repo: activar 2FA en la cuenta de
  GitHub, considerar protección de rama en `main`.

Ver [[bridge]] · [[device-agent]].
