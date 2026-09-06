---
title: Shared Claude session
tags: [subsystem, llm]
status: active
updated: 2026-09-01
summary: bridge and telegram share one claude -p --resume <session_id>; session_lock.py serializes it.
---

# Shared Claude session

`bridge/config.json` stores a `session_id`. Both [[bridge]] (`ask_claude`) and [[telegram]]
run `claude -p --resume <that id>` so the conversation is continuous across channels.

## The problem

Two `claude --resume` on the same session **at once** can corrupt it or fail with lock errors.

## `bridge/session_lock.py` ([[pr-6-hardening]])

An `fcntl` file lock (`.claude-session.lock`). Both processes take it around the
`subprocess.run`. If they can't get it within 180 s → `TimeoutError`, and the caller replies
"busy" instead of running unsynchronized. No-op on non-POSIX.

```python
from session_lock import claude_session_lock
with claude_session_lock():
    subprocess.run(["claude", "-p", ...])
```

## Related

[[bridge]] · [[telegram]] · [[pr-6-hardening]]
