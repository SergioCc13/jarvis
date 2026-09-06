# Jarvis

Voice assistant built on Claude Code + the [voicemode MCP](https://github.com/mbailey/voicemode) (local Whisper STT + Kokoro TTS), with a HUD dashboard and optional phone access over Tailscale.

## Project knowledge graph

For orientation on how the parts fit together, the design decisions, and open work, read
**`vault/wiki/MOC.md`** (the map) or **`vault/wiki/_graph.json`** (nodes + edges in one read).
It's an Obsidian-style linked wiki; `bin/wiki-graph` regenerates `_graph.*` and the MOC index
from each note's frontmatter + `[[links]]`. Update the relevant note when you change a subsystem.

## "jarvis on" trigger

When the user says or types "jarvis on", start a voice conversation session: greet them (e.g. "Jarvis online, how can I help?" — adjust language/wording as configured below) and converse via `mcp__voicemode__converse`, checking for relevant skills before acting on spoken requests per the tool's `voice_skills_instructions`.

## Layout

- `hud/index.html` — the single page. On this PC, served loopback-only via `bin/jarvis` (`python3 -m http.server 8791 --bind 127.0.0.1`, run *from `hud/`*, viewed at `http://127.0.0.1:8791/`) — never serve it from the repo root, that leaks `.git/` and every `.env` (bridge token, device-agent shell PIN, email password) to anyone who can reach the port; fixed 2026-09-04 after that exact thing happened live via `0.0.0.0`. Only the Pi serves the HUD over Tailscale (see the Pi's `jarvis-public/hud` symlink setup) — this PC's copy is local-only. Dashboard on a laptop; on a phone the layout collapses to the chat panel with the side panels in a drawer. Its chat panel does both text and voice against `bridge/server.py` (mic button + 2-clap trigger), so there are no separate phone pages. Reads `vault/outputs/*.md` for its panels and `hud/voicemode-logs` (a symlink you create locally, see below) for the audio/activity strip. Installs as a PWA (`hud/manifest.webmanifest` + `hud/sw.js`); on a phone it shows a client-side WebAuthn (Face ID / fingerprint) gate before unlocking.
- `bridge/server.py` — HTTP bridge so the HUD (or any browser) can talk to Jarvis by voice or text: audio → Whisper STT → `claude -p --resume` (its own persistent session, separate from your interactive terminal session) → Kokoro TTS → audio back (`/voice`); or text straight to the same `claude -p --resume` call, skipping STT/TTS (`/chat`). On startup it writes `hud/jarvis-config.js` (gitignored) with the bridge token so the HUD connects without manual entry. See the bridge's own security notes below before exposing it.
- `bin/jarvis` — one-command launcher: starts whisper/kokoro, the HUD server, the bridge, and opens a `jarvis on` session.
- `vault/` — where the (optional) Spanish-language skills (`plan`, `inbox`, `habitos`, `recordatorios`, `vault`) write their output. Not required to use Jarvis — the HUD just shows empty panels without them.

## Language

Defaults to Spanish (`VOICEMODE_WHISPER_LANGUAGE=es` in `~/.voicemode/voicemode.env`, Spanish greeting/UI text). To run it in another language, change that env var and the greeting text mentioned above, and re-point `JARVIS_TTS_VOICE` (see `bridge/server.py`) at a Kokoro voice for your language.

The product speaks Spanish to the user; this repo's code comments, docstrings and docs are in English. Spanish strings that are user-facing (greetings, Telegram/email copy) or that Jarvis must recognize as spoken input (the trigger phrases quoted below) are deliberately kept in Spanish.

## Multi-device control

Jarvis can control any registered device (Mac, PC, etc.) over Tailscale. Each device runs `agents/device_agent.py` which exposes a local HTTP server (default port 8793). On startup each agent registers itself with this Pi hub via `POST /register` — the hub stores the registry in `bridge/devices.json`.

### Checking available devices

```bash
cat bridge/devices.json
# or via HTTP:
curl -H "Authorization: Bearer <bridge-token>" "http://localhost:8792/devices"
```

### Dispatching a command to a device

Use bash + curl to reach any device agent directly. The device URL and token are in `bridge/devices.json`.
**Always send the token via header, never `?token=`** — query strings land in
`journalctl`/access logs in plain text, and this endpoint grants full shell.

```bash
# Open an app on the Mac
curl -s -X POST "http://<device-tailscale-ip>:8793/execute" \
  -H "X-Jarvis-Token: <device-token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"open_app","params":{"app":"Spotify"}}'

# Set volume
curl -s -X POST "http://<ip>:8793/execute" \
  -H "X-Jarvis-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"volume","params":{"level":40}}'

# Send a notification
curl -s -X POST "http://<ip>:8793/execute" \
  -H "X-Jarvis-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"notify","params":{"title":"Jarvis","message":"Hola desde el Pi"}}'

# Run any shell command — if that device has JARVIS_AGENT_SHELL_PIN set,
# params.pin is required too (ask the user for it, don't guess/store it).
# Wrong or missing PIN when one is configured returns ok:false, not a crash.
curl -s -X POST "http://<ip>:8793/execute" \
  -H "X-Jarvis-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"shell","params":{"cmd":"ls ~/Desktop","pin":"<shell pin, if set>"}}'

# Get device status (battery, running apps, etc.)
curl -s -H "X-Jarvis-Token: <token>" "http://<ip>:8793/status"
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
| `shell` | `cmd`, `pin` (if `JARVIS_AGENT_SHELL_PIN` is set on that device) | all |

If `shell` comes back `ok:false` with a PIN-related message, ask the user for
their PIN out loud/in chat rather than guessing — never try common PINs, and
never store the PIN anywhere outside `agents/.env`. If they forgot it:
`curl -s -H "X-Jarvis-Token: <token>" "http://<ip>:8793/pin-recover"` emails
it to them (requires `JARVIS_EMAIL_*` configured on that device).

### Controlling an iPhone (no device agent — Telegram button instead)

iOS won't run a background HTTP server like `agents/device_agent.py` (no
`shell`, `open_url`, etc. via silent remote call — Apple's sandboxing blocks
it, and the paid workaround, Pushcut, was dropped in favor of this free
approach). Instead, when the target device is the iPhone, send a Telegram
message with a one-tap button that opens the URL/app deep link:

```bash
python3 bridge/notify.py --phone-button "Abrir YouTube" "https://www.youtube.com" \
  "Toca para abrir YouTube en el móvil"
```

This needs `JARVIS_TELEGRAM_TOKEN` + `JARVIS_TELEGRAM_CHAT_ID` in `bridge/.env`
(same ones the Telegram bot already uses). One tap is unavoidable — Apple
doesn't allow a truly silent remote trigger without a paid service. Use this
whenever the user asks to open something "en mi móvil"/"en el iPhone" instead
of trying to reach it like a registered device.

### Starting an agent on a device

```bash
# On the Mac / PC — copy the example env file, fill in the Pi IP and bridge token, then:
cp agents/env.example agents/.env
# edit agents/.env: set JARVIS_HUB_URL and JARVIS_HUB_TOKEN
source agents/.env && python3 agents/device_agent.py
```

`JARVIS_HUB_TOKEN` must match the `"token"` field in `bridge/config.json` on the Pi — the hub requires it to authenticate device registrations. The agent stores its own token in `agents/config.json` (gitignored).

Add it to a launchd plist (Mac) or systemd service (Linux) for auto-start on boot.
On Mac, `agents/com.jarvis.device-agent.plist` + `agents/start-agent.sh` are
ready to use — see the install steps in the comment at the top of the plist.
`KeepAlive` also relaunches it if it crashes, not just on boot.

## Multi-agent mode

**Trigger**: the user says or types `agentes:` followed by the task.

Examples (spoken in Spanish):
- *"agentes: busca el precio de Ragavan y dime si es buen momento para vender"*
- *"agentes: revisa mi stock de Cardmarket y baja un 10% todo lo que lleve más de 30 días sin venderse"*
- *"agentes: investiga las cartas más vendidas de Lorcana esta semana"*

**How to respond**: break the task into subtasks and launch specialized agents in parallel with Claude Code's `Agent` tool. Standard roles:

| Role | What it does |
|---|---|
| **Researcher** (`Investigador`) | Finds information — uses `python3 agents/cardmarket.py`, `python3 bin/search`, `curl` |
| **Analyst** (`Analista`) | Evaluates the researcher's data and draws conclusions |
| **Executor** (`Ejecutor`) | Takes concrete actions — changes prices, sends notifications |
| **Critic** (`Crítico`) | Reviews everyone else's work and flags errors or improvements |

Not every agent is needed for every task — use only the ones the task requires. The final result is always sent via Telegram (`python3 bridge/notify.py --no-voice "result"`).

**Typical Cardmarket flow**:
1. Researcher looks up prices with `python3 agents/cardmarket.py`
2. Analyst compares against trends and decides on an action
3. Executor applies changes if the user asked for them (`set-price`)
4. Summary → Telegram

## Price & web scraper

`agents/scraper.py` fetches card prices and text from any URL. Pure stdlib, no API keys.

| Game | Source | Includes Cardmarket EUR price |
|---|---|---|
| Magic | Scryfall API (official) | ✅ yes |
| YuGiOh | ygoprodeck.com API | TCGPlayer USD |
| Pokémon | pokemontcg.io (DDG fallback) | TCGPlayer USD |

```bash
# Cards
python3 agents/scraper.py magic "Ragavan Nimble Pilferer"
python3 agents/scraper.py pokemon "Charizard"
python3 agents/scraper.py yugioh "Dark Magician"

# People
python3 agents/scraper.py persona "Elon Musk"              # multi-source search
python3 agents/scraper.py github "torvalds"                # GitHub profile (official API, no key)
python3 agents/scraper.py twitter "elonmusk"               # Twitter/X profile via Nitter

# Search
python3 agents/scraper.py google "query"                   # Google via SerpAPI (if a key is set) or DDG
python3 agents/scraper.py search "query"                   # DuckDuckGo Instant Answer
python3 agents/scraper.py url "https://any-site.com"       # clean text from any web page

# Jobs
python3 agents/scraper.py jobs "python developer"
python3 agents/scraper.py jobs "UX designer" --lugar "Barcelona"
```

- `persona`: combines DDG + GitHub API + LinkedIn/Twitter via DDG site-search + direct links
- `github`: official GitHub API, free, no key — returns bio, company, repos, followers
- `twitter`: tries to read the profile via Nitter mirrors (no login), falls back to direct links
- `google`: uses SerpAPI if `SERPAPI_KEY` is in `agents/.env` (100 searches/month free), otherwise DDG
- `jobs`: Indeed/Infojobs (scraping) + Remotive API (remote, free) + direct links

Use this scraper whenever the user asks about card prices, wants info on a person or a web page, or is looking for a job.

## Market analysis

`agents/trading.py` collects real-time market data (pure stdlib, no pip).
`bin/analiza` generates the **"Jarvis: Mercado"** email and sends it via **email + Telegram**.

**Cadence**: **full** report (multi-agent) on **Mondays**; **quick** report
(`--rapido`, a single call) the **rest of the week**. Installed by `bin/install-pi`.

| Source | Covers | Key needed |
|---|---|---|
| Yahoo Finance | Stocks (.MC/.DE/.L suffixes), ETFs, indices (^GSPC, ^GDAXI, ^VIX…), commodities (GC=F, CL=F), FX (DX-Y.NYB) | No |
| CoinGecko | Crypto (BTC, ETH, SOL, XRP, ADA, DOGE…) | No |
| agents/scraper.py | TCG cards (Cardmarket EUR price) | No |

### Multi-agent engine (full report, Mondays)

`bin/analiza` with no flags runs `agents/analistas.py`: for each asset in
`agents/watchlist.txt` it runs a role chain inspired by
[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents),
each role a `claude -p` call that sees the previous role's work:

1. **Technical / quantitative analyst** — trend, momentum, volume, 52-week range (facts only)
2. **Context & events analyst** — catalysts, next event
3. **Bull researcher** — the strongest case to buy
4. **Bear researcher** — rebuts it and builds the bearish case
5. **Trader** — weighs the debate, preliminary decision + entry/exit ranges
6. **Risk / portfolio manager** — FINAL verdict in the email's format

Then a portfolio role writes the **"Visión de cartera"** (portfolio view) that heads the report.
Each asset gets a block: Score 0-100, Recommendation
(strong/weak buy · Neutral · weak/strong sell), Horizon, target entry
and exit price, "Próximo evento relevante" (next relevant event), and Rationale.

The indicators (RSI, SMA 50/200, 52w, volume) come from `agents/seguimiento.py`.
The **"Próximo evento relevante" line is NOT invented by the LLM**: it comes from
`agents/calendar_data.py` (official Fed calendar + earnings/dividend dates from
Yahoo Finance) and is forced into the final block. The email
**attaches the scores chart** (`agents/charts.py --scores`, 0 tokens;
needs `python3-matplotlib`, installed by `bin/install-pi`).

**Cost**: ~6 calls per asset + 1. With the 21-asset watchlist ≈ 127 calls
and **~20-40 min** per run. That's why it runs **only on Mondays**. Not financial
advice: it's an analysis scaffold.

```bash
bin/analiza                       # full watchlist, multi-agent → email + Telegram
bin/analiza --only BTC ETH        # only those assets (for testing)
bin/analiza --limit 3             # only the first 3
bin/analiza --rapido [SYMBOLS]    # 1 call: 180-word summary (daily report)
python3 agents/trading.py AAPL BTC ^GSPC   # raw data only, no LLM
```

**Daily watchlist** (`agents/watchlist.txt`): one symbol per line. Lines of the
form `name tcg game` (cards) are ignored by the market engine.

**Email**: needs `JARVIS_EMAIL_PASSWORD` in `bridge/.env` (Gmail App Password).
How to get one: myaccount.google.com → Security → 2-Step Verification → App passwords → create "Jarvis".

**Voice / Telegram triggers** to recognize (spoken in Spanish):
- *"analiza AAPL"*, *"cómo va BTC hoy"* → `bin/analiza --only SYMBOL`
- *"resumen rápido del mercado"* → `bin/analiza --rapido`
- *"agentes: analiza mi cartera"* → `bin/analiza` (already multi-agent)

**Cron (Pi)** — added by `bin/install-pi`:
```
30 6 * * 1     cd /home/pi/jarvis && bin/analiza          >> /tmp/jarvis-mercado.log 2>&1  # full, Monday
0  7 * * 0,2-6 cd /home/pi/jarvis && bin/analiza --rapido >> /tmp/jarvis-mercado.log 2>&1  # quick, rest of week
```

The report is saved to `vault/outputs/mercado.md` (visible in the HUD). Telegram
gets only the portfolio view; the full report goes in the email.

### Event-filtered tracking

`agents/seguimiento.py` + `bin/seguimiento` do daily tracking of the same
`agents/watchlist.txt`, but the opposite way to `bin/analiza`: instead of
summarizing everything every day, they compute indicators (RSI 14, SMA 50/200,
52-week high/low, volume ratio), store history in SQLite
(`vault/raw/seguimiento.db`), and **only call the LLM for tickers that trip a
signal**. Quiet days: no token spend and nothing sent via Telegram (only updates
`vault/outputs/seguimiento.md`).

Signals that trigger analysis (thresholds in `TH`, overridable via env
`JARVIS_SEG_*`): daily move ≥4%, 5d ≥8%, volume ≥2x vs 20d average, RSI ≥75 or
≤25, within <2% of the 52-week high/low, 50/200 moving-average cross.

```bash
bin/seguimiento                 # sweep + LLM verdict + Telegram if there are signals
bin/seguimiento scan            # indicators table only, no LLM
bin/seguimiento scan --json     # + JSON dump
bin/seguimiento scan --notify --always   # notify even if there's nothing
bin/seguimiento score           # how the tickers flagged ≥14 days ago have moved
```

The verdict is a *tracking* one, never "buy/sell": it sorts into review today /
just watch. `score` is a diagnostic of the filter (did the flags anticipate
anything?), not the performance of a strategy.

**Integration with the daily email**: `bin/seguimiento` runs at 8:00 and writes
`vault/outputs/seguimiento.md`; `bin/analiza` runs at 8:05 and, if that file is
from today, **appends the tracking to its email** ("Jarvis: Mercado …"). So you
get a single email with the market summary + your watchlist analysis. Telegram
sends the two separately. To have `bin/seguimiento` send its own email
(standalone, not depending on `analiza`): `bin/seguimiento scan --notify --email`.

**Voice / Telegram triggers** (spoken in Spanish):
- *"cómo va mi watchlist"*, *"algo importante en mis tickers"* → `bin/seguimiento`
- *"revisa el seguimiento"* / *"¿acertaron los avisos?"* → `bin/seguimiento score`

**Cron (Pi)** — daily, just before the 8:05 `bin/analiza`:
```
0 8 * * * cd /home/pi/jarvis && bin/seguimiento >> /tmp/jarvis-seguimiento.log 2>&1
0 18 * * 5 cd /home/pi/jarvis && bin/seguimiento score >> /tmp/jarvis-seguimiento.log 2>&1
```

## Cardmarket (MKM API)

Wrapper in `agents/cardmarket.py`. Credentials in `agents/.env` (see `agents/cardmarket.env.example`).

```bash
python3 agents/cardmarket.py search "Ragavan"          # search for a card
python3 agents/cardmarket.py search "Charizard" --game 3  # Pokémon
python3 agents/cardmarket.py price <idProduct>         # guide price
python3 agents/cardmarket.py stock                     # your stock
python3 agents/cardmarket.py set-price <id> <price>    # change price
python3 agents/cardmarket.py orders                    # recent orders
```

Games: `--game 1` Magic (default), `2` YuGiOh, `3` Pokémon, `6` Lorcana.

How to get API credentials:
1. Go to cardmarket.com → your account → Developer Tools → Create App
2. Copy App Token + App Secret
3. Generate Access Token + Access Secret on the same page
4. Add them to `agents/.env`

## Notifications & Morning Brief

`bridge/notify.py` is the single module for sending Jarvis notifications. It supports three channels — all configured via environment variables in `bridge/.env` (copy `bridge/.env.example`).

### Channels

| Channel | Env vars needed | What it sends |
|---|---|---|
| Discord | `JARVIS_DISCORD_WEBHOOK` | Text message via webhook |
| Telegram | `JARVIS_TELEGRAM_TOKEN` + `JARVIS_TELEGRAM_CHAT_ID` | Text, or MP3 voice note if Kokoro is running |

### Sending a notification

```bash
# Send to all configured channels
python3 bridge/notify.py "Message text"

# Send only to specific channels
python3 bridge/notify.py --channels discord,telegram "Message"
python3 bridge/notify.py --channels call "Jarvis llamando"

# Skip voice synthesis (text-only Telegram)
python3 bridge/notify.py --no-voice "Plain text"
```

Or from Python:
```python
from bridge.notify import dispatch
dispatch("Buenos días, Sergio. Tu agenda de hoy...")
```

### Morning Brief (daily cron)

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

## Proactive reminders

`bin/check-reminders` reads `vault/outputs/recordatorios.md` and sends a Telegram notification for any reminder due in the next 30 minutes.

```bash
# Install cron on Pi:
crontab -e
# Add (every 30 minutes):
*/30 * * * * cd /home/pi/jarvis && python3 bin/check-reminders >> /tmp/jarvis-reminders.log 2>&1
```

## Vault auto-refresh

`bin/vault-refresh` re-runs all skills (plan, habitos, recordatorios, inbox) so the HUD always shows fresh data.

```bash
# Add to Pi crontab (30 min before morning brief):
30 7 * * * cd /home/pi/jarvis && bin/vault-refresh >> /tmp/jarvis-vault.log 2>&1
```

## Health watchdog

`bin/watchdog` checks the bridge (port 8792), the Telegram bot process, and device agent last-seen timestamps. Sends a Telegram alert when anything goes down or recovers.

```bash
# Add to Pi crontab (every 5 minutes):
*/5 * * * * cd /home/pi/jarvis && python3 bin/watchdog >> /tmp/jarvis-watchdog.log 2>&1
```

## Web search

`bin/search` queries DuckDuckGo's Instant Answer API (no API key required).

```bash
python3 bin/search "tiempo en Madrid mañana"
python3 bin/search "precio del Bitcoin hoy"
```

When asked about current events, news, weather, or anything time-sensitive, use bash to call `python3 bin/search "query"` before answering.

## Phone bridge security

`bridge/server.py` inherits whatever Bash permissions are pre-approved in this project's `.claude/settings.local.json`. If you've approved broad rules there (e.g. `Bash(python3 *)`), anyone who obtains the bridge token can get Claude to run those commands with **no confirmation prompt**, since the bridge runs Claude headless (`-p`) and there's no one to approve/deny. Review that file before exposing the bridge beyond your own devices. On a phone the HUD (`hud/index.html`) shows a client-side WebAuthn biometric gate (Face ID / fingerprint) before it unlocks, as a UX-level protection against a lost/unlocked phone — it does **not** cryptographically verify anything server-side (no signature check), so it doesn't protect against someone who already has the token and calls the API directly. Note also that `hud/jarvis-config.js` carries the token in plain text and is served by the `:8791` static server, so anyone who can reach the Tailscale node can read it.
