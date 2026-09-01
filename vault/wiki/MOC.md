---
title: Jarvis — Mapa
tags: [meta]
status: vivo
updated: 2026-09-01
summary: Punto de entrada del wiki. Empieza aquí; el índice de abajo se regenera solo.
---

# Jarvis — Mapa de contenido

Wiki del proyecto **[SergioCc13/jarvis](https://github.com/SergioCc13/jarvis)**: asistente
de voz sobre Claude Code + voicemode, con HUD, puente de voz por Telegram/teléfono y
agentes en cada dispositivo, todo sobre Tailscale y corriendo en una Raspberry Pi.

## Cómo usar este wiki

- **Una nota = un concepto**, corta, con enlaces `[[así]]`. Obsidian dibuja el grafo solo.
- **Frontmatter obligatorio**: `title`, `tags` (el primero agrupa), `status`, `updated`, `summary`.
- `bin/wiki-graph` regenera `_graph.json` + `_graph.md` y el índice de abajo. No edites
  el bloque entre los marcadores.
- Notas personales / borrador → `vault/wiki/private/` (no se sube).
- Detalle del propio sistema en [[wiki-como-funciona]].

## Para Claude

Lee **esta nota** para el mapa, o **`vault/wiki/_graph.json`** para la versión estructurada
(nodos + aristas en una sola lectura). Cada nota enlaza a su código y a sus PRs.

## Índice

<!-- AUTO:INDEX -->
_Regenerado por `bin/wiki-graph` — no editar este bloque._

### decision

- [[coste-tokens|Coste de tokens]] — Prioridad del proyecto — minimizar consumo de cuota; preferir stdlib a llamadas LLM.  ·  `vivo`

### idea

- [[ideas-pendientes|Ideas y pendientes]] — Cosas detectadas que aún no son PR — cron, refactor de ollama, seguridad del agente.  ·  `abierto`

### meta

- [[wiki-como-funciona|Cómo funciona este wiki]] — Convenciones del wiki y qué hace bin/wiki-graph (grafo + índice + chequeos).  ·  `vivo`
- [[moc|Jarvis — Mapa]] — Punto de entrada del wiki. Empieza aquí; el índice de abajo se regenera solo.  ·  `vivo`

### pr

- [[pr-1-ollama-fallback|"PR #1 — fix ollama-fallback"]] — El fallback a Ollama de server.py anunciaba el cambio pero nunca respondía.  ·  `abierto`
- [[pr-2-mercado-cadencia|"PR #2 — mercado: semanal + diario"]] — Multi-agente solo los lunes, rápido a diario; + fechas reales y gráfico de puntuaciones.  ·  `abierto`
- [[pr-3-orbe-vivo|"PR #3 — orbe vivo"]] — El orbe del HUD no reaccionaba al pensar ni al hablar; añade estado thinking + hudCore().  ·  `abierto`
- [[pr-4-bugs-varios|"PR #4 — bugs varios"]] — Recordatorios duplicados, Telegram >4096, watchdog frágil, timeouts sin capturar.  ·  `abierto`
- [[pr-5-telegram-ollama-jobs|"PR #5 — Telegram→Ollama + jobs"]] — Telegram cae a Ollama sin tokens; el bridge guarda los últimos 8 jobs en vez de 1.  ·  `abierto`
- [[pr-6-hardening|"PR #6 — endurecimiento"]] — Lock de sesión Claude, agente de dispositivo más cerrado, vault-refresh sin gasto extra.  ·  `abierto`

### subsistema

- [[device-agent|Agente de dispositivo]] — agents/device_agent.py — HTTP :8793 en cada equipo; ejecuta acciones (shell, apps, volumen…).  ·  `activo`
- [[mercado|Análisis de mercado]] — bin/analiza — informe completo multi-agente los lunes, rápido (1 llamada) a diario.  ·  `activo`
- [[telegram|Bot de Telegram]] — bridge/telegram_bot.py — long-poll; cada mensaje va a claude -p, responde por voz o texto.  ·  `activo`
- [[bridge|Bridge]] — Servidor HTTP hub en el puerto 8792 — voz, chat, registro de dispositivos y SSE.  ·  `activo`
- [[cron|Cron de la Pi]] — Qué corre y cuándo en la Raspberry Pi; lo instala bin/install-pi.  ·  `activo`
- [[ollama-fallback|Fallback a Ollama]] — LLM local cuando claude no responde — recorre backends, verifica modelo, timeout largo.  ·  `activo`
- [[hud|HUD]] — Dashboard web (hud/*.html) servido estático — orbe, chat, voz, estado, SSE.  ·  `activo`
- [[notificaciones|Notificaciones]] — bridge/notify.py — Discord / Telegram / email desde un solo dispatch().  ·  `activo`
- [[orbe|Orbe de cristal]] — La bola del HUD — canvas con ruido; estados idle/listening/thinking/speaking.  ·  `activo`
- [[seguimiento|Seguimiento de watchlist]] — agents/seguimiento.py — indicadores + SQLite; LLM solo si un ticker dispara señal.  ·  `activo`
- [[sesion-claude|Sesión de Claude compartida]] — bridge y telegram comparten un claude -p --resume <session_id>; session_lock.py lo serializa.  ·  `activo`
- [[vault-refresh|vault-refresh]] — bin/vault-refresh regenera vault/outputs/*.md con skills de voz antes del brief.  ·  `activo`
- [[watchdog|Watchdog y recordatorios]] — bin/watchdog vigila servicios; bin/check-reminders avisa de recordatorios próximos.  ·  `activo`

<!-- /AUTO:INDEX -->
