# Changelog

## v1.0.0 (2026-03-21)

### Breaking Changes
- Message `body` is now a full **ACP JSON-RPC 2.0 object** (previously plain text). All channel and agent plugins have been updated accordingly.
- `log()` function signature changed: `name` parameter added as the second argument.

### New Features
- **`channel_terminal` plugin** — interact with the agent from a local terminal session.
- **`logging.suppress_types`** setting — filter out specific log types (e.g. suppress `trace`) to reduce log noise.
- ACP JSON-RPC body support added to `channel_discord`, `channel_line`, `channel_schedule`, and `agent_acp`.
- ACP support added to `agent_echo` and `channel_random_talker`.

### Bug Fixes
- Prevented multiple instances of the terminal agent from starting.

---

## v0.4.0 (2026-03-13)

### New Features
- **LINE channel support** — chat with your AI via LINE Messaging API.
- Added LINE bot registration guide (`docs/LINE_bot_registration.md`).

---

## v0.3.0 (2026-03-13)

### New Features
- **`agent_acp` plugin** — connects to any ACP-compatible CLI (Copilot, Codex, Gemini, OpenCode, …) via JSON-RPC 2.0 over stdio; replaces the old `pty`-based approach.
- **Session continuation** — resume the previous session on startup with `-c`, `--continue`, or `-r latest`.
- **`output_thought` setting** — optionally stream agent thought chunks as `💭 …` messages.
- **Windows native support** — commands are resolved via `shutil.which`, removing the need for WSL.
- Expanded `asyncio.StreamReader` buffer: 64 KB → 4 MB to handle large ACP payloads.
- Removed `pexpect` dependency.

---

## v0.2.0 (2026-03-12)

- Discord: send long messages in multiple chunks of up to 2,000 characters.

---

## v0.1.0 (2026-03-07)

- Initial release.
- Plugin architecture: `Channel` and `Agent` abstract base classes with dynamic loading from `plugins/`.
- Discord channel plugin (`channel_discord`).
- Echo agent plugin (`agent_echo`) for testing.
- Environment variable expansion (`${VAR}`) in `settings.json`.

