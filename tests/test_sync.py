import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reel.build import RESERVED_SLUGS, load_manifest
from reel.drive import SHORTCUT_MIME_TYPE, DriveError
from reel.models import Manifest, original_path
from reel.sync import (
    MANIFEST_NAME,
    SUPPORTED_MIME_TYPES,
    display_title,
    is_cover,
    natural_sort_key,
    slugify,
    sync_portfolio,
    unique_slugs,
)
from tests.fixtures.fake_drive import FakeDriveClient

ROOT = "root"
SLUG_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
LATER = datetime(2025, 6, 1, tzinfo=UTC)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / ".cache"


@pytest.fixture
def drive(fake_drive: FakeDriveClient) -> FakeDriveClient:
    fake_drive.add_root(ROOT)
    return fake_drive


def _sync(drive: FakeDriveClient, cache_dir: Path) -> Manifest:
    return sync_portfolio(drive, ROOT, cache_dir)


def _one_album(drive: FakeDriveClient, *photo_ids: str, name: str = "Book") -> None:
    """Folder `name` (id `f-book`) holding a JPEG per id, named `<id>.jpg`."""
    drive.add_folder(ROOT, "f-book", name)
    for photo_id in photo_ids:
        drive.add_file("f-book", photo_id, f"{photo_id}.jpg", content=f"bytes-{photo_id}".encode())


def _album_names(manifest: Manifest) -> list[str]:
    return [album.name for album in manifest.albums]


def _photo_names(manifest: Manifest) -> list[str]:
    return [photo.name for photo in manifest.albums[0].photos]


def _warned_about(caplog: pytest.LogCaptureFixture, text: str) -> bool:
    return any(
        record.levelno == logging.WARNING and text in record.getMessage()
        for record in caplog.records
    )


# --- constants ---------------------------------------------------------------------------


def test_supported_mime_types_jpeg_png_webp_only() -> None:
    assert frozenset({"image/jpeg", "image/png", "image/webp"}) == SUPPORTED_MIME_TYPES


def test_manifest_name_is_what_build_reads() -> None:
    assert MANIFEST_NAME == "manifest.json"


# --- natural_sort_key --------------------------------------------------------------------


def test_natural_sort_key_album_numbers_sort_numerically() -> None:
    assert sorted(["Book 10", "Book 2", "Book 1"], key=natural_sort_key) == [
        "Book 1",
        "Book 2",
        "Book 10",
    ]


def test_natural_sort_key_filenames_sort_numerically() -> None:
    assert sorted(["img10.jpg", "img2.jpg"], key=natural_sort_key) == ["img2.jpg", "img10.jpg"]


def test_natural_sort_key_case_ignored() -> None:
    assert sorted(["b.jpg", "A.jpg", "C.jpg"], key=natural_sort_key) == ["A.jpg", "b.jpg", "C.jpg"]


def test_natural_sort_key_leading_numbers_sort_numerically() -> None:
    assert sorted(["10 Late", "2 Early"], key=natural_sort_key) == ["2 Early", "10 Late"]


def test_natural_sort_key_later_number_group_compared_numerically() -> None:
    assert sorted(["a1b10", "a1b2"], key=natural_sort_key) == ["a1b2", "a1b10"]


def test_natural_sort_key_digits_and_letters_mixed_does_not_raise() -> None:
    names = ["abc", "10", "x5", "", "5x"]
    assert sorted(sorted(names, key=natural_sort_key)) == sorted(names)


# --- display_title -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "folder_name",
    ["01 Book I", "2-Portraits", "03_Street", "05 - Night", "2020 Trip", "Book 2", "007"],
)
def test_display_title_folder_name_kept_as_written(folder_name: str) -> None:
    assert display_title(folder_name) == folder_name


def test_display_title_surrounding_whitespace_collapsed() -> None:
    assert display_title("  Book I  ") == "Book I"


@pytest.mark.parametrize("folder_name", ["01", "01 ", " 01 - "])
def test_display_title_number_only_name_kept(folder_name: str) -> None:
    assert display_title(folder_name) == folder_name.strip()


# --- slugify -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Book I", "book-i"),
        ("Café Noir!", "cafe-noir"),
        ("../../etc", "etc"),
        ("<script>", "script"),
        ("--a  __  b--", "a-b"),
        ("Book 2", "book-2"),
    ],
)
def test_slugify_title_normalized(title: str, expected: str) -> None:
    assert slugify(title) == expected


@pytest.mark.parametrize("title", ["", "   ", "!!!", "日本"])
def test_slugify_nothing_usable_falls_back_to_album(title: str) -> None:
    assert slugify(title) == "album"


@pytest.mark.parametrize(
    "title",
    ["<img src=x onerror=alert(1)>", "..\\..\\Windows", "a/b/c", "Ünïcödé — Title", "\x00\n\t"],
)
def test_slugify_unsafe_input_matches_slug_pattern(title: str) -> None:
    assert SLUG_PATTERN.fullmatch(slugify(title))


# --- unique_slugs ------------------------------------------------------------------------


def test_unique_slugs_distinct_unchanged() -> None:
    assert unique_slugs(["a", "b"]) == ["a", "b"]


def test_unique_slugs_duplicates_suffixed_in_order() -> None:
    assert unique_slugs(["a", "a", "a"]) == ["a", "a-2", "a-3"]


def test_unique_slugs_empty_returns_empty() -> None:
    assert unique_slugs([]) == []


@pytest.mark.parametrize("reserved", sorted(RESERVED_SLUGS))
def test_unique_slugs_reserved_slug_suffixed(reserved: str) -> None:
    assert unique_slugs([reserved]) == [f"{reserved}-2"]


def test_unique_slugs_suffix_colliding_with_existing_slug_still_unique() -> None:
    result = unique_slugs(["a-2", "a", "a"])
    assert len(set(result)) == 3


def test_unique_slugs_repeated_reserved_never_reserved_or_duplicated() -> None:
    result = unique_slugs(["work", "work", "work-2"])
    assert len(set(result)) == 3 and not set(result) & RESERVED_SLUGS


# --- is_cover ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["cover.jpg", "Cover.JPG", "COVER.webp", "cover.png"])
def test_is_cover_stem_cover_true(name: str) -> None:
    assert is_cover(name)


@pytest.mark.parametrize(
    "name", ["cover-2.jpg", "my cover.jpg", "discover.jpg", "cover.backup.jpg", "covers.jpg"]
)
def test_is_cover_other_stem_false(name: str) -> None:
    assert not is_cover(name)


# --- sync_portfolio: root lookup ---------------------------------------------------------


def test_sync_portfolio_root_looked_up_before_listing(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    assert drive.calls[0] == ("get_folder", ROOT)


def test_sync_portfolio_unshared_root_raises_drive_error(
    fake_drive: FakeDriveClient, cache_dir: Path
) -> None:
    with pytest.raises(DriveError, match="shared with the service account"):
        sync_portfolio(fake_drive, "unshared", cache_dir)


def test_sync_portfolio_unshared_root_lists_nothing(
    fake_drive: FakeDriveClient, cache_dir: Path
) -> None:
    fake_drive.add_folder("unshared", "f-book", "Book")
    with pytest.raises(DriveError):
        sync_portfolio(fake_drive, "unshared", cache_dir)
    assert fake_drive.listed == []


def test_sync_portfolio_unshared_root_writes_no_manifest(
    fake_drive: FakeDriveClient, cache_dir: Path
) -> None:
    with pytest.raises(DriveError):
        sync_portfolio(fake_drive, "unshared", cache_dir)
    assert not (cache_dir / "manifest.json").exists()


# --- sync_portfolio: albums --------------------------------------------------------------


def test_sync_portfolio_empty_root_returns_no_albums(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    assert _sync(drive, cache_dir).albums == []


def test_sync_portfolio_album_has_folder_id_name_title_and_slug(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-book", "01 Book I")
    drive.add_file("f-book", "p1", "a.jpg")
    album = _sync(drive, cache_dir).albums[0]
    assert (album.folder_id, album.name, album.title, album.slug) == (
        "f-book",
        "01 Book I",
        "01 Book I",
        "01-book-i",
    )


def test_sync_portfolio_albums_natural_sorted_by_folder_name(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    for index, name in enumerate(["Book 10", "Book 2", "book 1"]):
        drive.add_folder(ROOT, f"f{index}", name)
        drive.add_file(f"f{index}", f"p{index}", "a.jpg")
    assert _album_names(_sync(drive, cache_dir)) == ["book 1", "Book 2", "Book 10"]


def test_sync_portfolio_numeric_prefix_forces_album_order(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    for index, name in enumerate(["10 Mid", "Aardvark", "02 Alpha", "01 Zeta", "3 Beta"]):
        drive.add_folder(ROOT, f"f{index}", name)
        drive.add_file(f"f{index}", f"p{index}", "a.jpg")
    titles = [album.title for album in _sync(drive, cache_dir).albums]
    assert titles == ["01 Zeta", "02 Alpha", "3 Beta", "10 Mid", "Aardvark"]


def test_sync_portfolio_files_at_root_not_albums(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_file(ROOT, "stray", "stray.jpg")
    assert _album_names(_sync(drive, cache_dir)) == ["Book"]


def test_sync_portfolio_files_at_root_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file(ROOT, "stray", "stray.jpg")
    _sync(drive, cache_dir)
    assert "stray" not in drive.downloads


def test_sync_portfolio_nested_subfolder_not_listed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_folder("f-book", "f-nested", "Outtakes")
    drive.add_file("f-nested", "deep", "deep.jpg")
    _sync(drive, cache_dir)
    assert "f-nested" not in drive.listed


def test_sync_portfolio_nested_subfolder_photos_not_in_album(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_folder("f-book", "f-nested", "Outtakes")
    drive.add_file("f-nested", "deep", "deep.jpg")
    assert _photo_names(_sync(drive, cache_dir)) == ["p1.jpg"]


def test_sync_portfolio_empty_album_not_published(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_folder(ROOT, "f-empty", "Empty")
    assert _album_names(_sync(drive, cache_dir)) == ["Book"]


def test_sync_portfolio_album_with_only_unsupported_files_not_published(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-docs", "Docs")
    drive.add_file("f-docs", "d1", "notes.pdf", mime_type="application/pdf")
    assert _sync(drive, cache_dir).albums == []


def test_sync_portfolio_album_with_only_cover_not_published(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-book", "Book")
    drive.add_file("f-book", "c1", "cover.jpg")
    assert _sync(drive, cache_dir).albums == []


def test_sync_portfolio_duplicate_titles_get_unique_slugs(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    for index, name in enumerate(["Travel", "travel", "Travel!"]):
        drive.add_folder(ROOT, f"f{index}", name)
        drive.add_file(f"f{index}", f"p{index}", "a.jpg")
    slugs = [album.slug for album in _sync(drive, cache_dir).albums]
    assert slugs == ["travel", "travel-2", "travel-3"]


def test_sync_portfolio_reserved_album_name_slug_suffixed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", name="Work")
    assert _sync(drive, cache_dir).albums[0].slug == "work-2"


@pytest.mark.parametrize(
    "name", ["../../etc", "<script>alert(1)</script>", "..\\..\\Windows", "日本", "   "]
)
def test_sync_portfolio_unsafe_album_name_gets_safe_slug(
    drive: FakeDriveClient, cache_dir: Path, name: str
) -> None:
    _one_album(drive, "p1", name=name)
    assert SLUG_PATTERN.fullmatch(_sync(drive, cache_dir).albums[0].slug)


def test_sync_portfolio_path_traversal_album_name_writes_only_inside_cache(
    drive: FakeDriveClient, cache_dir: Path, tmp_path: Path
) -> None:
    _one_album(drive, "p1", name="../../outside")
    _sync(drive, cache_dir)
    assert list(tmp_path.iterdir()) == [cache_dir]


def test_sync_portfolio_html_album_name_kept_raw_for_escaping_at_build(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", name="<b>Book</b>")
    assert _sync(drive, cache_dir).albums[0].name == "<b>Book</b>"


# --- sync_portfolio: photos --------------------------------------------------------------


def test_sync_portfolio_photos_natural_sorted_by_filename(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-book", "Book")
    for index, name in enumerate(["img10.jpg", "img2.jpg", "IMG1.jpg"]):
        drive.add_file("f-book", f"p{index}", name)
    assert _photo_names(_sync(drive, cache_dir)) == ["IMG1.jpg", "img2.jpg", "img10.jpg"]


@pytest.mark.parametrize("mime_type", ["image/jpeg", "image/png", "image/webp"])
def test_sync_portfolio_supported_type_included(
    drive: FakeDriveClient, cache_dir: Path, mime_type: str
) -> None:
    drive.add_folder(ROOT, "f-book", "Book")
    drive.add_file("f-book", "p1", "a.img", mime_type=mime_type)
    assert _photo_names(_sync(drive, cache_dir)) == ["a.img"]


def test_sync_portfolio_photo_metadata_copied_from_drive(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-book", "Book")
    drive.add_file(
        "f-book", "p1", "a.png", mime_type="image/png", md5_checksum="abc", modified_time=LATER
    )
    photo = _sync(drive, cache_dir).albums[0].photos[0]
    assert (photo.file_id, photo.mime_type, photo.md5_checksum, photo.modified_time) == (
        "p1",
        "image/png",
        "abc",
        LATER,
    )


@pytest.mark.parametrize(
    ("name", "mime_type"),
    [
        ("clip.mp4", "video/mp4"),
        ("notes", "application/vnd.google-apps.document"),
        ("photo.heic", "image/heic"),
        ("fake.jpg", "application/pdf"),
        ("link.jpg", SHORTCUT_MIME_TYPE),
    ],
)
def test_sync_portfolio_unsupported_file_skipped(
    drive: FakeDriveClient, cache_dir: Path, name: str, mime_type: str
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "x1", name, mime_type=mime_type)
    assert _photo_names(_sync(drive, cache_dir)) == ["p1.jpg"]


@pytest.mark.parametrize(
    ("name", "mime_type"),
    [("clip.mp4", "video/mp4"), ("link.jpg", SHORTCUT_MIME_TYPE)],
)
def test_sync_portfolio_unsupported_file_logs_warning_with_name(
    drive: FakeDriveClient,
    cache_dir: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
    mime_type: str,
) -> None:
    caplog.set_level(logging.WARNING)
    _one_album(drive, "p1")
    drive.add_file("f-book", "x1", name, mime_type=mime_type)
    _sync(drive, cache_dir)
    assert _warned_about(caplog, name)


def test_sync_portfolio_unsupported_file_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "x1", "link.jpg", mime_type=SHORTCUT_MIME_TYPE)
    _sync(drive, cache_dir)
    assert drive.downloads == ["p1"]


def test_sync_portfolio_unsafe_file_id_photo_skipped(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "../evil", "evil.jpg")
    assert _photo_names(_sync(drive, cache_dir)) == ["p1.jpg"]


def test_sync_portfolio_unsafe_file_id_logs_warning_with_name(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _one_album(drive, "p1")
    drive.add_file("f-book", "../evil", "evil.jpg")
    _sync(drive, cache_dir)
    assert _warned_about(caplog, "evil.jpg")


def test_sync_portfolio_unsafe_file_id_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "../evil", "evil.jpg")
    _sync(drive, cache_dir)
    assert "../evil" not in drive.downloads


# --- sync_portfolio: cover ---------------------------------------------------------------


def test_sync_portfolio_cover_file_becomes_album_cover(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "Cover.JPG")
    cover = _sync(drive, cache_dir).albums[0].cover
    assert cover is not None and cover.file_id == "c1"


def test_sync_portfolio_cover_file_excluded_from_photos(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg")
    assert _photo_names(_sync(drive, cache_dir)) == ["p1.jpg"]


def test_sync_portfolio_cover_file_downloaded(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg", content=b"cover-bytes")
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "c1").read_bytes() == b"cover-bytes"


def test_sync_portfolio_no_cover_file_cover_is_none(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    assert _sync(drive, cache_dir).albums[0].cover is None


def test_sync_portfolio_cover_like_name_is_a_photo(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover-2.jpg")
    assert _sync(drive, cache_dir).albums[0].cover is None


def test_sync_portfolio_unsupported_cover_type_ignored(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.pdf", mime_type="application/pdf")
    assert _sync(drive, cache_dir).albums[0].cover is None


def test_sync_portfolio_cover_shortcut_ignored(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg", mime_type=SHORTCUT_MIME_TYPE)
    assert _sync(drive, cache_dir).albums[0].cover is None


def test_sync_portfolio_unsafe_cover_id_ignored(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "../cover", "cover.jpg")
    assert _sync(drive, cache_dir).albums[0].cover is None


# --- sync_portfolio: downloads and manifest ----------------------------------------------


def test_sync_portfolio_missing_cache_dir_created_and_photo_downloaded(
    drive: FakeDriveClient, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "deep" / "cache"
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "p1").read_bytes() == b"bytes-p1"


def test_sync_portfolio_writes_manifest_loadable_by_build(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    manifest = _sync(drive, cache_dir)
    assert load_manifest(cache_dir / "manifest.json") == manifest


def test_sync_portfolio_empty_root_writes_empty_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _sync(drive, cache_dir)
    assert load_manifest(cache_dir / "manifest.json").albums == []


def test_sync_portfolio_first_sync_downloads_every_photo(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    assert sorted(drive.downloads) == ["p1", "p2"]


# --- sync_portfolio: incremental ---------------------------------------------------------


def test_sync_portfolio_unchanged_photo_not_downloaded_again(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    _sync(drive, cache_dir)
    assert drive.downloads == []


def test_sync_portfolio_unchanged_photo_original_kept(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "p1").read_bytes() == b"bytes-p1"


def test_sync_portfolio_unchanged_cover_not_downloaded_again(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    _sync(drive, cache_dir)
    assert "c1" not in drive.downloads


def test_sync_portfolio_md5_changed_redownloaded(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    drive.update_file("p1", content=b"edited", md5_checksum="new-md5")
    _sync(drive, cache_dir)
    assert drive.downloads == ["p1"]


def test_sync_portfolio_md5_changed_original_replaced(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    drive.update_file("p1", content=b"edited", md5_checksum="new-md5")
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "p1").read_bytes() == b"edited"


def test_sync_portfolio_modified_time_changed_redownloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    drive.update_file("p2", modified_time=LATER)
    _sync(drive, cache_dir)
    assert drive.downloads == ["p2"]


def test_sync_portfolio_original_missing_locally_redownloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    original_path(cache_dir, "p1").unlink()
    _sync(drive, cache_dir)
    assert drive.downloads == ["p1"]


def test_sync_portfolio_photo_moved_between_albums_not_downloaded_again(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    drive.add_folder(ROOT, "f-other", "Other")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    drive.remove("p2")
    drive.add_file("f-other", "p2", "p2.jpg", content=b"bytes-p2")
    _sync(drive, cache_dir)
    assert drive.downloads == []


@pytest.mark.parametrize("previous", ["", "{not json", '{"albums": 5}', "[]"])
def test_sync_portfolio_corrupt_previous_manifest_downloads_everything(
    drive: FakeDriveClient, cache_dir: Path, previous: str
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    (cache_dir / "manifest.json").write_text(previous, encoding="utf-8")
    _sync(drive, cache_dir)
    assert drive.downloads == ["p1"]


def test_sync_portfolio_corrupt_previous_manifest_replaced_with_valid_one(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    cache_dir.mkdir()
    (cache_dir / "manifest.json").write_text("{not json", encoding="utf-8")
    manifest = _sync(drive, cache_dir)
    assert load_manifest(cache_dir / "manifest.json") == manifest


def test_sync_portfolio_original_without_previous_manifest_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    stale = original_path(cache_dir, "p1")
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    _sync(drive, cache_dir)
    assert stale.read_bytes() == b"bytes-p1"


# --- sync_portfolio: cleanup -------------------------------------------------------------


def test_sync_portfolio_photo_deleted_in_drive_original_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.remove("p2")
    _sync(drive, cache_dir)
    assert not original_path(cache_dir, "p2").exists()


def test_sync_portfolio_photo_deleted_in_drive_dropped_from_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.remove("p2")
    assert _photo_names(_sync(drive, cache_dir)) == ["p1.jpg"]


def test_sync_portfolio_album_deleted_in_drive_originals_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_folder(ROOT, "f-gone", "Gone")
    drive.add_file("f-gone", "g1", "g1.jpg")
    _sync(drive, cache_dir)
    drive.remove("f-gone")
    _sync(drive, cache_dir)
    assert not original_path(cache_dir, "g1").exists()


def test_sync_portfolio_cover_deleted_in_drive_original_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg")
    _sync(drive, cache_dir)
    drive.remove("c1")
    _sync(drive, cache_dir)
    assert not original_path(cache_dir, "c1").exists()


def test_sync_portfolio_stray_files_in_originals_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    originals = cache_dir / "originals"
    originals.mkdir(parents=True)
    (originals / "orphan").write_bytes(b"x")
    (originals / "p1.part").write_bytes(b"half")
    _sync(drive, cache_dir)
    assert sorted(path.name for path in originals.iterdir()) == ["p1"]


def test_sync_portfolio_album_emptied_in_drive_originals_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file("f-book", "c1", "cover.jpg")
    _sync(drive, cache_dir)
    drive.remove("p1")
    _sync(drive, cache_dir)
    assert not original_path(cache_dir, "c1").exists()


# --- sync_portfolio: download failure ----------------------------------------------------


def test_sync_portfolio_download_failure_raises(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    drive.failing_downloads.add("p1")
    with pytest.raises(DriveError):
        _sync(drive, cache_dir)


def test_sync_portfolio_download_failure_keeps_previous_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    before = (cache_dir / "manifest.json").read_bytes()
    drive.update_file("p2", md5_checksum="new-md5")
    drive.failing_downloads.add("p2")
    with pytest.raises(DriveError):
        _sync(drive, cache_dir)
    assert (cache_dir / "manifest.json").read_bytes() == before


def test_sync_portfolio_download_failure_on_first_sync_writes_no_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.failing_downloads.add("p1")
    with pytest.raises(DriveError):
        _sync(drive, cache_dir)
    assert not (cache_dir / "manifest.json").exists()


def test_sync_portfolio_case_only_name_tie_slugs_stable_across_listing_order(
    tmp_path: Path,
) -> None:
    slugs = []
    for order in (["a", "b"], ["b", "a"]):
        drive = FakeDriveClient()
        drive.add_root(ROOT)
        names = {"a": "Travel", "b": "travel"}
        for folder_id in order:
            drive.add_folder(ROOT, folder_id, names[folder_id])
            drive.add_file(folder_id, f"{folder_id}-p", "1.jpg", content=b"x")
        manifest = sync_portfolio(drive, ROOT, tmp_path / "-".join(order))
        slugs.append({album.folder_id: album.slug for album in manifest.albums})
    assert slugs[0] == slugs[1]


def test_sync_portfolio_manifest_write_failure_keeps_previous_originals(
    drive: FakeDriveClient, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.remove("p2")

    def failing_replace(self: Path, target: Path) -> Path:
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", failing_replace)
    with pytest.raises(PermissionError):
        _sync(drive, cache_dir)
    assert original_path(cache_dir, "p2").exists()


def test_sync_portfolio_locked_stale_original_logs_warning_and_succeeds(
    drive: FakeDriveClient,
    cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _one_album(drive, "p1", "p2")
    _sync(drive, cache_dir)
    drive.remove("p2")
    original_unlink = Path.unlink

    def failing_unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "p2":
            raise PermissionError("locked")
        original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    with caplog.at_level(logging.WARNING):
        _sync(drive, cache_dir)
    assert _warned_about(caplog, "p2")


# --- sync_portfolio: about.json and contact.json in the root -------------------------------


def _root_text(
    drive: FakeDriveClient,
    file_id: str,
    name: str,
    content: bytes | None = None,
    mime_type: str = "application/json",
) -> None:
    drive.add_file(
        ROOT, file_id, name, content=content or f"json-{file_id}".encode(), mime_type=mime_type
    )


def _about_id(manifest: Manifest) -> str | None:
    return manifest.about.file_id if manifest.about else None


def _contact_id(manifest: Manifest) -> str | None:
    return manifest.contact.file_id if manifest.contact else None


def test_sync_portfolio_no_text_files_about_is_none(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    assert _sync(drive, cache_dir).about is None


def test_sync_portfolio_no_text_files_contact_is_none(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    assert _sync(drive, cache_dir).contact is None


def test_sync_portfolio_about_json_in_root_recorded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    assert _about_id(_sync(drive, cache_dir)) == "t-about"


def test_sync_portfolio_contact_json_in_root_recorded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-contact", "contact.json")
    assert _contact_id(_sync(drive, cache_dir)) == "t-contact"


def test_sync_portfolio_about_and_contact_not_swapped(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-contact", "contact.json")
    _root_text(drive, "t-about", "about.json")
    manifest = _sync(drive, cache_dir)
    assert (_about_id(manifest), _contact_id(manifest)) == ("t-about", "t-contact")


def test_sync_portfolio_text_file_metadata_copied_from_drive(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_file(
        ROOT,
        "t-about",
        "About.json",
        mime_type="application/json",
        md5_checksum="abc",
        modified_time=LATER,
    )
    about = _sync(drive, cache_dir).about
    assert about is not None and (
        about.file_id,
        about.name,
        about.mime_type,
        about.md5_checksum,
        about.modified_time,
    ) == ("t-about", "About.json", "application/json", "abc", LATER)


@pytest.mark.parametrize("name", ["About.json", "ABOUT.JSON", "aBoUt.JsOn", "  about.json  "])
def test_sync_portfolio_about_name_matched_case_and_space_insensitive(
    drive: FakeDriveClient, cache_dir: Path, name: str
) -> None:
    _root_text(drive, "t-about", name)
    assert _about_id(_sync(drive, cache_dir)) == "t-about"


@pytest.mark.parametrize("name", ["Contact.json", "CONTACT.JSON", " contact.json"])
def test_sync_portfolio_contact_name_matched_case_and_space_insensitive(
    drive: FakeDriveClient, cache_dir: Path, name: str
) -> None:
    _root_text(drive, "t-contact", name)
    assert _contact_id(_sync(drive, cache_dir)) == "t-contact"


@pytest.mark.parametrize(
    "name",
    ["about.txt", "about", "about.json.txt", "about.json.bak", "my about.json", "about .json"],
)
def test_sync_portfolio_other_about_like_name_ignored(
    drive: FakeDriveClient, cache_dir: Path, name: str
) -> None:
    _root_text(drive, "t-about", name)
    assert _sync(drive, cache_dir).about is None


@pytest.mark.parametrize("name", ["about.txt", "contact.txt", "notes.json", "contact.json.bak"])
def test_sync_portfolio_other_root_file_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path, name: str
) -> None:
    _root_text(drive, "t-other", name, mime_type="text/plain")
    _sync(drive, cache_dir)
    assert "t-other" not in drive.downloads


@pytest.mark.parametrize("name", ["about.txt", "contact.txt", "notes.json"])
def test_sync_portfolio_other_root_file_logs_no_warning(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture, name: str
) -> None:
    caplog.set_level(logging.WARNING)
    _root_text(drive, "t-other", name, mime_type="text/plain")
    _sync(drive, cache_dir)
    assert [
        record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
    ] == []


def test_sync_portfolio_old_about_txt_ignored_beside_about_json(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-old", "about.txt", mime_type="text/plain")
    _root_text(drive, "t-about", "about.json")
    assert _about_id(_sync(drive, cache_dir)) == "t-about"


@pytest.mark.parametrize(
    "mime_type",
    ["application/json", "text/plain", "application/octet-stream", "text/x-json"],
)
def test_sync_portfolio_about_matched_by_name_whatever_drive_type(
    drive: FakeDriveClient, cache_dir: Path, mime_type: str
) -> None:
    _root_text(drive, "t-about", "about.json", mime_type=mime_type)
    assert _about_id(_sync(drive, cache_dir)) == "t-about"


@pytest.mark.parametrize("mime_type", ["application/json", "application/octet-stream"])
def test_sync_portfolio_contact_matched_by_name_downloaded(
    drive: FakeDriveClient, cache_dir: Path, mime_type: str
) -> None:
    _root_text(drive, "t-contact", "contact.json", mime_type=mime_type)
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-contact"]


@pytest.mark.parametrize(
    "mime_type",
    [
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        SHORTCUT_MIME_TYPE,
    ],
)
def test_sync_portfolio_about_google_apps_or_shortcut_skipped(
    drive: FakeDriveClient, cache_dir: Path, mime_type: str
) -> None:
    _root_text(drive, "t-about", "about.json", mime_type=mime_type)
    assert _sync(drive, cache_dir).about is None


def test_sync_portfolio_converted_google_doc_warns_with_type(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _root_text(drive, "t-contact", "Contact.json", mime_type="application/vnd.google-apps.document")
    _sync(drive, cache_dir)
    assert _warned_about(
        caplog,
        "Skipping 'Contact.json': Google Drive converted it (application/vnd.google-apps.document);"
        " upload it with conversion turned off",
    )


def test_sync_portfolio_converted_google_doc_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json", mime_type="application/vnd.google-apps.document")
    _sync(drive, cache_dir)
    assert drive.downloads == []


def test_sync_portfolio_shortcut_named_like_page_warns_not_a_file(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _root_text(drive, "t-contact", "Contact.json", mime_type=SHORTCUT_MIME_TYPE)
    _sync(drive, cache_dir)
    assert _warned_about(caplog, "Skipping 'Contact.json': not a file")


def test_sync_portfolio_folder_named_about_json_not_a_page(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-about", "about.json")
    drive.add_file("f-about", "p1", "p1.jpg")
    assert _sync(drive, cache_dir).about is None


def test_sync_portfolio_folder_named_about_json_stays_an_album(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    drive.add_folder(ROOT, "f-about", "about.json")
    drive.add_file("f-about", "p1", "p1.jpg")
    assert _album_names(_sync(drive, cache_dir)) == ["about.json"]


def test_sync_portfolio_converted_duplicate_does_not_hide_usable_file(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-doc", "About.json", mime_type="application/vnd.google-apps.document")
    _root_text(drive, "t-file", "about.json")
    assert _about_id(_sync(drive, cache_dir)) == "t-file"


def test_sync_portfolio_unsafe_text_file_id_skipped(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "../about", "about.json")
    assert _sync(drive, cache_dir).about is None


def test_sync_portfolio_unsafe_text_file_id_warns_with_name(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _root_text(drive, "../about", "about.json")
    _sync(drive, cache_dir)
    assert _warned_about(caplog, "Skipping 'about.json'")


def test_sync_portfolio_unsafe_text_file_id_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "../about", "about.json")
    _sync(drive, cache_dir)
    assert drive.downloads == []


def test_sync_portfolio_duplicate_about_case_variant_first_in_natural_order_wins(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-lower", "about.json")
    _root_text(drive, "t-upper", "About.json")
    assert _about_id(_sync(drive, cache_dir)) == "t-upper"


def test_sync_portfolio_duplicate_about_same_name_lowest_id_wins(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-b", "about.json")
    _root_text(drive, "t-a", "about.json")
    assert _about_id(_sync(drive, cache_dir)) == "t-a"


def test_sync_portfolio_duplicate_about_warns_about_extra(
    drive: FakeDriveClient, cache_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _root_text(drive, "t-lower", "about.json")
    _root_text(drive, "t-upper", "About.json")
    _sync(drive, cache_dir)
    assert _warned_about(caplog, "Skipping 'about.json': using an earlier about.json instead")


def test_sync_portfolio_duplicate_contact_extra_not_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-b", "contact.json")
    _root_text(drive, "t-a", "CONTACT.json")
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-a"]


def test_sync_portfolio_text_file_downloaded_to_originals(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json", content=b"Hello there.")
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "t-about").read_bytes() == b"Hello there."


def test_sync_portfolio_text_files_recorded_in_written_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _root_text(drive, "t-about", "about.json")
    _root_text(drive, "t-contact", "contact.json")
    manifest = _sync(drive, cache_dir)
    assert load_manifest(cache_dir / "manifest.json") == manifest


def test_sync_portfolio_text_files_need_no_extra_listing(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _root_text(drive, "t-about", "about.json")
    _root_text(drive, "t-contact", "contact.json")
    _sync(drive, cache_dir)
    assert drive.listed == [ROOT, "f-book"]


def test_sync_portfolio_text_files_root_still_looked_up_first(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    assert drive.calls[0] == ("get_folder", ROOT)


def test_sync_portfolio_stray_root_image_still_not_downloaded_beside_text_files(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    drive.add_file(ROOT, "stray", "stray.jpg")
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    assert "stray" not in drive.downloads


def test_sync_portfolio_text_files_not_albums(drive: FakeDriveClient, cache_dir: Path) -> None:
    _one_album(drive, "p1")
    _root_text(drive, "t-about", "about.json")
    assert _album_names(_sync(drive, cache_dir)) == ["Book"]


def test_sync_portfolio_text_file_original_kept_after_sync(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "t-about").is_file()


def test_sync_portfolio_unchanged_text_file_not_downloaded_again(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _root_text(drive, "t-contact", "contact.json")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    _sync(drive, cache_dir)
    assert drive.downloads == []


def test_sync_portfolio_text_file_md5_changed_redownloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _root_text(drive, "t-contact", "contact.json")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    drive.update_file("t-about", content=b"New bio.", md5_checksum="new-md5")
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-about"]


def test_sync_portfolio_text_file_md5_changed_original_replaced(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    drive.update_file("t-about", content=b"New bio.", md5_checksum="new-md5")
    _sync(drive, cache_dir)
    assert original_path(cache_dir, "t-about").read_bytes() == b"New bio."


def test_sync_portfolio_text_file_modified_time_changed_redownloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _root_text(drive, "t-contact", "contact.json")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    drive.update_file("t-contact", modified_time=LATER)
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-contact"]


def test_sync_portfolio_text_file_missing_locally_redownloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    drive.downloads.clear()
    original_path(cache_dir, "t-about").unlink()
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-about"]


def test_sync_portfolio_text_file_after_old_manifest_downloaded(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _sync(drive, cache_dir)
    manifest_path = cache_dir / "manifest.json"
    albums_only = {"albums": json.loads(manifest_path.read_text(encoding="utf-8"))["albums"]}
    manifest_path.write_text(json.dumps(albums_only), encoding="utf-8")
    drive.downloads.clear()
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    assert drive.downloads == ["t-about"]


def test_sync_portfolio_text_file_deleted_in_drive_original_removed(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    drive.remove("t-about")
    _sync(drive, cache_dir)
    assert not original_path(cache_dir, "t-about").exists()


def test_sync_portfolio_text_file_deleted_in_drive_dropped_from_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _root_text(drive, "t-contact", "contact.json")
    _sync(drive, cache_dir)
    drive.remove("t-contact")
    _sync(drive, cache_dir)
    assert load_manifest(cache_dir / "manifest.json").contact is None


def test_sync_portfolio_text_file_deleted_but_manifest_write_fails_original_kept(
    drive: FakeDriveClient, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    drive.remove("t-about")

    def failing_replace(self: Path, target: Path) -> Path:
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "replace", failing_replace)
    with pytest.raises(PermissionError):
        _sync(drive, cache_dir)
    assert original_path(cache_dir, "t-about").exists()


def test_sync_portfolio_text_file_download_failure_keeps_previous_manifest(
    drive: FakeDriveClient, cache_dir: Path
) -> None:
    _one_album(drive, "p1")
    _root_text(drive, "t-about", "about.json")
    _sync(drive, cache_dir)
    before = (cache_dir / "manifest.json").read_bytes()
    drive.update_file("t-about", md5_checksum="new-md5")
    drive.failing_downloads.add("t-about")
    with pytest.raises(DriveError):
        _sync(drive, cache_dir)
    assert (cache_dir / "manifest.json").read_bytes() == before


@pytest.mark.parametrize(("name", "slug"), [("About", "about-2"), ("Contact", "contact-2")])
def test_sync_portfolio_album_named_like_page_slug_suffixed(
    drive: FakeDriveClient, cache_dir: Path, name: str, slug: str
) -> None:
    _one_album(drive, "p1", name=name)
    assert _sync(drive, cache_dir).albums[0].slug == slug
