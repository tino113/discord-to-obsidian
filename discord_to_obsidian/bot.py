"""Discord bot implementation for exporting messages into Obsidian-ready Markdown."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from zoneinfo import ZoneInfo

from .config import ConfigManager, GuildConfig
from .storage import StorageManager

DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "configs.json"
STORAGE_ROOT = DATA_DIR / "vault"
BOT_VERSION = "0.1.0"


class ObsidianBot(commands.Bot):
    """Custom bot with helpers for accessing config and storage."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)
        self.config_manager = ConfigManager(CONFIG_PATH)
        self.storage_manager = StorageManager(STORAGE_ROOT)

    async def setup_hook(self) -> None:
        self.tree.add_command(build_obsidian_group(self))
        await self.tree.sync()

    # ---------- permission helpers ----------
    def _has_permissions(self, interaction: discord.Interaction) -> bool:
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            return False
        guild = interaction.guild
        if guild is None:
            return False
        config = self.config_manager.get(guild.id)
        if config.admin_role_id:
            role = guild.get_role(config.admin_role_id)
            return role in interaction.user.roles if role else False
        return interaction.user.guild_permissions.manage_guild

    def _require_permissions(self, interaction: discord.Interaction) -> None:
        if not self._has_permissions(interaction):
            raise app_commands.CheckFailure("You do not have permission to use this command.")

    # ---------- message listeners ----------
    async def on_message(self, message: discord.Message) -> None:
        await super().on_message(message)
        if message.author.bot or not message.guild:
            return
        config = self.config_manager.get(message.guild.id)
        if not self._should_log(config, message.channel.id):
            return
        await self._persist_message(config, message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.author.bot or not after.guild:
            return
        config = self.config_manager.get(after.guild.id)
        if not self._should_log(config, after.channel.id):
            return
        await self._persist_message(config, after, event="edited")

    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        config = self.config_manager.get(message.guild.id)
        if not self._should_log(config, message.channel.id):
            return
        await self._persist_message(config, message, event="deleted")

    def _should_log(self, config: GuildConfig, channel_id: int) -> bool:
        if config.include_channels and channel_id not in config.include_channels:
            return False
        if config.exclude_channels and channel_id in config.exclude_channels:
            return False
        return True

    async def _persist_message(self, config: GuildConfig, message: discord.Message, event: str = "message") -> None:
        attachments = [attachment.url for attachment in message.attachments]
        content = message.clean_content
        author = f"@{message.author.display_name}"
        channel_name = (
            message.channel.name
            if isinstance(message.channel, discord.abc.GuildChannel)
            else str(message.channel.id)
        )
        self.storage_manager.append_message(
            config,
            channel_name=channel_name,
            message_id=message.id,
            author=author,
            content=content,
            timestamp=message.created_at,
            attachments=attachments,
            event=event,
        )

    # ---------- helpers ----------
    async def _send_zip(self, interaction: discord.Interaction, *, paths: Iterable[Path], label: str) -> None:
        buffer = self.storage_manager.zip_paths(paths)
        await interaction.followup.send(file=discord.File(buffer, filename=f"{label}.zip"))


def build_obsidian_group(bot: ObsidianBot) -> app_commands.Group:
    obsidian = app_commands.Group(name="obsidian", description="Manage Obsidian exports")

    # ---------- CONFIG GROUP ----------
    config_group = app_commands.Group(name="config", description="Configuration commands", parent=obsidian)

    @config_group.command(name="show", description="Show current configuration")
    async def config_show(interaction: discord.Interaction) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        config = bot.config_manager.get(guild.id)
        data = asdict(config)
        lines = ["**Current Configuration**"]
        for key, value in data.items():
            lines.append(f"- `{key}`: {value}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @config_group.command(name="set_export_mode")
    @app_commands.describe(mode="single, monthly, daily or custom", custom_days="Only used for custom mode")
    async def config_set_export_mode(
        interaction: discord.Interaction, mode: str, custom_days: Optional[int] = None
    ) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        if mode not in {"single", "monthly", "daily", "custom"}:
            await interaction.response.send_message("Invalid mode.", ephemeral=True)
            return
        bot.config_manager.update(guild.id, export_mode=mode, custom_period_days=custom_days or 7)
        await interaction.response.send_message(f"Export mode set to {mode}.", ephemeral=True)

    @config_group.command(name="set_timezone")
    async def config_set_timezone(interaction: discord.Interaction, timezone_name: str) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        try:
            ZoneInfo(timezone_name)
        except Exception:
            await interaction.response.send_message("Invalid timezone.", ephemeral=True)
            return
        bot.config_manager.update(guild.id, timezone=timezone_name)
        await interaction.response.send_message(f"Timezone updated to {timezone_name}.", ephemeral=True)

    @config_group.command(name="set_vault_path")
    async def config_set_vault_path(interaction: discord.Interaction, vault_path: str) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        bot.config_manager.update(guild.id, vault_path=vault_path)
        await interaction.response.send_message(f"Vault path updated to {vault_path}.", ephemeral=True)

    @config_group.command(name="include_channels")
    async def config_include_channels(interaction: discord.Interaction, channels: str) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        ids = _parse_channel_ids(channels)
        bot.config_manager.update(guild.id, include_channels=ids)
        await interaction.response.send_message("Include list updated.", ephemeral=True)

    @config_group.command(name="exclude_channels")
    async def config_exclude_channels(interaction: discord.Interaction, channels: str) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        ids = _parse_channel_ids(channels)
        bot.config_manager.update(guild.id, exclude_channels=ids)
        await interaction.response.send_message("Exclude list updated.", ephemeral=True)

    @config_group.command(name="set_role")
    async def config_set_role(interaction: discord.Interaction, role: discord.Role) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        bot.config_manager.update(guild.id, admin_role_id=role.id)
        await interaction.response.send_message(f"Admin role set to {role.name}.", ephemeral=True)

    @config_group.command(name="backfill")
    @app_commands.describe(channel="Channel to backfill", limit="Number of messages to fetch (max 1000)")
    async def config_backfill(
        interaction: discord.Interaction, channel: discord.TextChannel, limit: Optional[int] = 200
    ) -> None:
        bot._require_permissions(interaction)
        if limit and (limit < 1 or limit > 1000):
            await interaction.response.send_message("Limit must be between 1 and 1000.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        config = bot.config_manager.get(interaction.guild_id)
        count = 0
        async for message in channel.history(limit=limit, oldest_first=True):
            await bot._persist_message(config, message)
            count += 1
        await interaction.followup.send(f"Backfilled {count} messages from {channel.mention}.", ephemeral=True)

    @config_group.command(name="set_filename_template")
    async def config_set_filename_template(interaction: discord.Interaction, template: str) -> None:
        bot._require_permissions(interaction)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        bot.config_manager.update(guild.id, filename_template=template)
        await interaction.response.send_message("Filename template updated.", ephemeral=True)

    obsidian.add_command(config_group)

    # ---------- EXPORT GROUP ----------
    export_group = app_commands.Group(name="export", description="Export commands", parent=obsidian)

    @export_group.command(name="list")
    async def export_list(interaction: discord.Interaction) -> None:
        bot._require_permissions(interaction)
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        config = bot.config_manager.get(interaction.guild_id)
        files = bot.storage_manager.list_files(config)
        if not files:
            await interaction.response.send_message("No files available yet.", ephemeral=True)
            return
        preview = "\n".join(f"- {path.relative_to(STORAGE_ROOT)}" for path in files[:25])
        more = " (truncated)" if len(files) > 25 else ""
        await interaction.response.send_message(f"Found {len(files)} files{more}:\n{preview}", ephemeral=True)

    @export_group.command(name="channel")
    @app_commands.describe(channel="Channel", date_range="Optional text filter like 2024-01")
    async def export_channel(interaction: discord.Interaction, channel: discord.TextChannel, date_range: Optional[str] = None) -> None:
        bot._require_permissions(interaction)
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this command inside a guild.", ephemeral=True)
            return
        config = bot.config_manager.get(interaction.guild_id)
        files = [path for path in bot.storage_manager.list_files(config) if str(channel.id) in path.stem or channel.name in path.stem]
        if date_range:
            files = [path for path in files if date_range in path.name]
        if not files:
            await interaction.response.send_message("No files match the request.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await bot._send_zip(interaction, paths=files, label=f"{channel.name}_export")

    @export_group.command(name="all")
    async def export_all(interaction: discord.Interaction) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        files = bot.storage_manager.list_files(config)
        if not files:
            await interaction.response.send_message("No files available yet.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await bot._send_zip(interaction, paths=files, label=f"guild_{interaction.guild_id}_export")

    @export_group.command(name="search")
    async def export_search(interaction: discord.Interaction, keyword: str) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        matches = bot.storage_manager.search(config, keyword=keyword)
        if not matches:
            await interaction.response.send_message("No matches found.", ephemeral=True)
            return
        preview = "\n".join(f"- {path.relative_to(STORAGE_ROOT)}" for path in matches[:20])
        await interaction.response.send_message(f"Found {len(matches)} files:\n{preview}", ephemeral=True)

    obsidian.add_command(export_group)

    # ---------- MAINTENANCE COMMANDS ----------
    @obsidian.command(name="status")
    async def status(interaction: discord.Interaction) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        files = bot.storage_manager.list_files(config)
        total_size = sum(path.stat().st_size for path in files)
        await interaction.response.send_message(
            f"Vault path: {config.vault_path}\n"
            f"Files: {len(files)}\n"
            f"Total size: {total_size / 1024:.1f} KiB",
            ephemeral=True,
        )

    @obsidian.command(name="clear_cache")
    async def clear_cache(interaction: discord.Interaction) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        bot.storage_manager.clear_cache(config)
        await interaction.response.send_message("Cache cleared.", ephemeral=True)

    @obsidian.command(name="purge")
    async def purge(interaction: discord.Interaction, channel_name: Optional[str] = None) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        removed = bot.storage_manager.purge(config, channel_name=channel_name)
        await interaction.response.send_message(f"Removed {removed} files.", ephemeral=True)

    @obsidian.command(name="help")
    async def help_command(interaction: discord.Interaction) -> None:
        description = (
            "Use `/obsidian config` commands to adjust settings, `/obsidian export` to retrieve data, "
            "and `/obsidian status` for stats."
        )
        await interaction.response.send_message(description, ephemeral=True)

    @obsidian.command(name="version")
    async def version(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Discord to Obsidian bot v{BOT_VERSION}", ephemeral=True)

    @obsidian.command(name="test_export")
    async def test_export(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        bot._require_permissions(interaction)
        config = bot.config_manager.get(interaction.guild_id)
        timestamp = datetime.now(timezone.utc)
        bot.storage_manager.append_message(
            config,
            channel_name=channel.name,
            message_id=0,
            author="@Test",
            content="This is a test entry.",
            timestamp=timestamp,
            attachments=None,
            event="test",
        )
        await interaction.response.send_message("Test entry written.", ephemeral=True)

    return obsidian


def _parse_channel_ids(raw: str) -> List[int]:
    ids = []
    for chunk in raw.replace("<", " ").replace(">", " ").split():
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return ids


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is required")
    bot = ObsidianBot()
    bot.run(token)


if __name__ == "__main__":
    main()
