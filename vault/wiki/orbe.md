---
title: Glass orb
tags: [subsystem, frontend]
status: active
updated: 2026-09-01
summary: The HUD's ball — a noise canvas; idle/listening/thinking/speaking states.
---

# Glass orb — `hud/index.html` (`initCore`)

An organic blob drawn on a `<canvas>` with Perlin noise; continuous `requestAnimationFrame`.
`CORE_STATES` defines amplitude, surface speed, breathing and glow per state.

## States

| State | Feel |
|---|---|
| `idle` | calm, slow drift |
| `listening` | reactive, high glow |
| `thinking` | fast-boiling surface, size pulse, orbiting blobs (**new**) |
| `speaking` | edge ripples + brightness flicker, tied to audio playback |

## The bug [[pr-3-orbe-vivo]] fixes

The orb was moved **only** by `renderAudio()` (which reads voicemode logs). The text chat and
the HUD mic never touched it, and `renderAudio` forced it back to `idle` every 1.5 s. Result:
frozen at rest almost all the time.

Fix: a new `thinking` state + `hudCore(state)` — while the HUD chat/voice is active it owns the
orb and `renderAudio` yields. `_setChatState` and `_sendVoice` drive it.

## Related

[[hud]] · [[pr-3-orbe-vivo]]
