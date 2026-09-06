#!/bin/bash
# Wrapper so launchd/systemd can start the device agent without embedding
# secrets in the unit file — agents/.env (gitignored) supplies them at
# runtime, this script just sources it and execs the agent.
set -e
cd "$(dirname "$0")/.."
# launchd/systemd start us with a minimal PATH that omits Homebrew — without
# this, device_agent.py can't find `tailscale` to resolve its own IP and
# silently falls back to binding 0.0.0.0 and registering IP "unknown".
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# Unbuffered stdout/stderr so /tmp/jarvis-agent.log reflects reality in real
# time — block-buffered output is why the log once looked "2 days stale" while
# the agent was actually crash-looping.
export PYTHONUNBUFFERED=1
source agents/.env
exec python3 agents/device_agent.py
