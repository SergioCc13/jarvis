# Jarvis

A personal voice assistant built on [Claude Code](https://claude.com/claude-code) + the [voicemode MCP](https://github.com/mbailey/voicemode) (local Whisper STT + Kokoro TTS), with a live HUD dashboard and optional phone access over [Tailscale](https://tailscale.com).

- Talk to it locally through Claude Code's voice tools.
- Watch a HUD (habits, agenda, skills, an animated voice "orb") in the browser.
- Optionally use that same HUD from your phone over your Tailscale network — text and voice both live in the HUD's chat panel, sharing the phone's own persistent conversation, separate from your terminal session. The HUD is the only page: it installs as a PWA and adapts its layout for phone and laptop.

## How it works

```
you (voice, local mic)  ──► mcp__voicemode__converse ──► Claude Code (interactive session)
you (voice, HUD)        ──► hud/index.html ──► bridge/server.py ──► Whisper STT
                                                              └──► claude -p --resume (headless session)
                                                              └──► Kokoro TTS ──► audio back to the HUD
you (text, HUD)         ──► hud/index.html ──► bridge/server.py ──► claude -p --resume (same headless session)
```

See `CLAUDE.md` for the full layout and the "jarvis on" trigger behavior.

## Requirements

- [Claude Code](https://claude.com/claude-code) CLI.
- [voicemode MCP](https://github.com/mbailey/voicemode) configured with local Whisper + Kokoro services (`voicemode service start whisper|kokoro`).
- Python 3 (bridge and HUD server use only the standard library — no `pip install` needed).
- For phone access: a [Tailscale](https://tailscale.com) account, with **Tailscale Serve** enabled once in the admin console (`https://login.tailscale.com/f/serve`) — needed because mobile browsers require HTTPS to grant microphone access.

## Setup

1. Clone this repo.
2. Make sure `voicemode service start whisper` and `voicemode service start kokoro` work (see the voicemode MCP docs).
3. Run the launcher:
   ```
   bin/jarvis
   ```
   This starts whisper/kokoro, serves the HUD at `http://localhost:8791/hud/`, starts the phone bridge on `:8792`, and opens a `jarvis on` Claude Code session. On first run, `bin/jarvis` is a good starting point to adapt if your setup differs (e.g. native Linux/macOS instead of WSL — see the comments in the script).
4. (Optional, for the HUD's audio strip) symlink your voicemode event log directory into the HUD:
   ```
   ln -s ~/.voicemode/logs/events hud/voicemode-logs
   ```
5. (Optional, for phone access) after `bin/jarvis` has set up `tailscale serve`, open your Tailscale node's HTTPS URL on your phone, passing the bridge token once:
   ```
   https://<your-tailscale-node>.ts.net/hud/?token=<token from bridge/config.json>
   ```
   The token is stored in the browser after the first open, so later you can just open `.../hud/`. On the phone the HUD shows a Face ID / fingerprint gate before it unlocks (a UX guard against a lost or unlocked phone — see the security notes). Use **Add to Home Screen** to install it as a standalone app.

   **Read the security notes in `CLAUDE.md` before doing this** — the bridge token grants whatever Bash permissions your project's `.claude/settings.local.json` already pre-approves.

## Auto-start on PC boot (optional)

So voice/chat via the PC are available whenever it's powered on, without remembering to run `bin/jarvis` by hand: `bin/jarvis` calls into `bin/jarvis-services` for the actual service-starting logic (whisper/kokoro/HUD/bridge/tailscale serve — no browser, no interactive Claude session), which is safe to run unattended. On Windows/WSL2, a `.bat` in the Windows Startup folder (`shell:startup`, i.e. `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`) running `wsl.exe -d <your-distro> -u <your-user> /path/to/jarvis-services` at every login covers this without needing admin rights (unlike Task Scheduler, which may need elevation depending on your machine's policy).

## Vault (optional)

The Spanish-language skills (`plan`, `inbox`, `habitos`, `recordatorios`, `vault`) write their output to `vault/outputs/*.md`, which the HUD reads. These skills aren't included in this repo (they live in your Claude Code skills directory) — without them the HUD just shows empty panels, which is fine.

## License

MIT — see `LICENSE`.
