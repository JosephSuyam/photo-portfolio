"""Domain models: albums, the photos inside them, and the root text pages."""

import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

# Drive file IDs are URL-safe; anything else could escape the cache directory.
_FILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


class Photo(BaseModel):
    """One image in an album, as known from Drive."""

    file_id: str
    name: str
    mime_type: str
    md5_checksum: str | None = None
    modified_time: datetime


class Album(BaseModel):
    """One Drive subfolder of the portfolio root."""

    folder_id: str
    name: str
    title: str
    slug: str
    photos: list[Photo]
    cover: Photo | None = None


class TextFile(BaseModel):
    """A plain-text page source in the Drive root (about.txt, contact.txt)."""

    file_id: str
    name: str
    mime_type: str
    md5_checksum: str | None = None
    modified_time: datetime


class Manifest(BaseModel):
    """Everything sync learned from Drive, already ordered, titled, and slugged."""

    albums: list[Album]
    about: TextFile | None = None
    contact: TextFile | None = None


def original_path(cache_dir: Path, file_id: str) -> Path:
    """Where sync stores the original bytes of `file_id` inside `cache_dir`.

    Raises ValueError if `file_id` is not a plain Drive-style ID, so it cannot form a path.
    """
    if not _FILE_ID_PATTERN.fullmatch(file_id):
        raise ValueError(f"Unsafe Drive file ID: {file_id!r}")
    return cache_dir / "originals" / file_id
