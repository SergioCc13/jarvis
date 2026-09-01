---
title: "PR #3 — orbe vivo"
tags: [pr, frontend]
status: abierto
updated: 2026-09-01
summary: El orbe del HUD no reaccionaba al pensar ni al hablar; añade estado thinking + hudCore().
---

# PR #3 — `feat/orbe-vivo-pensando-hablando`

**Problema:** el [[orbe]] estaba siempre igual. Lo movía solo `renderAudio()` (logs de
voicemode); el chat de texto y el micro del HUD nunca lo tocaban, y `renderAudio` lo forzaba
a `idle` cada 1,5 s.

**Fix (todo en `hud/index.html`):**
- Estado `thinking` nuevo (superficie hirviendo, pulso, bultos girando) + halo CSS.
- `hudCore(state)`: mientras el chat/voz del HUD está activo, es dueño del orbe.
- `_setChatState` y `_sendVoice` conducen el orbe; `speaking` atado a la reproducción real.

Ver [[orbe]] · [[hud]].
