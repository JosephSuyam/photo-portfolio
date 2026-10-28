"""Incremental sync of the Drive folder tree into `.cache/` plus `manifest.json`.

Originals are downloaded only when Drive reports a new `md5Checksum` or `modifiedTime`.
The manifest is written only after every download succeeded, and stale originals are removed
only after that, so a failed sync leaves the previous manifest (and the site built from it)
untouched.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from portfolio.build import RESERVED_SLUGS
from portfolio.drive import DriveClient, DriveFile
from portfolio.models import Album, Manifest, Photo, TextFile, original_path

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
ABOUT_NAME = "about.json"
CONTACT_NAME = "contact.json"
MANIFEST_NAME = "manifest.json"
ORIGINALS_DIR = "originals"

_DIGITS = re.compile(r"(\d+)")
_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
_FALLBACK_SLUG = "album"
_GOOGLE_APPS_MIME_PREFIX = "application/vnd.google-apps."

type Original = Photo | TextFile


def natural_sort_key(name: str) -> tuple[str | int, ...]:
    """Case-insensitive key that orders digit runs numerically ("img2" before "img10").

    Splitting on digit runs always yields text at even positions and numbers at odd ones,
    so keys of any two names compare without mixing `str` and `int`.
    """
    parts = _DIGITS.split(name.casefold())
    return tuple(int(part) if index % 2 else part for index, part in enumerate(parts))


def display_title(folder_name: str) -> str:
    """Album title: the folder name as written, minus surrounding whitespace.

    A numeric prefix ("01 Book I") still controls the order but is kept in the title.
    """
    return folder_name.strip()


def slugify(title: str) -> str:
    """URL- and path-safe slug: ASCII lowercase letters and digits joined by single hyphens."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG_CHARS.sub("-", ascii_title.lower()).strip("-") or _FALLBACK_SLUG


def unique_slugs(slugs: Sequence[str]) -> list[str]:
    """Make `slugs` unique and unreserved, suffixing later duplicates with -2, -3, ...

    Every input slug counts as taken up front, so a generated suffix never collides with
    a slug that appears later in the list.
    """
    taken = set(RESERVED_SLUGS) | set(slugs)
    used: set[str] = set()
    result: list[str] = []
    for slug in slugs:
        candidate = slug
        if slug in used or slug in RESERVED_SLUGS:
            suffix = 2
            while f"{slug}-{suffix}" in taken:
                suffix += 1
            candidate = f"{slug}-{suffix}"
            taken.add(candidate)
        used.add(candidate)
        result.append(candidate)
    return result


def is_cover(name: str) -> bool:
    """Whether `name` is an album cover file (`cover.<ext>`, any case)."""
    return _stem(name) == "cover"


def _stem(name: str) -> str:
    """`name` without its last extension, casefolded."""
    stem, dot, _ = name.rpartition(".")
    return (stem if dot else name).casefold()


def sync_portfolio(client: DriveClient, root_folder_id: str, cache_dir: Path) -> Manifest:
    """Mirror the Drive portfolio under `root_folder_id` into `cache_dir` and return it.

    Raises `DriveError` if the root is missing or unshared (before anything is listed) or
    if a download fails; in both cases the previous manifest is left as it was.
    """
    # Drive lists an unshared folder as empty, so look the root up first to fail loudly.
    client.get_folder(root_folder_id)
    root_entries = client.list_children(root_folder_id)
    manifest = Manifest(
        albums=_read_albums(client, root_entries),
        about=_find_text_file(root_entries, ABOUT_NAME),
        contact=_find_text_file(root_entries, CONTACT_NAME),
        about_photo=_find_page_photo(root_entries, "about"),
        contact_photo=_find_page_photo(root_entries, "contact"),
    )
    originals = _manifest_originals(manifest)

    manifest_path = cache_dir / MANIFEST_NAME
    downloaded, reused = _download_originals(
        client, originals, _previous_originals(manifest_path), cache_dir
    )
    _write_manifest(manifest_path, manifest)
    removed = _remove_unreferenced(cache_dir, {original.file_id for original in originals})

    logger.info(
        "Synced %d albums: %d downloaded, %d reused, %d removed",
        len(manifest.albums),
        downloaded,
        reused,
        removed,
    )
    return manifest


def _drive_order(entry: DriveFile) -> tuple[object, ...]:
    """Natural order, with the exact name and id as tie-breakers.

    Drive's listing order is not stable, and names like "Travel"/"travel" or "01"/"1" tie
    under natural order; without a tie-breaker slugs and covers could change between syncs.
    """
    return (natural_sort_key(entry.name), entry.name, entry.id)


def _read_albums(client: DriveClient, root_entries: Sequence[DriveFile]) -> list[Album]:
    folders = sorted((entry for entry in root_entries if entry.is_folder), key=_drive_order)
    contents = [(folder, *_read_photos(client, folder)) for folder in folders]
    published = [(folder, photos, cover) for folder, photos, cover in contents if photos]
    titles = [display_title(folder.name) for folder, _, _ in published]
    slugs = unique_slugs([slugify(title) for title in titles])
    return [
        Album(
            folder_id=folder.id,
            name=folder.name,
            title=title,
            slug=slug,
            photos=photos,
            cover=cover,
        )
        for (folder, photos, cover), title, slug in zip(published, titles, slugs, strict=True)
    ]


def _read_photos(client: DriveClient, folder: DriveFile) -> tuple[list[Photo], Photo | None]:
    """The album's photos in order, and its cover file if it has one."""
    files = sorted(
        (entry for entry in client.list_children(folder.id) if _is_usable_photo(entry)),
        key=_drive_order,
    )
    covers = [_to_photo(entry) for entry in files if is_cover(entry.name)]
    photos = [_to_photo(entry) for entry in files if not is_cover(entry.name)]
    for extra in covers[1:]:
        logger.warning(
            "Skipping %r in album %r: album already has a cover", extra.name, folder.name
        )
    return photos, covers[0] if covers else None


def _is_usable_photo(entry: DriveFile) -> bool:
    """Whether `entry` is a supported image; logs why other files are skipped."""
    if entry.is_folder:
        # Albums are one level deep; nested folders are ignored without a warning.
        return False
    if entry.mime_type not in SUPPORTED_MIME_TYPES:
        logger.warning("Skipping %r: unsupported type %s", entry.name, entry.mime_type)
        return False
    try:
        original_path(Path(), entry.id)
    except ValueError:
        logger.warning("Skipping %r: unsafe Drive file ID", entry.name)
        return False
    return True


def _find_text_file(root_entries: Sequence[DriveFile], page_name: str) -> TextFile | None:
    """The root file named `page_name` (any case), or None; warns about unusable ones."""
    matches = sorted(
        (entry for entry in root_entries if entry.name.strip().casefold() == page_name),
        key=_drive_order,
    )
    usable = [entry for entry in matches if _is_usable_page_file(entry)]
    for extra in usable[1:]:
        logger.warning("Skipping %r: using an earlier %s instead", extra.name, page_name)
    if not usable:
        return None
    first = usable[0]
    return TextFile(
        file_id=first.id,
        name=first.name,
        mime_type=first.mime_type,
        md5_checksum=first.md5_checksum,
        modified_time=first.modified_time,
    )


def _find_page_photo(root_entries: Sequence[DriveFile], stem: str) -> Photo | None:
    """The root image named `<stem>.<ext>` (any case), or None; warns about unusable ones.

    Only images and shortcuts are candidates: other root files (the page's .json, an old
    about.txt) stay silent, while an unsupported image type (about.gif) or a shortcut warns.
    """
    candidates = sorted(
        (
            entry
            for entry in root_entries
            if (entry.mime_type.startswith("image/") or entry.is_shortcut)
            and _stem(entry.name) == stem
        ),
        key=_drive_order,
    )
    usable = [entry for entry in candidates if _is_usable_photo(entry)]
    for extra in usable[1:]:
        logger.warning("Skipping %r: using an earlier %s photo instead", extra.name, stem)
    return _to_photo(usable[0]) if usable else None


def _is_usable_page_file(entry: DriveFile) -> bool:
    """Whether `entry` can be downloaded as-is; logs why others are skipped.

    Matching is by name only: Drive labels .json files as application/json, text/plain, or
    application/octet-stream depending on how they were uploaded.
    """
    if entry.is_folder or entry.is_shortcut:
        logger.warning("Skipping %r: not a file", entry.name)
        return False
    if entry.mime_type.startswith(_GOOGLE_APPS_MIME_PREFIX):
        logger.warning(
            "Skipping %r: Google Drive converted it (%s); upload it with conversion turned off",
            entry.name,
            entry.mime_type,
        )
        return False
    try:
        original_path(Path(), entry.id)
    except ValueError:
        logger.warning("Skipping %r: unsafe Drive file ID", entry.name)
        return False
    return True


def _to_photo(entry: DriveFile) -> Photo:
    return Photo(
        file_id=entry.id,
        name=entry.name,
        mime_type=entry.mime_type,
        md5_checksum=entry.md5_checksum,
        modified_time=entry.modified_time,
    )


def _manifest_photos(manifest: Manifest) -> list[Photo]:
    """Every photo and cover in `manifest`, plus the About and Contact photos."""
    photos: list[Photo] = []
    for album in manifest.albums:
        photos.extend(album.photos)
        if album.cover is not None:
            photos.append(album.cover)
    photos.extend(
        photo for photo in (manifest.about_photo, manifest.contact_photo) if photo is not None
    )
    return photos


def _manifest_originals(manifest: Manifest) -> list[Original]:
    """Every file in `manifest` that has an original in the cache."""
    texts = [text for text in (manifest.about, manifest.contact) if text is not None]
    return [*_manifest_photos(manifest), *texts]


def _previous_originals(manifest_path: Path) -> dict[str, Original]:
    """Files from the last successful sync by file ID; empty if there is no usable manifest."""
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        logger.warning("Ignoring unreadable %s: %s", manifest_path, error)
        return {}
    try:
        previous = Manifest.model_validate_json(text)
    except ValueError:
        # Includes pydantic's ValidationError; a bad manifest just means a full download.
        logger.warning("Ignoring invalid %s; downloading every file again", manifest_path)
        return {}
    return {original.file_id: original for original in _manifest_originals(previous)}


def _is_current(original: Original, previous: Original | None, dest: Path) -> bool:
    return (
        previous is not None
        and previous.md5_checksum == original.md5_checksum
        and previous.modified_time == original.modified_time
        and dest.is_file()
    )


def _download_originals(
    client: DriveClient,
    originals: Iterable[Original],
    previous: dict[str, Original],
    cache_dir: Path,
) -> tuple[int, int]:
    """Download new or changed originals; return (downloaded, reused) counts."""
    downloaded = reused = 0
    seen: set[str] = set()
    for original in originals:
        if original.file_id in seen:
            continue
        seen.add(original.file_id)
        dest = original_path(cache_dir, original.file_id)
        if _is_current(original, previous.get(original.file_id), dest):
            reused += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        client.download(original.file_id, dest)
        downloaded += 1
    return downloaded, reused


def _remove_unreferenced(cache_dir: Path, referenced_ids: set[str]) -> int:
    """Delete cached originals (and leftover `.part` files) no longer in Drive.

    Runs after the new manifest is written, so a file that can't be removed (e.g. locked on
    Windows) is only left behind, never needed; the next sync retries it.
    """
    originals = cache_dir / ORIGINALS_DIR
    if not originals.is_dir():
        return 0
    removed = 0
    for path in originals.iterdir():
        if not path.is_file() or path.name in referenced_ids:
            continue
        try:
            path.unlink()
        except OSError as error:
            logger.warning("Could not remove stale original %s: %s", path.name, error)
            continue
        removed += 1
    return removed


def _write_manifest(manifest_path: Path, manifest: Manifest) -> None:
    """Write via a temp file and rename so readers never see a half-written manifest."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_name(f"{manifest_path.name}.tmp")
    try:
        temp_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(manifest_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
