# Changelog

## v1.6.0 (2026-03-23)

### New Features
- **Discord file upload** — images, audio, and binary files returned by the agent (via ACP `image`, `audio`, `resource` content blocks) are uploaded directly to Discord using `discord.File`.
- **MCP tool result images** — images embedded in `tool_call_update` notifications (when MCP tool use results are JSON serialized and put into the text data) are extracted and uploaded automatically.
- **`resource_link` embed** — URI-only references are posted as rich Discord embeds; non-HTTP URIs are shown inline as code.
- Added `import json`, `import base64`, `import io` to `channel_discord`.
- `agent_acp`: `asyncio.StreamReader` buffer limit raised to 16 MB (configurable via `limit=`) to handle large base64-encoded payloads.

---

## v1.5.0 (2026-03-22)

### Changes
- Reorganised `plugins/` folder: legacy non-ACP plugin code moved to `plugins/text_body/historical/`.
- Replaced `settings_terminal_echo_test.json` example with `settings_terminal_conversation_test.json`.
- README and README_ja.md rewritten for clarity.

---

## v1.4.0 (2026-03-22)

### New Features
- **`/modes`, `/ai_models`, `/reasoning_efforts` commands** (Discord) — each command posts a Select menu (`ConfigSelectView`) that lists available options and sends `session/set_config_option` on selection.
- **Permission buttons** (Discord) — `session/request_permission` requests from the agent are presented as clickable buttons (`PermissionView`). Button colour reflects the ACP `kind` field (allow → red Danger, reject → grey Secondary).

---

## v1.3.0 (2026-03-22)

### New Features
- **`output_thought` setting** — streaming agent thought chunks (`💭 …`) can now be enabled per channel for Discord and LINE. Added to all example settings files.

---

## v1.2.0 (2026-03-22)

### New Features
- **Discord typing indicator** — a typing indicator is sent to Discord while the agent is processing, cancelled when `stopReason` arrives or after a 30-second safety timeout.

### Bug Fixes
- Fixed ACP `initialize` ID collision: when the agent rejects the ID with error code 7001, the channel now retries with a new random ID.

---

## v1.1.0 (2026-03-22)

### Changes
- **`work_dir` now overrides `cwd`** in all ACP requests — prevents channel plugins from setting an arbitrary working directory; the agent's configured `work_dir` is always used.

---

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

