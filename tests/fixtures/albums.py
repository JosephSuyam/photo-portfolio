"""Builders for Photo/Album models and their cached originals."""

from datetime import UTC, datetime
from pathlib import Path

from portfolio.models import Album, Photo
from tests.fixtures.images import make_image

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


def make_photo(file_id: str, name: str | None = None) -> Photo:
    return Photo(
        file_id=file_id,
        name=name or f"{file_id}.jpg",
        mime_type="image/jpeg",
        md5_checksum=f"md5-{file_id}",
        modified_time=_EPOCH,
    )


def make_album(
    slug: str,
    photos: list[Photo],
    title: str | None = None,
    cover: Photo | None = None,
) -> Album:
    return Album(
        folder_id=f"folder-{slug}",
        name=title or slug,
        title=title or slug,
        slug=slug,
        photos=photos,
        cover=cover,
    )


def write_original(
    cache_dir: Path,
    file_id: str,
    color: tuple[int, int, int] = (200, 50, 50),
    size: tuple[int, int] = (40, 30),
) -> Path:
    """Place a tiny JPEG where sync stores originals: `<cache>/originals/<file_id>`."""
    return make_image(cache_dir / "originals" / file_id, size=size, color=color)


def write_corrupt_original(cache_dir: Path, file_id: str) -> Path:
    path = cache_dir / "originals" / file_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not an image at all")
    return path
