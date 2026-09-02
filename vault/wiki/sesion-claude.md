---
title: Sesión de Claude compartida
tags: [subsistema, llm]
status: activo
updated: 2026-09-01
summary: bridge y telegram comparten un claude -p --resume <session_id>; session_lock.py lo serializa.
---

# Sesión de Claude compartida

`bridge/config.json` guarda un `session_id`. Tanto [[bridge]] (`ask_claude`) como [[telegram]]
hacen `claude -p --resume <ese id>` para que la conversación sea continua entre canales.

## El problema

Dos `claude --resume` sobre la misma sesión **a la vez** pueden corromperla o fallar con
errores de lock.

## `bridge/session_lock.py` ([[pr-6-hardening]])

Lock de fichero `fcntl` (`.claude-session.lock`). Ambos procesos lo toman alrededor del
`subprocess.run`. Si no lo consiguen en 180 s → `TimeoutError` y el llamador responde
"ocupado" en vez de correr sin sincronizar. No-op en no-POSIX.

```python
from session_lock import claude_session_lock
with claude_session_lock():
    subprocess.run(["claude", "-p", ...])
```

## Relacionado

[[bridge]] · [[telegram]] · [[pr-6-hardening]]
