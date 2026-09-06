---
title: "PR #3 — living orb"
tags: [pr, frontend]
status: open
updated: 2026-09-01
summary: The HUD orb didn't react while thinking or speaking; adds a thinking state + hudCore().
---

# PR #3 — `feat/orbe-vivo-pensando-hablando`

**Problem:** the [[orbe]] always looked the same. Only `renderAudio()` moved it (voicemode logs);
the HUD's text chat and mic never touched it, and `renderAudio` forced it back to `idle` every 1.5 s.

**Fix (all in `hud/index.html`):**
- New `thinking` state (boiling surface, pulse, orbiting blobs) + a CSS halo.
- `hudCore(state)`: while the HUD chat/voice is active, it owns the orb.
- `_setChatState` and `_sendVoice` drive the orb; `speaking` is tied to actual playback.

See [[orbe]] · [[hud]].
