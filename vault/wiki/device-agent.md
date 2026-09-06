---
title: Device agent
tags: [subsystem, network]
status: active
updated: 2026-09-01
summary: agents/device_agent.py — HTTP :8793 on each machine; runs actions (shell, apps, volume…).
---

# Device agent — `agents/device_agent.py`

Runs on Mac/PC. On startup it registers with the hub ([[bridge]] `/register`) and heartbeats
every 60 s. Exposes `POST /execute` so Jarvis can control the machine over Tailscale.

## Actions (`execute_action`)

`shell` (arbitrary), `open_app`, `open_url`, `volume`, `mute`, `notify`, `screenshot`,
`sleep`, `get_status` (battery, apps). Capabilities depend on the platform.

## Hardening ([[pr-6-hardening]])

- Bind to the **Tailscale IP** instead of `0.0.0.0` (`JARVIS_AGENT_BIND` to override).
- Token **only** via the `X-Jarvis-Token` header (2026-09-03: the `?token=` fallback that
  lingered "for compat" was removed — the query string leaks into logs, see
  [[fix-token-query-string]]). `_try_register()` sends `HUB_TOKEN` the same way, by header.
- **`JARVIS_AGENT_ALLOW_SHELL=0`** disables `shell` entirely.
- POST body ≤ 1 MiB; shell output truncated to 20k.
- **`JARVIS_AGENT_SHELL_PIN`** (2026-09-03): a second secret, for `action:"shell"` only,
  separate from the device token — it has to be sent in `params.pin`, compared with
  `hmac.compare_digest` (constant time). Stealing the token alone is no longer enough for RCE.
  Every attempt (right or wrong) is audited in `agents/shell-audit.log`. If you forget the PIN:
  `GET /pin-recover` (authenticated with the token) emails it to you — uses `agents/.env`'s own
  `JARVIS_EMAIL_*`, TLS always verified (no MITM-tolerant fallback like `bridge/notify.py`'s —
  not appropriate for a secret). By design, `shell` still works with just the token, as before.

## Residual risk

`shell=True` over HTTP: acceptable only because it's behind Tailscale and the token can no
longer leak via URL/logs (see [[fix-token-query-string]]). With `JARVIS_AGENT_SHELL_PIN` set,
a leaked token isn't enough on its own — but if the PIN travels over the same channel as the
token (e.g. both in one message), that extra protection is lost. Never expose outside the tailnet.

## Related

[[bridge]] · [[pr-6-hardening]]
