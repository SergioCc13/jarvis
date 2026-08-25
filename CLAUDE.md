# Jarvis

Voice assistant built on Claude Code + the [voicemode MCP](https://github.com/mbailey/voicemode) (local Whisper STT + Kokoro TTS), with a HUD dashboard and optional phone access over Tailscale.

## "jarvis on" trigger

When the user says or types "jarvis on", start a voice conversation session: greet them (e.g. "Jarvis online, how can I help?" — adjust language/wording as configured below) and converse via `mcp__voicemode__converse`, checking for relevant skills before acting on spoken requests per the tool's `voice_skills_instructions`.

## Layout

- `hud/index.html` — dashboard (served via `python3 -m http.server 8791` from the repo root, viewed at `http://localhost:8791/hud/`). Reads `vault/outputs/*.md` for its panels and `hud/voicemode-logs` (a symlink you create locally, see below) for the audio/activity strip.
- `hud/voice.html` — phone voice UI (mic button styled as the same animated orb as the HUD), talks to `bridge/server.py`.
- `hud/chat.html` — phone text chat UI (no microphone), also talks to `bridge/server.py`, sharing the same persistent phone session as voice.
- `bridge/server.py` — HTTP bridge so a phone (or any browser) can talk to Jarvis by voice or text: phone audio → Whisper STT → `claude -p --resume` (its own persistent session, separate from your interactive terminal session) → Kokoro TTS → audio back (`/voice`); or phone text straight to the same `claude -p --resume` call, skipping STT/TTS (`/chat`). See the bridge's own security notes below before exposing it.
- `bin/jarvis` — one-command launcher: starts whisper/kokoro, the HUD server, the bridge, and opens a `jarvis on` session.
- `vault/` — where the (optional) Spanish-language skills (`plan`, `inbox`, `habitos`, `recordatorios`, `vault`) write their output. Not required to use Jarvis — the HUD just shows empty panels without them.

## Language

Defaults to Spanish (`VOICEMODE_WHISPER_LANGUAGE=es` in `~/.voicemode/voicemode.env`, Spanish greeting/UI text). To run it in another language, change that env var and the greeting text mentioned above, and re-point `JARVIS_TTS_VOICE` (see `bridge/server.py`) at a Kokoro voice for your language.

## Multi-device control

Jarvis can control any registered device (Mac, PC, etc.) over Tailscale. Each device runs `agents/device_agent.py` which exposes a local HTTP server (default port 8793). On startup each agent registers itself with this Pi hub via `POST /register` — the hub stores the registry in `bridge/devices.json`.

### Checking available devices

```bash
cat bridge/devices.json
# or via HTTP:
curl "http://localhost:8792/devices?token=<bridge-token>"
```

### Dispatching a command to a device

Use bash + curl to reach any device agent directly. The device URL and token are in `bridge/devices.json`.

```bash
# Open an app on the Mac
curl -s -X POST "http://<device-tailscale-ip>:8793/execute?token=<device-token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"open_app","params":{"app":"Spotify"}}'

# Set volume
curl -s -X POST "http://<ip>:8793/execute?token=<token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"volume","params":{"level":40}}'

# Send a notification
curl -s -X POST "http://<ip>:8793/execute?token=<token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"notify","params":{"title":"Jarvis","message":"Hola desde el Pi"}}'

# Run any shell command
curl -s -X POST "http://<ip>:8793/execute?token=<token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"shell","params":{"cmd":"ls ~/Desktop"}}'

# Get device status (battery, running apps, etc.)
curl -s "http://<ip>:8793/status?token=<token>"
```

### Supported actions

| Action | Params | Platforms |
|---|---|---|
| `open_app` | `app` (app name) | mac, linux |
| `open_url` | `url` | all |
| `volume` | `level` (0-100) | mac |
| `mute` | `muted` (true/false) | mac |
| `notify` | `title`, `message` | mac |
| `screenshot` | `path` (optional) | mac |
| `sleep` | — | mac, linux |
| `get_status` | — | all |
| `shell` | `cmd` | all |

### Starting an agent on a device

```bash
# On the Mac / PC — copy the example env file, fill in the Pi IP and bridge token, then:
cp agents/env.example agents/.env
# edit agents/.env: set JARVIS_HUB_URL and JARVIS_HUB_TOKEN
source agents/.env && python3 agents/device_agent.py
```

`JARVIS_HUB_TOKEN` must match the `"token"` field in `bridge/config.json` on the Pi — the hub requires it to authenticate device registrations. The agent stores its own token in `agents/config.json` (gitignored).

Add it to a launchd plist (Mac) or systemd service (Linux) for auto-start on boot.

## Notifications & Morning Brief

`bridge/notify.py` is the single module for sending Jarvis notifications. It supports three channels — all configured via environment variables in `bridge/.env` (copy `bridge/.env.example`).

### Channels

| Channel | Env vars needed | What it sends |
|---|---|---|
| Discord | `JARVIS_DISCORD_WEBHOOK` | Text message via webhook |
| Telegram | `JARVIS_TELEGRAM_TOKEN` + `JARVIS_TELEGRAM_CHAT_ID` | Text, or MP3 voice note if Kokoro is running |
| Phone call | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_PHONE_FROM` + `TWILIO_PHONE_TO` | Outbound call with TTS voice (Spanish, Lucía voice) |

### Sending a notification

```bash
# Send to all configured channels
python3 bridge/notify.py "Texto del mensaje"

# Send only to specific channels
python3 bridge/notify.py --channels discord,telegram "Mensaje"
python3 bridge/notify.py --channels call "Jarvis llamando"

# Skip voice synthesis (text-only Telegram)
python3 bridge/notify.py --no-voice "Texto plano"
```

Or from Python:
```python
from bridge.notify import dispatch
dispatch("Buenos días, Sergio. Tu agenda de hoy...")
```

### Morning Brief (cron diario)

`bin/morning-brief` asks Claude to generate a 180-word summary (plan, reminders, habits) and distributes it to all configured channels. The brief is also saved to `vault/outputs/brief.md` and shown in the HUD center panel.

Install on the Pi:
```bash
# Open crontab
crontab -e

# Add line (8:00 AM every day):
0 8 * * * cd /home/pi/jarvis && bin/morning-brief >> /tmp/jarvis-brief.log 2>&1
```

Test it manually:
```bash
cd /home/pi/jarvis && bash bin/morning-brief
```

### Getting a Twilio number (for phone calls)

1. Sign up at [twilio.com](https://www.twilio.com) — free trial includes $15 credit
2. Buy a phone number (≈$1/mo) or use the free trial number
3. Copy Account SID, Auth Token from the Console dashboard
4. Fill in `bridge/.env`

### Getting a Telegram bot

1. Chat with [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the bot token into `JARVIS_TELEGRAM_TOKEN`
3. Get your chat ID: send any message to the bot, then:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   ```
   Copy the `chat.id` value into `JARVIS_TELEGRAM_CHAT_ID`

### Telegram bidirectional bot

`bridge/telegram_bot.py` runs on the Pi and enables two-way conversation: write to the bot → Jarvis (Claude) replies, as voice note if Kokoro is running or plain text if not.

```bash
# Test manually on the Pi:
source bridge/.env && python3 bridge/telegram_bot.py

# Install as systemd service (auto-start, auto-restart):
sudo cp bridge/jarvis-telegram.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-telegram

# Logs:
journalctl -u jarvis-telegram -f
```

Add `JARVIS_TG_VOICE=0` to `bridge/.env` to force text-only replies (skip Kokoro).

## Phone bridge security

`bridge/server.py` inherits whatever Bash permissions are pre-approved in this project's `.claude/settings.local.json`. If you've approved broad rules there (e.g. `Bash(python3 *)`), anyone who obtains the bridge token can get Claude to run those commands with **no confirmation prompt**, since the bridge runs Claude headless (`-p`) and there's no one to approve/deny. Review that file before exposing the bridge beyond your own devices. `hud/voice.html` adds a client-side WebAuthn biometric gate (Face ID / fingerprint) as a UX-level protection against a lost/unlocked phone — it does **not** cryptographically verify anything server-side (no signature check), so it doesn't protect against someone who already has the token and calls the API directly.
