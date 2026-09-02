---
title: Ideas y pendientes
tags: [idea, ops]
status: abierto
updated: 2026-09-01
summary: Cosas detectadas que aún no son PR — cron, refactor de ollama, seguridad del agente.
---

# Ideas y pendientes

## Después de mergear PRs

- **Unificar Ollama:** que `bridge/server.py` use `bridge/ollama_fallback.py` en vez de su
  copia. Hacer tras [[pr-1-ollama-fallback]] + [[pr-5-telegram-ollama-jobs]]. Ver [[ollama-fallback]].
- **Escalonar el cron:** varios jobs a las `0 8` y cerca de las 7 chocan → separar 2-3 min.
  Toca `bin/install-pi`, que también cambia [[pr-2-mercado-cadencia]]. Ver [[cron]].

## Bugs / mejoras sin PR

- `bridge/telegram_bot.py`: el bucle se bloquea hasta 120 s por mensaje; no procesa otros
  mientras. No entiende notas de voz entrantes.
- **Race de sesión al 100 %:** el lock ([[sesion-claude]]) serializa, pero si un proceso
  muere con el lock tomado hay que soltarlo (flock lo suelta al cerrar el fd; verificar en la Pi).
- `agents/device_agent.py`: `shell=True` por HTTP; aceptable tras Tailscale pero convendría
  una allowlist de comandos. Ver [[device-agent]].
- HUD: si un job se abandona sin recargar, `_hudCore` puede quedarse en `thinking`. Ver [[orbe]].

## Wiki

- Enganchar `bin/wiki-graph --check` a un pre-commit. Ver [[wiki-como-funciona]].
