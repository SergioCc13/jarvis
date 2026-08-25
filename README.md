# Jarvis

A personal voice assistant built on [Claude Code](https://claude.com/claude-code) + the [voicemode MCP](https://github.com/mbailey/voicemode) (local Whisper STT + Kokoro TTS), with a live HUD dashboard and optional phone access over [Tailscale](https://tailscale.com).

- Talk to it locally through Claude Code's voice tools.
- Watch a HUD (habits, agenda, skills, an animated voice "orb") in the browser.
- Optionally talk to it from your phone over your Tailscale network — by voice or by text, both sharing the phone's own persistent conversation, separate from your terminal session.

## How it works

```
you (voice, local mic)  ──► mcp__voicemode__converse ──► Claude Code (interactive session)
you (voice, phone)      ──► hud/voice.html ──► bridge/server.py ──► Whisper STT
                                                              └──► claude -p --resume (headless session)
                                                              └──► Kokoro TTS ──► audio back to phone
you (text, phone)       ──► hud/chat.html  ──► bridge/server.py ──► claude -p --resume (same headless session)
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
5. (Optional, for phone access) after `bin/jarvis` has set up `tailscale serve`, open the printed bridge token + your Tailscale node's HTTPS URL on your phone — voice:
   ```
   https://<your-tailscale-node>.ts.net/hud/voice.html?token=<token from bridge/config.json>
   ```
   or text chat (same token, no microphone needed):
   ```
   https://<your-tailscale-node>.ts.net/hud/chat.html?token=<token from bridge/config.json>
   ```
   `chat.html` also has a mic button for voice, which talks to *this* PC's bridge specifically (needed if `chat.html` itself is hosted elsewhere, e.g. an always-on Raspberry Pi doing text-only Jarvis). It needs a second URL param the first time: `&voice_token=<same token from bridge/config.json>`, and the PC's Tailscale hostname is a constant (`PC_VOICE_HOST`) near the top of `chat.html`'s `<script>` — update it if your PC's Tailscale node name changes. The mic button checks that this PC is actually reachable before recording, so it fails with a clear message instead of a network error when the PC is off.

   **Read the security notes in `CLAUDE.md` before doing this** — the bridge token grants whatever Bash permissions your project's `.claude/settings.local.json` already pre-approves.

## Auto-start on PC boot (optional)

So voice/chat via the PC are available whenever it's powered on, without remembering to run `bin/jarvis` by hand: `bin/jarvis` calls into `bin/jarvis-services` for the actual service-starting logic (whisper/kokoro/HUD/bridge/tailscale serve — no browser, no interactive Claude session), which is safe to run unattended. On Windows/WSL2, a `.bat` in the Windows Startup folder (`shell:startup`, i.e. `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`) running `wsl.exe -d <your-distro> -u <your-user> /path/to/jarvis-services` at every login covers this without needing admin rights (unlike Task Scheduler, which may need elevation depending on your machine's policy).

## Vault (optional)

The Spanish-language skills (`plan`, `inbox`, `habitos`, `recordatorios`, `vault`) write their output to `vault/outputs/*.md`, which the HUD reads. These skills aren't included in this repo (they live in your Claude Code skills directory) — without them the HUD just shows empty panels, which is fine.

## License

MIT — see `LICENSE`.
