# Discord to Obsidian Bot

A Discord bot that captures channel conversations and writes them to Obsidian-ready Markdown files. Everything is configurable through Discord slash commands under the `/obsidian` namespace.

## Features

- Real-time logging of every message, edit, and deletion the bot can see.
- Configurable export modes: single file per channel, monthly, daily, or custom buckets.
- Slash commands to change vault path, timezone, included/excluded channels, and permissions.
- Backfill command to ingest historical messages.
- Export commands to list, search, or download Markdown archives as ZIP files.
- Simple JSON-based configuration per guild and filesystem storage compatible with Obsidian vaults.

## Getting Started

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Create a Discord application/bot** and invite it to your server with the `applications.commands` and `bot` scopes. Grant `Read Message History`, `View Channels`, `Send Messages`, and `Attach Files` permissions.
3. **Set the token**
   ```bash
   export DISCORD_TOKEN=your_bot_token_here
   ```
4. **Run the bot**
   ```bash
   python -m discord_to_obsidian.bot
   ```
5. **Configure from Discord** using `/obsidian config ...` commands.

## Command Overview

- `/obsidian config show` – Display the current configuration.
- `/obsidian config set_export_mode` – Choose between `single`, `monthly`, `daily`, or `custom` storage.
- `/obsidian config set_timezone`, `set_vault_path`, `set_role`, `include_channels`, `exclude_channels`, `set_filename_template` – Adjust behavior.
- `/obsidian config backfill` – Pull historical messages from a channel.
- `/obsidian export list|channel|all|search` – Retrieve Markdown files or search contents.
- `/obsidian status|clear_cache|purge|help|version|test_export` – Maintenance helpers.

## Storage Layout

All data lives under `data/`. Each guild gets its own folder with configurable vault path. Files follow the chosen export mode and include frontmatter so they work nicely inside an Obsidian vault.

## Development Notes

- Configurations live in `data/configs.json` and can be edited manually when the bot is offline.
- The bot relies on `discord.Intents.message_content`; ensure it is enabled in the Developer Portal.
- Attachments are logged as links; download mirroring can be added inside `StorageManager.append_message` if desired.

## License

This project is provided as-is without warranty.
