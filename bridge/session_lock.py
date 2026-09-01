#!/usr/bin/env python3
"""One writer at a time for the shared `claude -p --resume <session>` call.

bridge/server.py (HUD chat + voice) and bridge/telegram_bot.py both drive the
SAME Claude session id. Two `claude --resume` processes writing that session
concurrently can corrupt it or fail with lock errors. This is an advisory
file lock (fcntl) they both take around the subprocess call.

    from session_lock import claude_session_lock
    with claude_session_lock():
        result = subprocess.run(["claude", "-p", ...], ...)

POSIX only (Pi + Mac). If fcntl is unavailable the lock is a no-op.
"""
import contextlib
import os
import time

_LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude-session.lock")

try:
    import fcntl
except ImportError:  # pragma: no cover  (non-POSIX)
    fcntl = None


@contextlib.contextmanager
def claude_session_lock(timeout=180, poll=0.5):
    """Block until the Claude session is free, then hold it for the `with` body.

    Raises TimeoutError if it can't be acquired within `timeout` seconds — the
    caller should fall back (e.g. to Ollama) rather than run unsynchronised.
    """
    if fcntl is None:
        yield
        return
    f = open(_LOCK_PATH, "w")
    try:
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(
                        "otra petición está usando la sesión de Claude "
                        f"(esperé {timeout}s)"
                    )
                time.sleep(poll)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()
