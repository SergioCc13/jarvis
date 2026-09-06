---
title: Ideas and to-dos
tags: [idea, ops]
status: open
updated: 2026-09-01
summary: Things spotted that aren't PRs yet — cron, ollama refactor, agent security.
---

# Ideas and to-dos

## After merging the PRs

- **Unify Ollama:** have `bridge/server.py` use `bridge/ollama_fallback.py` instead of its own
  copy. Do this after [[pr-1-ollama-fallback]] + [[pr-5-telegram-ollama-jobs]]. See [[ollama-fallback]].
- **Stagger the cron:** several jobs at `0 8` and near 7 collide → space them 2-3 min apart.
  Touches `bin/install-pi`, which [[pr-2-mercado-cadencia]] also changes. See [[cron]].

## Bugs / improvements without a PR

- `bridge/telegram_bot.py`: the loop blocks for up to 120 s per message; it processes no
  others meanwhile. It doesn't understand incoming voice notes.
- **Session race at 100%:** the lock ([[sesion-claude]]) serializes, but if a process dies
  holding the lock it has to be released (flock releases it when the fd closes; verify on the Pi).
- `agents/device_agent.py`: `shell=True` over HTTP; acceptable behind Tailscale but a command
  allowlist would be better. See [[device-agent]].
- HUD: if a job is abandoned without a reload, `_hudCore` can stay stuck in `thinking`. See [[orbe]].

## Wiki

- Hook `bin/wiki-graph --check` into a pre-commit. See [[wiki-como-funciona]].
