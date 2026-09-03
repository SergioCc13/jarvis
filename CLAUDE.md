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

### Starting an agent on a device

```bash
# On the Mac / PC — copy the example env file, fill in the Pi IP and bridge token, then:
cp agents/env.example agents/.env
# edit agents/.env: set JARVIS_HUB_URL and JARVIS_HUB_TOKEN
source agents/.env && python3 agents/device_agent.py
```

`JARVIS_HUB_TOKEN` must match the `"token"` field in `bridge/config.json` on the Pi — the hub requires it to authenticate device registrations. The agent stores its own token in `agents/config.json` (gitignored).

Add it to a launchd plist (Mac) or systemd service (Linux) for auto-start on boot.

## Modo multi-agente

**Trigger**: el usuario dice o escribe `agentes:` seguido de la tarea.

Ejemplos:
- *"agentes: busca el precio de Ragavan y dime si es buen momento para vender"*
- *"agentes: revisa mi stock de Cardmarket y baja un 10% todo lo que lleve más de 30 días sin venderse"*
- *"agentes: investiga las cartas más vendidas de Lorcana esta semana"*

**Cómo responder**: descompón la tarea en subtareas y lanza agentes especializados en paralelo usando el `Agent` tool de Claude Code. Roles estándar:

| Rol | Qué hace |
|---|---|
| **Investigador** | Busca información — usa `python3 agents/cardmarket.py`, `python3 bin/search`, `curl` |
| **Analista** | Evalúa los datos del investigador y saca conclusiones |
| **Ejecutor** | Toma acciones concretas — modifica precios, envía notificaciones |
| **Crítico** | Revisa el trabajo del resto y señala errores o mejoras |

No todos los agentes son necesarios en cada tarea — usa solo los que la tarea requiera. El resultado final se envía siempre por Telegram (`python3 bridge/notify.py --no-voice "resultado"`).

**Flujo tipo para Cardmarket**:
1. Investigador busca precios con `python3 agents/cardmarket.py`
2. Analista compara con tendencias y decide acción
3. Ejecutor aplica cambios si el usuario lo pidió (`set-price`)
4. Resumen → Telegram

## Scraper de precios y webs

`agents/scraper.py` obtiene precios de cartas y texto de cualquier URL. Stdlib puro, sin API keys.

| Juego | Fuente | Incluye precio Cardmarket EUR |
|---|---|---|
| Magic | Scryfall API (oficial) | ✅ sí |
| YuGiOh | ygoprodeck.com API | TCGPlayer USD |
| Pokémon | pokemontcg.io (fallback DDG) | TCGPlayer USD |

```bash
# Cartas
python3 agents/scraper.py magic "Ragavan Nimble Pilferer"
python3 agents/scraper.py pokemon "Charizard"
python3 agents/scraper.py yugioh "Dark Magician"

# Personas
python3 agents/scraper.py persona "Elon Musk"              # búsqueda multi-fuente
python3 agents/scraper.py github "torvalds"                # perfil GitHub (API oficial, sin key)
python3 agents/scraper.py twitter "elonmusk"               # perfil Twitter/X vía Nitter

# Búsqueda
python3 agents/scraper.py google "consulta"                # Google vía SerpAPI (si hay key) o DDG
python3 agents/scraper.py search "consulta"                # DuckDuckGo Instant Answer
python3 agents/scraper.py url "https://cualquier-web.com"  # texto limpio de cualquier web

# Trabajo
python3 agents/scraper.py jobs "desarrollador python"
python3 agents/scraper.py jobs "diseñador UX" --lugar "Barcelona"
```

- `persona`: combina DDG + GitHub API + LinkedIn/Twitter vía DDG site-search + links directos
- `github`: API oficial de GitHub, gratuita, sin key — devuelve bio, empresa, repos, seguidores
- `twitter`: intenta leer perfil vía mirrors Nitter (sin login), fallback a links directos
- `google`: usa SerpAPI si `SERPAPI_KEY` está en `agents/.env` (100 búsquedas/mes gratis), si no DDG
- `jobs`: Indeed/Infojobs (scraping) + Remotive API (remoto, gratis) + links directos

Usa este scraper siempre que el usuario pregunte por precios de cartas, pida info de una persona, de una web, o busque trabajo.

## Análisis de mercado

`agents/trading.py` recoge datos de mercado en tiempo real (stdlib puro, sin pip).
`bin/analiza` genera el email **"Jarvis: Mercado"** y lo envía por **email + Telegram**.

**Cadencia**: informe **completo** (multi-agente) los **lunes**; informe **rápido**
(`--rapido`, 1 sola llamada) el **resto de días**. Lo instala `bin/install-pi`.

| Fuente | Cubre | Key necesaria |
|---|---|---|
| Yahoo Finance | Acciones (sufijos .MC/.DE/.L), ETFs, índices (^GSPC, ^GDAXI, ^VIX…), materias primas (GC=F, CL=F), FX (DX-Y.NYB) | No |
| CoinGecko | Cripto (BTC, ETH, SOL, XRP, ADA, DOGE…) | No |
| agents/scraper.py | Cartas TCG (precio Cardmarket EUR) | No |

### Motor multi-agente (informe completo, lunes)

`bin/analiza` sin flags ejecuta `agents/analistas.py`: por cada activo de
`agents/watchlist.txt` corre una cadena de roles inspirada en
[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents),
cada rol una llamada a `claude -p` que ve el trabajo del anterior:

1. **Analista técnico/cuantitativo** — tendencia, momentum, volumen, 52 semanas (solo hechos)
2. **Analista de contexto y eventos** — catalizadores, próximo evento
3. **Investigador alcista** — mejor tesis de compra
4. **Investigador bajista** — rebate y construye el caso bajista
5. **Trader** — sopesa el debate, decisión preliminar + rangos entrada/salida
6. **Gestor de riesgo / cartera** — veredicto FINAL en el formato del email

Luego un rol de cartera escribe la **Visión de cartera** que encabeza el informe.
Cada activo queda con un bloque: Puntuación 0-100, Recomendación
(Compra fuerte/floja · Neutral · Venta floja/fuerte), Plazo, Precio objetivo de
entrada y de salida, Próximo evento relevante, y Justificación.

Los indicadores (RSI, SMA 50/200, 52 s, volumen) los aporta `agents/seguimiento.py`.
La línea **"Próximo evento relevante" NO la inventa el LLM**: sale de
`agents/calendar_data.py` (calendario oficial de la Fed + fechas de
resultados/dividendos de Yahoo Finance) y se fuerza en el bloque final. El email
**adjunta el gráfico de puntuaciones** (`agents/charts.py --scores`, 0 tokens;
necesita `python3-matplotlib`, que instala `bin/install-pi`).

**Coste**: ~6 llamadas por activo + 1. Con la watchlist de 21 activos ≈ 127 llamadas
y **~20-40 min** por ejecución. Por eso corre **solo los lunes**. No es asesoría
financiera: es un scaffold de análisis.

```bash
bin/analiza                       # watchlist completa, multi-agente → email + Telegram
bin/analiza --only BTC ETH        # solo esos activos (para probar)
bin/analiza --limit 3             # solo los 3 primeros
bin/analiza --rapido [SÍMBOLOS]   # 1 llamada: resumen de 180 palabras (informe diario)
python3 agents/trading.py AAPL BTC ^GSPC   # solo datos brutos, sin LLM
```

**Watchlist diaria** (`agents/watchlist.txt`): un símbolo por línea. Las líneas
`nombre tcg juego` (cartas) las ignora el motor de mercado.

**Email**: necesita `JARVIS_EMAIL_PASSWORD` en `bridge/.env` (Gmail App Password).
Cómo obtenerlo: myaccount.google.com → Seguridad → Verificación en 2 pasos → Contraseñas de app → crear "Jarvis".

**Triggers de voz/Telegram** que debes reconocer:
- *"analiza AAPL"*, *"cómo va BTC hoy"* → `bin/analiza --only SÍMBOLO`
- *"resumen rápido del mercado"* → `bin/analiza --rapido`
- *"agentes: analiza mi cartera"* → `bin/analiza` (ya es multi-agente)

**Cron (Pi)** — añadido por `bin/install-pi`:
```
30 6 * * 1     cd /home/pi/jarvis && bin/analiza          >> /tmp/jarvis-mercado.log 2>&1  # completo, lunes
0  7 * * 0,2-6 cd /home/pi/jarvis && bin/analiza --rapido >> /tmp/jarvis-mercado.log 2>&1  # rápido, resto
```

El informe se guarda en `vault/outputs/mercado.md` (visible en el HUD). Telegram
recibe solo la Visión de cartera; el informe completo va en el email.

### Seguimiento con filtro de eventos

`agents/seguimiento.py` + `bin/seguimiento` hacen seguimiento diario de la misma
`agents/watchlist.txt`, pero al revés que `bin/analiza`: en vez de resumir todo cada
día, calculan indicadores (RSI 14, SMA 50/200, máx/mín de 52 semanas, ratio de
volumen), guardan histórico en SQLite (`vault/raw/seguimiento.db`) y **solo llaman
al LLM para los tickers que disparan una señal**. Días tranquilos: no gasta tokens
y no manda nada por Telegram (solo actualiza `vault/outputs/seguimiento.md`).

Señales que disparan análisis (umbrales en `TH`, overridables por env `JARVIS_SEG_*`):
movimiento diario ≥4%, 5d ≥8%, volumen ≥x2 vs media 20d, RSI ≥75 o ≤25, a <2% de
máx/mín de 52 semanas, cruce de medias 50/200.

```bash
bin/seguimiento                 # barrido + veredicto LLM + Telegram si hay señales
bin/seguimiento scan            # solo la tabla de indicadores, sin LLM
bin/seguimiento scan --json     # + volcado JSON
bin/seguimiento scan --notify --always   # notifica aunque no haya nada
bin/seguimiento score           # cómo se movieron los tickers marcados hace ≥14 días
```

El veredicto es de *seguimiento*, nunca "compra/vende": clasifica en revisar hoy /
solo vigilar. `score` es diagnóstico del filtro (¿los flags anticiparon algo?), no
rendimiento de una estrategia.

**Integración con el email diario**: `bin/seguimiento` corre a las 8:00 y escribe
`vault/outputs/seguimiento.md`; `bin/analiza` corre a las 8:05 y, si ese fichero es
de hoy, **añade el seguimiento a su email** ("Jarvis: Mercado …"). Así recibes un
único correo con el resumen de mercado + el análisis de tu watchlist. Telegram
manda los dos por separado. Para que `bin/seguimiento` mande su propio email
(standalone, sin depender de `analiza`): `bin/seguimiento scan --notify --email`.

**Triggers de voz/Telegram**:
- *"cómo va mi watchlist"*, *"algo importante en mis tickers"* → `bin/seguimiento`
- *"revisa el seguimiento"* / *"¿acertaron los avisos?"* → `bin/seguimiento score`

**Cron (Pi)** — diario, justo antes del `bin/analiza` de las 8:05:
```
0 8 * * * cd /home/pi/jarvis && bin/seguimiento >> /tmp/jarvis-seguimiento.log 2>&1
0 18 * * 5 cd /home/pi/jarvis && bin/seguimiento score >> /tmp/jarvis-seguimiento.log 2>&1
```

## Cardmarket (MKM API)

Wrapper en `agents/cardmarket.py`. Credenciales en `agents/.env` (ver `agents/cardmarket.env.example`).

```bash
python3 agents/cardmarket.py search "Ragavan"          # buscar carta
python3 agents/cardmarket.py search "Charizard" --game 3  # Pokémon
python3 agents/cardmarket.py price <idProduct>         # precio guía
python3 agents/cardmarket.py stock                     # tu stock
python3 agents/cardmarket.py set-price <id> <precio>   # cambiar precio
python3 agents/cardmarket.py orders                    # pedidos recientes
```

Juegos: `--game 1` Magic (defecto), `2` YuGiOh, `3` Pokémon, `6` Lorcana.

Cómo obtener credenciales API:
1. Ve a cardmarket.com → tu cuenta → Developer Tools → Create App
2. Copia App Token + App Secret
3. Genera Access Token + Access Secret en la misma página
4. Añádelos a `agents/.env`

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
