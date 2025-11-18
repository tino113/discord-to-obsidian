"""Storage helpers for writing Discord messages to Markdown."""

from __future__ import annotations

import io
import re
import shutil
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from zoneinfo import ZoneInfo

from .config import GuildConfig

MARKDOWN_HEADER = """---
channel: {channel}
server: {server}
period: {period}
export_mode: {export_mode}
generated_on: {generated}
---

"""

SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class StorageManager:
    """Handles writing Markdown files and preparing exports."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    # -------------- path helpers --------------
    def _safe(self, value: str) -> str:
        cleaned = SANITIZE_PATTERN.sub("-", value.strip())
        return cleaned.strip("-") or "untitled"

    def _base_dir(self, guild_id: int, vault_path: str) -> Path:
        path = self.root / str(guild_id) / vault_path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def determine_file_path(
        self, config: GuildConfig, *, channel_name: str, timestamp: datetime
    ) -> Path:
        tz = ZoneInfo(config.timezone)
        local_time = timestamp.astimezone(tz)
        channel_slug = self._safe(channel_name)
        base_dir = self._base_dir(config.guild_id, config.vault_path)

        year = f"{local_time.year:04d}"
        month = f"{local_time.month:02d}"
        day = f"{local_time.day:02d}"

        if config.export_mode == "single":
            rel_path = Path(channel_slug + ".md")
        elif config.export_mode == "daily":
            rel_path = Path(channel_slug) / f"{year}-{month}-{day}.md"
        elif config.export_mode == "monthly":
            rel_path = Path(channel_slug) / f"{year}-{month}.md"
        elif config.export_mode == "custom":
            days = max(1, config.custom_period_days)
            # Determine bucket start date
            bucket_start = local_time - timedelta(days=local_time.timetuple().tm_yday % days)
            rel_path = (
                Path(channel_slug)
                / f"{bucket_start.year:04d}-{bucket_start.month:02d}-{bucket_start.day:02d}_d{days}.md"
            )
        else:
            rel_path = Path(
                config.filename_template.format(
                    channel=channel_slug,
                    year=year,
                    month=month,
                    day=day,
                )
            )
            if not rel_path.suffix:
                rel_path = rel_path.with_suffix(".md")

        path = base_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # -------------- writing --------------
    def _ensure_header(self, path: Path, *, config: GuildConfig, channel_name: str, timestamp: datetime) -> None:
        if path.exists() and path.stat().st_size > 0:
            return
        period = "varies"
        if config.export_mode == "single":
            period = "all"
        elif config.export_mode == "daily":
            period = timestamp.strftime("%Y-%m-%d")
        elif config.export_mode == "monthly":
            period = timestamp.strftime("%Y-%m")
        header = MARKDOWN_HEADER.format(
            channel=channel_name,
            server=config.guild_id,
            period=period,
            export_mode=config.export_mode,
            generated=datetime.now(timezone.utc).isoformat(),
        )
        path.write_text(header)

    def append_message(
        self,
        config: GuildConfig,
        *,
        channel_name: str,
        message_id: int,
        author: str,
        content: str,
        timestamp: datetime,
        attachments: Optional[List[str]] = None,
        event: str = "message",
    ) -> Path:
        attachments = attachments or []
        file_path = self.determine_file_path(config, channel_name=channel_name, timestamp=timestamp)
        self._ensure_header(file_path, config=config, channel_name=channel_name, timestamp=timestamp)
        stamp = timestamp.strftime("%Y-%m-%d %H:%M")
        attachments_block = ""
        if attachments:
            attachments_block = "\n".join(f"- Attachment: {url}" for url in attachments)
        entry = (
            f"### {stamp} {author}\n"
            f"{content or '[no content]'}\n"
            f"- Message ID: {message_id}\n"
            f"- Event: {event}\n"
        )
        if attachments_block:
            entry += attachments_block + "\n"
        entry += "\n"
        with file_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return file_path

    # -------------- exports --------------
    def list_files(self, config: GuildConfig) -> List[Path]:
        base_dir = self._base_dir(config.guild_id, config.vault_path)
        return [p for p in base_dir.rglob("*.md") if p.is_file()]

    def search(self, config: GuildConfig, *, keyword: str) -> List[Path]:
        keyword_lower = keyword.lower()
        matches = []
        for path in self.list_files(config):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if keyword_lower in text.lower():
                matches.append(path)
        return matches

    def zip_paths(self, paths: Iterable[Path]) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path, arcname=str(path.relative_to(self.root)))
        buffer.seek(0)
        return buffer

    def purge(self, config: GuildConfig, *, channel_name: Optional[str] = None) -> int:
        paths = self.list_files(config)
        removed = 0
        for path in paths:
            if channel_name and self._safe(channel_name) not in path.parts:
                continue
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def clear_cache(self, config: GuildConfig) -> None:
        cache_dir = self._base_dir(config.guild_id, config.vault_path) / ".cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)


__all__ = ["StorageManager", "MARKDOWN_HEADER"]
