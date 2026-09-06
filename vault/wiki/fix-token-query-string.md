---
title: "Fix — tokens out of the query string"
tags: [fix, seguridad]
status: closed
updated: 2026-09-03
summary: Bridge, device_agent and HUB_TOKEN stop sending the token via ?token= (except /events) — it leaked into journalctl/logs.
---

# Fix — tokens out of the query string

**Why:** `?token=...` in the URL ends up in plain text in `journalctl -u jarvis-bridge`
(confirmed live 2026-09-03) and in any access log. Combined with [[device-agent]] (arbitrary
remote shell), a log leak gave a path to command execution without even being on the tailnet.

## Changes

- **`bridge/server.py`:** new `Handler._bearer_token()` (reads `Authorization: Bearer
  <token>`). Every endpoint uses it — `/chat`, `/chat/image`, `/chat/result`, `/devices`,
  `/register`, `/voice`, `/`. The only endpoint that keeps `?token=` as a fallback: `/events`,
  because the browser's native `EventSource` can't send custom headers.
- **`agents/device_agent.py`:** the `?token=` fallback that lingered "for compat" was removed —
  now header `X-Jarvis-Token` only. `_try_register()` sends `HUB_TOKEN` as
  `Authorization: Bearer` instead of in the `/register` URL.
- **`hud/index.html`:** all 4 `fetch()` calls (`/chat`, `/chat/result`, `/chat/image`,
  `/voice`) move to an `Authorization` header. `/events` stays as-is (see above).
- **`CLAUDE.md`:** the `curl` examples for dispatching commands to devices updated to
  `-H "X-Jarvis-Token: ..."` / `-H "Authorization: Bearer ..."`.

## Second pass (2026-09-03, same session) — CORS, /events ticket, audit

- **CORS:** `bridge/server.py` and `agents/device_agent.py` sent
  `Access-Control-Allow-Origin: *` on everything. Now `bridge/server.py` only reflects the
  `Origin` if it's in `JARVIS_ALLOWED_ORIGINS` (or, unset, if it ends in `.ts.net`);
  `device_agent.py` stopped sending CORS headers entirely — nothing in the repo calls it from
  browser JS, only `curl`/Bash.
- **`/events`:** no longer accepts the real token via `?token=`. `hud/index.html` first
  requests a one-shot ticket via `GET /events/ticket` (authenticated with the usual header)
  and only then opens the `EventSource`. The ticket expires in 30s or on first use — if it
  leaks into a log, it's already worthless.
- **Audit in `device_agent`:** every `action: "shell"` is logged (source IP + command) to
  `agents/shell-audit.log` (gitignored) and to stderr. It doesn't prevent abuse, but it makes
  it visible.

## Residual risk (untouched)

- `agents/device_agent.py` is still arbitrary remote shell by design — accepted and documented
  in [[device-agent]]. Alternatives evaluated and not applied: drop `shell` and keep only named
  actions, human approval before running, or (the strongest) restrict via a Tailscale ACL which
  devices can reach port 8793 — that last one needs access to the Tailscale admin console,
  outside this repo's scope.
- Whisper/Kokoro (voicemode, not this repo's code) listen on `0.0.0.0` with no token —
  confirmed live on this PC (Kokoro `:8880`). Reachable not just from the tailnet but from
  anyone on the same WiFi/LAN. Real mitigation: a firewall rule (Windows/macOS/Linux depending
  on the device) that only allows those ports from the Tailscale range — not applied, it's a
  live system change to decide carefully, not something to touch lightly.
- `bin/auto-update`'s trust model: the old version did `git reset --hard origin/main` every
  5 min with no verification — it could silently orphan local work, and a compromised
  `SergioCc13` GitHub account would run code on every device within ≤5 min. **Rewritten
  2026-09-06**: it is now **fast-forward only** — no `reset --hard`, no stash; it skips the
  run (leaving the device on its current commit, pinging Telegram) if there are uncommitted
  changes or unpushed local commits. This removes the *data-loss* risk. The *supply-chain*
  risk (a stolen GitHub token → code on every device, now within ≤15 min) is unchanged;
  mitigations outside this repo: 2FA on the GitHub account, branch protection on `main`, and
  optionally signed commits + `git verify-commit` in the script.

See [[bridge]] · [[device-agent]].
