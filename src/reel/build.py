"""Render the manifest into static HTML in `dist/` with Jinja2.

The site is built into a staging directory next to the output and swapped into place
only when every page and image was written, so a failed build leaves the previous
site untouched. Output directories not created by `reel build` are never overwritten.
"""

import logging
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import ValidationError

from reel.images import ImageError, ProcessedPhoto, process_photo
from reel.models import Album, Manifest, Photo, original_path

logger = logging.getLogger(__name__)

RESERVED_SLUGS = frozenset({"work", "static", "images"})
BUILD_MARKER = ".reel-build"
IMAGES_DIR = "images"
STATIC_DIR = Path(__file__).parent / "static"

_SLUG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class BuildError(Exception):
    """Raised when the site cannot be built; the previous output is left intact."""


@dataclass(frozen=True)
class PublishedAlbum:
    """An album with at least one usable photo, ready to render."""

    title: str
    slug: str
    cover: ProcessedPhoto
    photos: list[ProcessedPhoto]


def make_environment() -> Environment:
    """Jinja2 environment for the bundled templates, with HTML autoescaping on.

    Album and photo names come from Drive and are untrusted, so autoescape is mandatory.
    """
    return Environment(
        loader=PackageLoader("reel", "templates"),
        autoescape=select_autoescape(["html"]),
    )


def base_path_from_url(url: str) -> str:
    """URL path of the site root, with leading and trailing slash ("/" when none)."""
    path = urlparse(url).path.strip("/")
    return f"/{path}/" if path else "/"


def load_manifest(path: Path) -> Manifest:
    """Read the manifest written by `reel sync`."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise BuildError(f"{path} not found. Run `reel sync` first.") from error
    except OSError as error:
        raise BuildError(f"Cannot read {path}: {error}") from error
    try:
        return Manifest.model_validate_json(text)
    except ValidationError as error:
        raise BuildError(f"{path} is not a valid manifest. Run `reel sync` again.") from error


def slug_problem(slug: str, seen: set[str]) -> str | None:
    """Why `slug` cannot be used as an output directory, or None if it can."""
    if not _SLUG_PATTERN.fullmatch(slug):
        return "must be lowercase letters and digits separated by single hyphens"
    if slug in RESERVED_SLUGS:
        return "is reserved for site paths"
    if slug in seen:
        return "is used by more than one album"
    return None


def validate_slugs(albums: Sequence[Album]) -> None:
    """Raise BuildError for the first unsafe, reserved, or duplicate slug."""
    seen: set[str] = set()
    for album in albums:
        problem = slug_problem(album.slug, seen)
        if problem:
            raise BuildError(f"Album {album.name!r} has slug {album.slug!r} that {problem}.")
        seen.add(album.slug)


def image_url(base_path: str, name: str) -> str:
    """Public URL of a derived image file."""
    return f"{base_path}{IMAGES_DIR}/{name}"


def next_album_index(index: int, count: int) -> int | None:
    """Index of the album after `index`, wrapping to the first; None if there is only one."""
    if count < 2:
        return None
    return (index + 1) % count


def staging_dir_for(out_dir: Path) -> Path:
    """Sibling directory the site is built in before being swapped into `out_dir`."""
    return out_dir.parent / f".{out_dir.name}.staging"


def previous_dir_for(out_dir: Path) -> Path:
    """Sibling directory the previous site is moved to while the new one is swapped in."""
    return out_dir.parent / f".{out_dir.name}.old"


def build_site(
    manifest: Manifest,
    cache_dir: Path,
    out_dir: Path,
    site_title: str,
    base_path: str = "/",
) -> int:
    """Render `manifest` into `out_dir` and return the number of published albums."""
    validate_slugs(manifest.albums)
    _ensure_replaceable(out_dir)
    staging = staging_dir_for(out_dir)
    try:
        _remove(staging)
        published = _publish_albums(manifest.albums, cache_dir, staging / IMAGES_DIR)
        _render_site(published, staging, site_title, base_path)
        shutil.copytree(STATIC_DIR, staging / "static")
        (staging / BUILD_MARKER).touch()
        _swap_into_place(staging, out_dir)
    except OSError as error:
        _discard(staging)
        raise BuildError(f"Cannot write the site to {out_dir}: {error}") from error
    except BaseException:
        _discard(staging)
        raise
    return len(published)


def _swap_into_place(staging: Path, out_dir: Path) -> None:
    """Replace `out_dir` with `staging`, restoring the previous site if the swap fails."""
    previous = previous_dir_for(out_dir)
    _remove(previous)
    if out_dir.exists():
        out_dir.rename(previous)
    try:
        staging.rename(out_dir)
    except BaseException:
        if previous.exists():
            previous.rename(out_dir)
        raise
    _discard(previous)


def _ensure_replaceable(out_dir: Path) -> None:
    if not out_dir.exists():
        return
    if not out_dir.is_dir():
        raise BuildError(f"{out_dir} exists and is not a directory.")
    if any(out_dir.iterdir()) and not (out_dir / BUILD_MARKER).is_file():
        raise BuildError(
            f"{out_dir} is not empty and was not created by `reel build`; refusing to replace it."
        )


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)


def _discard(path: Path) -> None:
    """Best-effort removal of a leftover directory; the next build retries it."""
    shutil.rmtree(path, ignore_errors=True)


def _publish_albums(
    albums: Sequence[Album], cache_dir: Path, images_dir: Path
) -> list[PublishedAlbum]:
    published: list[PublishedAlbum] = []
    for album in albums:
        processed_by_id: dict[str, ProcessedPhoto] = {}
        for photo in album.photos:
            if (processed := _process(album, photo, cache_dir, images_dir)) is not None:
                processed_by_id[photo.file_id] = processed
        photos = list(processed_by_id.values())
        if not photos:
            logger.warning("Album %r has no usable photos; not publishing it.", album.name)
            continue
        cover = None
        if album.cover:
            cover = processed_by_id.get(album.cover.file_id) or _process(
                album, album.cover, cache_dir, images_dir
            )
        published.append(
            PublishedAlbum(
                title=album.title, slug=album.slug, cover=cover or photos[0], photos=photos
            )
        )
    return published


def _process(
    album: Album, photo: Photo, cache_dir: Path, images_dir: Path
) -> ProcessedPhoto | None:
    try:
        source = original_path(cache_dir, photo.file_id)
    except ValueError as error:
        raise BuildError(f"Album {album.name!r}, photo {photo.name!r}: {error}") from error
    if not source.is_file():
        raise BuildError(
            f"Album {album.name!r}, photo {photo.name!r} is missing from {source.parent}. "
            "Run `reel sync` again."
        )
    try:
        return process_photo(source, images_dir)
    except ImageError as error:
        logger.warning("Skipping photo %r in album %r: %s", photo.name, album.name, error)
        return None


def _render_site(
    albums: Sequence[PublishedAlbum], out_dir: Path, site_title: str, base_path: str
) -> None:
    environment = make_environment()
    common = {"site_title": site_title, "base_path": base_path}

    index_html = environment.get_template("index.html").render(
        **common, albums=[_index_entry(album, base_path) for album in albums]
    )
    _write_page(out_dir / "index.html", index_html)
    _write_page(out_dir / "work" / "index.html", index_html)

    album_template = environment.get_template("album.html")
    for index, album in enumerate(albums):
        next_index = next_album_index(index, len(albums))
        next_album = albums[next_index] if next_index is not None else None
        html = album_template.render(
            **common,
            album=_album_context(album, base_path),
            next_album={"title": next_album.title, "slug": next_album.slug} if next_album else None,
        )
        _write_page(out_dir / album.slug / "index.html", html)


def _index_entry(album: PublishedAlbum, base_path: str) -> dict[str, object]:
    thumbnail = album.cover.thumbnail
    return {
        "title": album.title,
        "slug": album.slug,
        "cover_url": image_url(base_path, thumbnail.jpeg_name),
        "cover_webp_url": image_url(base_path, thumbnail.webp_name),
        "cover_width": thumbnail.width,
        "cover_height": thumbnail.height,
    }


def _album_context(album: PublishedAlbum, base_path: str) -> dict[str, object]:
    photos = [
        {
            "webp_url": image_url(base_path, photo.display.webp_name),
            "jpeg_url": image_url(base_path, photo.display.jpeg_name),
            "width": photo.display.width,
            "height": photo.display.height,
        }
        for photo in album.photos
    ]
    return {"title": album.title, "photos": photos}


def _write_page(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
