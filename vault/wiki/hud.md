---
title: HUD
tags: [subsystem, frontend]
status: active
updated: 2026-09-01
summary: Web dashboard (hud/*.html) served statically — orb, chat, voice, status, SSE.
---

# HUD — `hud/`

Static pages served by the [[bridge]] (or Tailscale). The token is injected per device into
`hud/jarvis-config.js` (gitignored).

| File | What it is |
|---|---|
| `index.html` | main dashboard: [[orbe]], chat, voice button, status strip, calendar, skills |
| `voice.html` | full-screen voice page (its own orb, already well wired) |
| `chat.html` | plain chat |

## Chat flow

`sendChat` → `POST /chat` → `job_id` → `_pollChatJob` every 2 s against `/chat/result`.
Survives a reload / the phone locking. The state (`listening` / `thinking` / `idle`) is
reflected in the chat panel **and** in the [[orbe]] via `hudCore()`.

## Voice in the HUD

`startVoice` records with VAD (auto-stops after silence), `_sendVoice` → `POST /voice`,
plays the mp3 back. The orb goes to `speaking` while it plays.

## Live events

`EventSource('/events')` → bridge notices (e.g. "using Ollama") show up as a notice.

## Related

[[orbe]] · [[bridge]] · [[pr-3-orbe-vivo]]
