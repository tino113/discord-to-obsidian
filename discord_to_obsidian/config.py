"""Configuration helpers for the Discord to Obsidian bot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_FILENAME_TEMPLATE = "{channel}/{year}-{month}-{day}"


@dataclass
class GuildConfig:
    """Represents the persisted configuration for a guild."""

    guild_id: int
    vault_path: str = "vaults"
    export_mode: str = "monthly"
    timezone: str = "UTC"
    include_channels: List[int] = field(default_factory=list)
    exclude_channels: List[int] = field(default_factory=list)
    admin_role_id: Optional[int] = None
    filename_template: str = DEFAULT_FILENAME_TEMPLATE
    custom_period_days: int = 7

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "vault_path": self.vault_path,
            "export_mode": self.export_mode,
            "timezone": self.timezone,
            "include_channels": self.include_channels,
            "exclude_channels": self.exclude_channels,
            "admin_role_id": self.admin_role_id,
            "filename_template": self.filename_template,
            "custom_period_days": self.custom_period_days,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuildConfig":
        return cls(
            guild_id=int(data["guild_id"]),
            vault_path=data.get("vault_path", "vaults"),
            export_mode=data.get("export_mode", "monthly"),
            timezone=data.get("timezone", "UTC"),
            include_channels=list(data.get("include_channels", [])),
            exclude_channels=list(data.get("exclude_channels", [])),
            admin_role_id=data.get("admin_role_id"),
            filename_template=data.get("filename_template", DEFAULT_FILENAME_TEMPLATE),
            custom_period_days=int(data.get("custom_period_days", 7)),
        )


class ConfigManager:
    """Utility that persists configuration for all guilds."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[int, GuildConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._cache = {}
            return
        try:
            payload = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            payload = {}
        for guild_id, data in payload.items():
            self._cache[int(guild_id)] = GuildConfig.from_dict(data)

    def _save(self) -> None:
        serialized = {guild_id: config.to_dict() for guild_id, config in self._cache.items()}
        self.path.write_text(json.dumps(serialized, indent=2, sort_keys=True))

    def get(self, guild_id: int) -> GuildConfig:
        if guild_id not in self._cache:
            self._cache[guild_id] = GuildConfig(guild_id=guild_id)
            self._save()
        return self._cache[guild_id]

    def update(self, guild_id: int, **kwargs: Any) -> GuildConfig:
        config = self.get(guild_id)
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self._cache[guild_id] = config
        self._save()
        return config

    def all_configs(self) -> List[GuildConfig]:
        return list(self._cache.values())


__all__ = ["ConfigManager", "GuildConfig", "DEFAULT_FILENAME_TEMPLATE"]
