#!/bin/bash
# Wrapper so launchd/systemd can start the device agent without embedding
# secrets in the unit file — agents/.env (gitignored) supplies them at
# runtime, this script just sources it and execs the agent.
set -e
cd "$(dirname "$0")/.."
source agents/.env
exec python3 agents/device_agent.py
