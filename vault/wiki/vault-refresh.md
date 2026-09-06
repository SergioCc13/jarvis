---
title: vault-refresh
tags: [subsystem, ops]
status: active
updated: 2026-09-01
summary: bin/vault-refresh regenerates vault/outputs/*.md with the voice skills before the brief.
---

# vault-refresh — `bin/vault-refresh`

Before `morning-brief`, it runs Jarvis's voice skills (`plan`, `habitos`,
`recordatorios`, `inbox`) to keep `vault/outputs/*.md` fresh, which is what the
[[hud]] shows.

Each skill is one `claude -p` call.

## Fix from [[pr-6-hardening]]

**Skips** the skill whose `vault/outputs/<skill>.md` is already from today → 0-4 fewer calls if
the cron runs again. `--force` regenerates everything. (`date -r` works on both macOS and GNU.)

## Related

[[cron]] · [[coste-tokens]] · [[wiki-como-funciona]]
