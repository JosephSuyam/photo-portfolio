"""Builders for about.json / contact.json manifest entries and their cached originals."""

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portfolio.models import TextFile

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


def make_text_file(file_id: str, name: str) -> "TextFile":
    from portfolio.models import TextFile

    return TextFile(
        file_id=file_id,
        name=name,
        mime_type="application/json",
        md5_checksum=f"md5-{file_id}",
        modified_time=_EPOCH,
    )


def write_text_original(cache_dir: Path, file_id: str, content: str | bytes) -> Path:
    """Place a text page where sync stores originals: `<cache>/originals/<file_id>`."""
    path = cache_dir / "originals" / file_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path
