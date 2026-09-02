---
title: Grafo (generado)
tags: [meta]
summary: Índice completo del wiki, regenerado por bin/wiki-graph. No editar a mano.
---

# Grafo del wiki — 23 notas
_Generado por `bin/wiki-graph` a partir del frontmatter y los `[[enlaces]]`. **No editar a mano.**_

### decision

- [[coste-tokens|Coste de tokens]] — Prioridad del proyecto — minimizar consumo de cuota; preferir stdlib a llamadas LLM.  ·  `vivo`
  ↳ [[mercado]] [[pr-2-mercado-cadencia]] [[vault-refresh]] [[pr-6-hardening]] [[seguimiento]] [[ollama-fallback]]

### idea

- [[ideas-pendientes|Ideas y pendientes]] — Cosas detectadas que aún no son PR — cron, refactor de ollama, seguridad del agente.  ·  `abierto`
  ↳ [[pr-1-ollama-fallback]] [[pr-5-telegram-ollama-jobs]] [[ollama-fallback]] [[pr-2-mercado-cadencia]] [[cron]] [[sesion-claude]] [[device-agent]] [[orbe]] [[wiki-como-funciona]]

### meta

- [[wiki-como-funciona|Cómo funciona este wiki]] — Convenciones del wiki y qué hace bin/wiki-graph (grafo + índice + chequeos).  ·  `vivo`
  ↳ [[moc]] [[cron]] [[coste-tokens]]
- [[moc|Jarvis — Mapa]] — Punto de entrada del wiki. Empieza aquí; el índice de abajo se regenera solo.  ·  `vivo`
  ↳ [[wiki-como-funciona]] [[coste-tokens]] [[ideas-pendientes]] [[moc]] [[pr-1-ollama-fallback]] [[pr-2-mercado-cadencia]] [[pr-3-orbe-vivo]] [[pr-4-bugs-varios]] [[pr-5-telegram-ollama-jobs]] [[pr-6-hardening]] [[device-agent]] [[mercado]] [[telegram]] [[bridge]] [[cron]] [[ollama-fallback]] [[hud]] [[notificaciones]] [[orbe]] [[seguimiento]] [[sesion-claude]] [[vault-refresh]] [[watchdog]]

### pr

- [[pr-1-ollama-fallback|"PR #1 — fix ollama-fallback"]] — El fallback a Ollama de server.py anunciaba el cambio pero nunca respondía.  ·  `abierto`
  ↳ [[ollama-fallback]] [[bridge]]
- [[pr-2-mercado-cadencia|"PR #2 — mercado: semanal + diario"]] — Multi-agente solo los lunes, rápido a diario; + fechas reales y gráfico de puntuaciones.  ·  `abierto`
  ↳ [[cron]] [[mercado]] [[seguimiento]] [[coste-tokens]]
- [[pr-3-orbe-vivo|"PR #3 — orbe vivo"]] — El orbe del HUD no reaccionaba al pensar ni al hablar; añade estado thinking + hudCore().  ·  `abierto`
  ↳ [[orbe]] [[hud]]
- [[pr-4-bugs-varios|"PR #4 — bugs varios"]] — Recordatorios duplicados, Telegram >4096, watchdog frágil, timeouts sin capturar.  ·  `abierto`
  ↳ [[watchdog]] [[notificaciones]] [[seguimiento]]
- [[pr-5-telegram-ollama-jobs|"PR #5 — Telegram→Ollama + jobs"]] — Telegram cae a Ollama sin tokens; el bridge guarda los últimos 8 jobs en vez de 1.  ·  `abierto`
  ↳ [[pr-1-ollama-fallback]] [[ideas-pendientes]] [[telegram]] [[ollama-fallback]] [[bridge]]
- [[pr-6-hardening|"PR #6 — endurecimiento"]] — Lock de sesión Claude, agente de dispositivo más cerrado, vault-refresh sin gasto extra.  ·  `abierto`
  ↳ [[bridge]] [[telegram]] [[sesion-claude]] [[device-agent]] [[vault-refresh]]

### subsistema

- [[device-agent|Agente de dispositivo]] — agents/device_agent.py — HTTP :8793 en cada equipo; ejecuta acciones (shell, apps, volumen…).  ·  `activo`
  ↳ [[bridge]] [[pr-6-hardening]]
- [[mercado|Análisis de mercado]] — bin/analiza — informe completo multi-agente los lunes, rápido (1 llamada) a diario.  ·  `activo`
  ↳ [[seguimiento]] [[pr-2-mercado-cadencia]] [[coste-tokens]] [[cron]]
- [[telegram|Bot de Telegram]] — bridge/telegram_bot.py — long-poll; cada mensaje va a claude -p, responde por voz o texto.  ·  `activo`
  ↳ [[bridge]] [[sesion-claude]] [[pr-5-telegram-ollama-jobs]] [[ollama-fallback]] [[notificaciones]]
- [[bridge|Bridge]] — Servidor HTTP hub en el puerto 8792 — voz, chat, registro de dispositivos y SSE.  ·  `activo`
  ↳ [[sesion-claude]] [[hud]] [[device-agent]] [[pr-5-telegram-ollama-jobs]] [[ollama-fallback]] [[telegram]] [[notificaciones]]
- [[cron|Cron de la Pi]] — Qué corre y cuándo en la Raspberry Pi; lo instala bin/install-pi.  ·  `activo`
  ↳ [[watchdog]] [[vault-refresh]] [[seguimiento]] [[mercado]] [[pr-2-mercado-cadencia]] [[ideas-pendientes]]
- [[ollama-fallback|Fallback a Ollama]] — LLM local cuando claude no responde — recorre backends, verifica modelo, timeout largo.  ·  `activo`
  ↳ [[pr-1-ollama-fallback]] [[pr-5-telegram-ollama-jobs]] [[telegram]] [[ideas-pendientes]] [[bridge]] [[coste-tokens]]
- [[hud|HUD]] — Dashboard web (hud/*.html) servido estático — orbe, chat, voz, estado, SSE.  ·  `activo`
  ↳ [[bridge]] [[orbe]] [[pr-3-orbe-vivo]]
- [[notificaciones|Notificaciones]] — bridge/notify.py — Discord / Telegram / email desde un solo dispatch().  ·  `activo`
  ↳ [[watchdog]] [[seguimiento]] [[mercado]] [[pr-4-bugs-varios]] [[pr-2-mercado-cadencia]] [[telegram]] [[cron]]
- [[orbe|Orbe de cristal]] — La bola del HUD — canvas con ruido; estados idle/listening/thinking/speaking.  ·  `activo`
  ↳ [[pr-3-orbe-vivo]] [[hud]]
- [[seguimiento|Seguimiento de watchlist]] — agents/seguimiento.py — indicadores + SQLite; LLM solo si un ticker dispara señal.  ·  `activo`
  ↳ [[mercado]] [[coste-tokens]] [[cron]]
- [[sesion-claude|Sesión de Claude compartida]] — bridge y telegram comparten un claude -p --resume <session_id>; session_lock.py lo serializa.  ·  `activo`
  ↳ [[bridge]] [[telegram]] [[pr-6-hardening]]
- [[vault-refresh|vault-refresh]] — bin/vault-refresh regenera vault/outputs/*.md con skills de voz antes del brief.  ·  `activo`
  ↳ [[hud]] [[pr-6-hardening]] [[cron]] [[coste-tokens]] [[wiki-como-funciona]]
- [[watchdog|Watchdog y recordatorios]] — bin/watchdog vigila servicios; bin/check-reminders avisa de recordatorios próximos.  ·  `activo`
  ↳ [[notificaciones]] [[pr-4-bugs-varios]] [[cron]]
