---
title: Orbe de cristal
tags: [subsistema, frontend]
status: activo
updated: 2026-09-01
summary: La bola del HUD — canvas con ruido; estados idle/listening/thinking/speaking.
---

# Orbe de cristal — `hud/index.html` (`initCore`)

Blob orgánico dibujado en `<canvas>` con ruido Perlin; `requestAnimationFrame` continuo.
`CORE_STATES` define amplitud, velocidad de superficie, respiración y glow por estado.

## Estados

| Estado | Sensación |
|---|---|
| `idle` | calma, deriva lenta |
| `listening` | reactivo, glow alto |
| `thinking` | superficie hirviendo rápido, pulso de tamaño, bultos girando (**nuevo**) |
| `speaking` | ondas en el borde + parpadeo de brillo, atado a la reproducción de audio |

## El bug que arregla [[pr-3-orbe-vivo]]

El orbe **solo** lo movía `renderAudio()` (lee logs de voicemode). El chat de texto y el
micro del HUD nunca lo tocaban, y `renderAudio` lo forzaba a `idle` cada 1,5 s. Resultado:
congelado en reposo casi siempre.

Arreglo: estado `thinking` nuevo + `hudCore(state)` — mientras el chat/voz del HUD está
activo, es dueño del orbe y `renderAudio` cede. `_setChatState` y `_sendVoice` lo conducen.

## Relacionado

[[hud]] · [[pr-3-orbe-vivo]]
