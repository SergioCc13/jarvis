---
title: HUD
tags: [subsistema, frontend]
status: activo
updated: 2026-09-01
summary: Dashboard web (hud/*.html) servido estático — orbe, chat, voz, estado, SSE.
---

# HUD — `hud/`

Páginas estáticas que sirve el [[bridge]] (o Tailscale). El token se inyecta por dispositivo
en `hud/jarvis-config.js` (gitignored).

| Fichero | Qué es |
|---|---|
| `index.html` | dashboard principal: [[orbe]], chat, botón de voz, tira de estado, calendario, skills |
| `voice.html` | página de voz a pantalla completa (orbe propio, ya bien cableado) |
| `chat.html` | chat a secas |

## Flujo de chat

`sendChat` → `POST /chat` → `job_id` → `_pollChatJob` cada 2 s sobre `/chat/result`.
Sobrevive a recargar / bloquear el móvil. El estado (`listening` / `thinking` / `idle`)
se refleja en el panel de chat **y** en el [[orbe]] vía `hudCore()`.

## Voz en el HUD

`startVoice` graba con VAD (auto-stop tras silencio), `_sendVoice` → `POST /voice`,
reproduce el mp3 de vuelta. El orbe pasa a `speaking` mientras suena.

## Eventos en vivo

`EventSource('/events')` → avisos del bridge (p. ej. "usando Ollama") aparecen como notice.

## Relacionado

[[orbe]] · [[bridge]] · [[pr-3-orbe-vivo]]
