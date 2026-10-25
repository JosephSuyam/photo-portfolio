"""Render the manifest into static HTML in `dist/` with Jinja2.

The site is built into a staging directory next to the output and swapped into place
only when every page and image was written, so a failed build leaves the previous
site untouched. Output directories not created by `reel build` are never overwritten.
"""

import logging
import math
import re
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import ValidationError

from reel.images import ImageError, ImageVariant, ProcessedPhoto, process_photo
from reel.models import Album, Manifest, Photo, TextFile, original_path
from reel.pages import AboutPage, ContactPage, parse_about, parse_contact, read_page_text

logger = logging.getLogger(__name__)

RESERVED_SLUGS = frozenset({"work", "static", "images", "about", "contact"})
BUILD_MARKER = ".reel-build"
IMAGES_DIR = "images"
STATIC_DIR = Path(__file__).parent / "static"

MOBILE_MAX_WIDTH_PX = 767

# Album index: the first album in a wide feature card, the rest in a 12-column grid of cards
# that all share one height; keep in sync with site.css.
FEATURE_WIDTH_VW = 66
FEATURE_ASPECT = Fraction(16, 9)
GRID_COLUMNS = 12
CARDS_PER_ROW = 4
# Span of each card in the last row(s) by the number of cards left after full rows.
LAST_ROW_SPANS = {1: (4, 4, 4, 6, 6), 2: (6, 6), 3: (4, 4, 4)}

# Album mosaic on a 4-column grid of square cells; keep in sync with site.css.
# Each 4-photo group fills a 4x2 block, alternating sides so the big tile zigzags.
MOSAIC_GROUP_SIZE = 4
MOSAIC_GROUPS = (("big", "small", "small", "wide"), ("wide", "big", "small", "small"))
MOSAIC_REMAINDERS = {
    1: (("full",), ("full",)),
    2: (("big", "big"), ("big", "big")),
    3: (("big", "wide", "wide"), ("wide", "big", "wide")),
}
# Shape -> (tile width in vw on desktop, tile width / height).
MOSAIC_TILES = {"small": (25, 1), "wide": (50, 2), "big": (50, 1), "full": (100, 2)}

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
    # Percent-encode so a space or comma in the path can't split a `srcset` candidate.
    path = quote(unquote(urlparse(url).path).strip("/"))
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


def srcset(candidates: Iterable[tuple[str, int]]) -> str:
    """`srcset` value from (url, pixel width) pairs, dropping repeated URLs."""
    seen: dict[str, int] = {}
    for url, width in candidates:
        seen.setdefault(url, width)
    return ", ".join(f"{url} {width}w" for url, width in seen.items())


def cover_sizes(variant: ImageVariant, width_vw: int | Fraction, box_aspect: Fraction) -> str:
    """`sizes` value for a photo cropped to fill a box `width_vw` wide; full width on phones.

    `box_aspect` is the box's width / height. A photo wider than its box is cropped at the
    sides, so it renders wider than the box.
    """
    # Fraction keeps exact multiples exact; floats can push them just past an integer.
    overflow = max(Fraction(1), Fraction(variant.width, variant.height) / box_aspect)
    return f"(max-width: {MOBILE_MAX_WIDTH_PX}px) 100vw, {math.ceil(width_vw * overflow)}vw"


def album_card_spans(count: int) -> list[int]:
    """Grid column span of each of `count` album cards, so every row fills all 12 columns."""
    if count < 0:
        raise ValueError(f"Card count must not be negative, got {count}.")
    if count == 1:
        return [GRID_COLUMNS]
    full_rows, left = divmod(count, CARDS_PER_ROW)
    if left == 1:
        # A lone last card would fill a whole row; regroup the last 5 cards as 3 + 2.
        full_rows -= 1
    full_span = GRID_COLUMNS // CARDS_PER_ROW
    return [full_span] * (full_rows * CARDS_PER_ROW) + list(LAST_ROW_SPANS.get(left, ()))


def card_aspect(span: int) -> Fraction:
    """Width / height of a card spanning `span` columns, ignoring the gaps between columns.

    site.css gives every card frame the same height; this ratio is close enough for `sizes`.
    """
    return Fraction(4, 5) * span / (GRID_COLUMNS // CARDS_PER_ROW)


def photo_count(count: int) -> str:
    """Photo count for display: "1 photo", "2 photos"."""
    return f"{count} photo{'' if count == 1 else 's'}"


def mosaic_shapes(count: int) -> list[str]:
    """Tile shape for each of `count` photos, filling whole 4x2 blocks of the mosaic."""
    if count < 0:
        raise ValueError(f"Photo count must not be negative, got {count}.")
    full_groups, remainder = divmod(count, MOSAIC_GROUP_SIZE)
    shapes = [shape for g in range(full_groups) for shape in MOSAIC_GROUPS[g % 2]]
    if remainder:
        shapes.extend(MOSAIC_REMAINDERS[remainder][full_groups % 2])
    return shapes


def mosaic_sizes(variant: ImageVariant, shape: str) -> str:
    """`sizes` value for a photo cropped to fill a `shape` tile; full width on phones."""
    try:
        tile_width_vw, tile_aspect = MOSAIC_TILES[shape]
    except KeyError:
        raise ValueError(f"Unknown mosaic shape {shape!r}.") from None
    return cover_sizes(variant, tile_width_vw, Fraction(tile_aspect))


def next_album_index(index: int, count: int) -> int | None:
    """Index of the album after `index`, wrapping to the first; None if there is only one."""
    if count < 2:
        return None
    return (index + 1) % count


def previous_album_index(index: int, count: int) -> int | None:
    """Index of the album before `index`, wrapping to the last; None if there is only one."""
    if count < 2:
        return None
    return (index - 1) % count


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
    scripts_dir: Path | None = None,
    contact_form_url: str | None = None,
) -> int:
    """Render `manifest` into `out_dir` and return the number of published albums.

    JavaScript files in `scripts_dir` (compiled from `src/reel/ts/`) are copied to `static/`
    and loaded on every page. Without them the site still works, minus the enhancements.
    About and Contact pages are written only when their text files are usable; the Contact
    page gets a form posting to `contact_form_url` when one is given.
    """
    validate_slugs(manifest.albums)
    about = _load_page(manifest.about, cache_dir, parse_about)
    contact = _load_page(manifest.contact, cache_dir, parse_contact)
    if contact_form_url and contact is None:
        logger.warning(
            "CONTACT_FORM_URL is set but there is no usable contact.txt; the form is not shown."
        )
    scripts = sorted(scripts_dir.glob("*.js")) if scripts_dir else []
    _ensure_replaceable(out_dir)
    staging = staging_dir_for(out_dir)
    try:
        _remove(staging)
        published = _publish_albums(manifest.albums, cache_dir, staging / IMAGES_DIR)
        _render_site(
            published,
            staging,
            site_title,
            base_path,
            [s.name for s in scripts],
            about=about,
            contact=contact,
            contact_form_url=contact_form_url,
        )
        shutil.copytree(STATIC_DIR, staging / "static")
        for script in scripts:
            shutil.copy2(script, staging / "static" / script.name)
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


def _load_page[T](
    text_file: TextFile | None, cache_dir: Path, parse: Callable[[str], T | None]
) -> T | None:
    """Parsed page from the cached text file; None if there is none or it is unusable."""
    if text_file is None:
        return None
    try:
        source = original_path(cache_dir, text_file.file_id)
    except ValueError as error:
        raise BuildError(f"{text_file.name!r}: {error}") from error
    if not source.is_file():
        raise BuildError(
            f"{text_file.name!r} is missing from {source.parent}. Run `reel sync` again."
        )
    try:
        text = read_page_text(source, text_file.name)
    except OSError as error:
        raise BuildError(f"Cannot read {text_file.name!r}: {error}") from error
    return None if text is None else parse(text)


def _render_site(
    albums: Sequence[PublishedAlbum],
    out_dir: Path,
    site_title: str,
    base_path: str,
    script_names: Sequence[str],
    *,
    about: AboutPage | None,
    contact: ContactPage | None,
    contact_form_url: str | None,
) -> None:
    environment = make_environment()
    common = {
        "site_title": site_title,
        "base_path": base_path,
        "script_names": script_names,
        "year": date.today().year,
        "about_page": about is not None,
        "contact_page": contact is not None,
    }

    index_html = environment.get_template("index.html").render(
        **common, **_index_context(albums, base_path)
    )
    _write_page(out_dir / "index.html", index_html)
    _write_page(out_dir / "work" / "index.html", index_html)

    album_template = environment.get_template("album.html")
    for index, album in enumerate(albums):
        previous_index = previous_album_index(index, len(albums))
        next_index = next_album_index(index, len(albums))
        html = album_template.render(
            **common,
            album=_album_context(album, base_path),
            previous_album=_link(albums[previous_index]) if previous_index is not None else None,
            next_album=_link(albums[next_index]) if next_index is not None else None,
        )
        _write_page(out_dir / album.slug / "index.html", html)

    if about is not None:
        html = environment.get_template("about.html").render(**common, about=about)
        _write_page(out_dir / "about" / "index.html", html)
    if contact is not None:
        html = environment.get_template("contact.html").render(
            **common, contact=contact, contact_form_url=contact_form_url
        )
        _write_page(out_dir / "contact" / "index.html", html)


def _link(album: PublishedAlbum) -> dict[str, str]:
    return {"title": album.title, "slug": album.slug}


def _index_context(albums: Sequence[PublishedAlbum], base_path: str) -> dict[str, object]:
    photo_total = sum(len(album.photos) for album in albums)
    feature = None
    if albums:
        first = albums[0]
        feature = {
            **_link(first),
            "count": photo_count(len(first.photos)),
            "cover": _cover_context(first, base_path, FEATURE_WIDTH_VW, FEATURE_ASPECT),
        }
    rest = albums[1:]
    cards = [
        {
            **_link(album),
            "count": photo_count(len(album.photos)),
            "span": span,
            "feature_sizes": cover_sizes(album.cover.display, FEATURE_WIDTH_VW, FEATURE_ASPECT),
            "cover": _cover_context(
                album, base_path, Fraction(100 * span, GRID_COLUMNS), card_aspect(span)
            ),
        }
        for album, span in zip(rest, album_card_spans(len(rest)), strict=True)
    ]
    album_word = "album" if len(albums) == 1 else "albums"
    photo_word = "photograph" if photo_total == 1 else "photographs"
    return {
        "summary": f"{len(albums)} {album_word} · {photo_total} {photo_word}",
        "feature": feature,
        "cards": cards,
    }


def _cover_context(
    album: PublishedAlbum, base_path: str, width_vw: int | Fraction, box_aspect: Fraction
) -> dict[str, object]:
    return _image_context(
        album.cover,
        base_path,
        fallback=album.cover.thumbnail,
        sizes_value=cover_sizes(album.cover.display, width_vw, box_aspect),
    )


def _album_context(album: PublishedAlbum, base_path: str) -> dict[str, object]:
    photos = [
        {
            **_image_context(
                photo,
                base_path,
                fallback=photo.display,
                sizes_value=mosaic_sizes(photo.display, shape),
            ),
            "shape": shape,
            "href": image_url(base_path, photo.display.jpeg_name),
        }
        for photo, shape in zip(album.photos, mosaic_shapes(len(album.photos)), strict=True)
    ]
    return {"title": album.title, "count": photo_count(len(album.photos)), "photos": photos}


def _image_context(
    photo: ProcessedPhoto, base_path: str, fallback: ImageVariant, sizes_value: str
) -> dict[str, object]:
    variants = (photo.thumbnail, photo.display)
    return {
        "src": image_url(base_path, fallback.jpeg_name),
        "webp_srcset": srcset((image_url(base_path, v.webp_name), v.width) for v in variants),
        "jpeg_srcset": srcset((image_url(base_path, v.jpeg_name), v.width) for v in variants),
        "sizes": sizes_value,
        "width": photo.display.width,
        "height": photo.display.height,
    }


def _write_page(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
