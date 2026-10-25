import json
import logging
import math
import re
from datetime import UTC, date, datetime
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from reel.models import Album
from tests.fixtures.albums import (
    make_album,
    make_photo,
    write_corrupt_original,
    write_original,
)
from tests.fixtures.html import Element, parse_html

if TYPE_CHECKING:
    from reel.images import ProcessedPhoto

# Names from build.py are imported inside tests so one missing name fails only the tests
# that use it.


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / ".cache"


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "dist"


def _build(
    albums: list[Album], cache: Path, out: Path, site_title: str = "Site", base_path: str = "/"
) -> None:
    from reel.build import build_site
    from reel.models import Manifest

    build_site(Manifest(albums=albums), cache, out, site_title, base_path)


def _expected(source: Path, scratch: Path) -> "ProcessedPhoto":
    """Derived names for `source`; content hashing makes them independent of the out dir."""
    from reel.images import process_photo

    scratch.mkdir(parents=True, exist_ok=True)
    return process_photo(source, scratch)


def _album_with_photo(cache: Path, slug: str, color: tuple[int, int, int]) -> Album:
    write_original(cache, f"{slug}-p1", color=color)
    return make_album(slug, [make_photo(f"{slug}-p1")])


def _three_albums(cache: Path) -> list[Album]:
    return [
        _album_with_photo(cache, "a", (255, 0, 0)),
        _album_with_photo(cache, "b", (0, 255, 0)),
        _album_with_photo(cache, "c", (0, 0, 255)),
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _page(path: Path) -> Element:
    return parse_html(_read(path))


def _one(root: Element, selector: str) -> Element:
    found = root.find_all(selector)
    assert len(found) == 1, f"expected exactly one {selector!r}, found {len(found)}"
    return found[0]


def _albums(cache: Path, count: int, photos_each: int = 1) -> list[Album]:
    """`count` albums with slugs a, b, c, ... and titles "Album A", "Album B", ..."""
    albums = []
    for a in range(count):
        slug = chr(ord("a") + a)
        photos = []
        for p in range(photos_each):
            write_original(cache, f"{slug}-p{p}", color=(a * 40 % 256, p * 60 % 256, 120))
            photos.append(make_photo(f"{slug}-p{p}"))
        albums.append(make_album(slug, photos, title=f"Album {slug.upper()}"))
    return albums


# base_path_from_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:8000", "/"),
        ("http://localhost:8000/", "/"),
        ("https://x.com/portfolio", "/portfolio/"),
        ("https://x.com/a/", "/a/"),
        ("https://x.com/a/b", "/a/b/"),
    ],
)
def test_base_path_from_url_returns_slash_wrapped_path(url: str, expected: str) -> None:
    from reel.build import base_path_from_url

    assert base_path_from_url(url) == expected


# load_manifest


def test_load_manifest_valid_file_returns_manifest(tmp_path: Path) -> None:
    from reel.build import load_manifest
    from reel.models import Manifest

    manifest = Manifest(albums=[make_album("a", [make_photo("p1")])])
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    assert load_manifest(path) == manifest


def test_load_manifest_missing_file_mentions_reel_sync(tmp_path: Path) -> None:
    from reel.build import BuildError, load_manifest

    with pytest.raises(BuildError, match="reel sync"):
        load_manifest(tmp_path / "manifest.json")


def test_load_manifest_invalid_json_raises_build_error(tmp_path: Path) -> None:
    from reel.build import BuildError, load_manifest

    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BuildError):
        load_manifest(path)


def test_load_manifest_wrong_schema_raises_build_error(tmp_path: Path) -> None:
    from reel.build import BuildError, load_manifest

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"albums": [{"slug": "a"}]}), encoding="utf-8")
    with pytest.raises(BuildError):
        load_manifest(path)


# build_site: output layout


@pytest.mark.parametrize(
    "relative",
    ["index.html", "work/index.html", "a/index.html", "c/index.html", ".reel-build"],
)
def test_build_site_writes_expected_file(cache: Path, out: Path, relative: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert (out / relative).is_file()


def test_build_site_copies_stylesheet(cache: Path, out: Path) -> None:
    from reel.build import STATIC_DIR

    _build(_three_albums(cache), cache, out)
    assert (out / "static" / "site.css").read_bytes() == (STATIC_DIR / "site.css").read_bytes()


def test_build_site_writes_derived_images(cache: Path, out: Path, tmp_path: Path) -> None:
    expected = _expected(write_original(cache, "p1"), tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert (out / "images" / expected.display.jpeg_name).is_file()


def test_build_site_originals_unchanged(cache: Path, out: Path) -> None:
    source = write_original(cache, "p1")
    before = source.read_bytes()
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert source.read_bytes() == before


# build_site: index


@pytest.mark.parametrize("page", ["index.html", "work/index.html"])
def test_build_site_index_links_album(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert 'href="/b/"' in _read(out / page)


def test_build_site_index_shows_album_title(cache: Path, out: Path) -> None:
    write_original(cache, "p1")
    _build([make_album("a", [make_photo("p1")], title="Book One")], cache, out)
    assert "Book One" in _read(out / "index.html")


def test_build_site_index_albums_in_manifest_order(cache: Path, out: Path) -> None:
    a, b, c = _three_albums(cache)
    _build([c, a, b], cache, out)
    page = _page(out / "index.html")
    links = page.find_all("a.feature") + page.find_all("ul.album-grid li.album-card a")
    assert [link.attrs.get("href") for link in links] == ["/c/", "/a/", "/b/"]


def test_build_site_base_path_prefixes_album_links(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out, base_path="/portfolio/")
    assert 'href="/portfolio/a/"' in _read(out / "index.html")


def test_build_site_base_path_prefixes_cover_urls(cache: Path, out: Path, tmp_path: Path) -> None:
    expected = _expected(write_original(cache, "p1"), tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out, base_path="/portfolio/")
    assert f"/portfolio/images/{expected.thumbnail.jpeg_name}" in _read(out / "index.html")


def test_build_site_cover_set_uses_cover_thumbnail(cache: Path, out: Path, tmp_path: Path) -> None:
    write_original(cache, "p1", color=(255, 0, 0))
    expected = _expected(write_original(cache, "cov", color=(0, 0, 255)), tmp_path / "scratch")
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    assert f"/images/{expected.thumbnail.jpeg_name}" in _read(out / "index.html")


def test_build_site_cover_missing_uses_first_photo_thumbnail(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    expected = _expected(write_original(cache, "p1", color=(255, 0, 0)), tmp_path / "scratch")
    write_original(cache, "p2", color=(0, 0, 255))
    _build([make_album("a", [make_photo("p1"), make_photo("p2")])], cache, out)
    assert f"/images/{expected.thumbnail.jpeg_name}" in _read(out / "index.html")


def test_build_site_cover_not_in_photos_not_on_album_page(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    write_original(cache, "p1", color=(255, 0, 0))
    expected = _expected(write_original(cache, "cov", color=(0, 0, 255)), tmp_path / "scratch")
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    assert expected.display.jpeg_name not in _read(out / "a" / "index.html")


# build_site: album pages


def test_build_site_album_page_photos_in_manifest_order(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    ids = ["p10", "p2", "p1"]
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    names = [
        _expected(write_original(cache, i, color=c), tmp_path / "scratch").display.jpeg_name
        for i, c in zip(ids, colors, strict=True)
    ]
    _build([make_album("a", [make_photo(i) for i in ids])], cache, out)
    html = _read(out / "a" / "index.html")
    positions = [html.index(name) for name in names]
    assert positions == sorted(positions)


def _pager_href(out: Path, slug: str, direction: str) -> str | None:
    page = _page(out / slug / "index.html")
    return _one(page, f"nav.album-pager a.pager-{direction}").attrs.get("href")


@pytest.mark.parametrize(
    ("slug", "direction", "expected"),
    [
        ("a", "next", "/b/"),
        ("b", "next", "/c/"),
        ("c", "next", "/a/"),
        ("a", "prev", "/c/"),
        ("b", "prev", "/a/"),
        ("c", "prev", "/b/"),
    ],
)
def test_build_site_album_pager_links_neighbour_wrapping_around(
    cache: Path, out: Path, slug: str, direction: str, expected: str
) -> None:
    _build(_three_albums(cache), cache, out)
    assert _pager_href(out, slug, direction) == expected


@pytest.mark.parametrize(("slug", "other"), [("a", "/b/"), ("b", "/a/")])
def test_build_site_two_albums_pager_links_both_point_to_other(
    cache: Path, out: Path, slug: str, other: str
) -> None:
    _build(_three_albums(cache)[:2], cache, out)
    assert [_pager_href(out, slug, d) for d in ("prev", "next")] == [other, other]


def test_build_site_single_album_has_no_pager(cache: Path, out: Path) -> None:
    _build([_album_with_photo(cache, "a", (255, 0, 0))], cache, out)
    assert _page(out / "a" / "index.html").find_all("nav.album-pager") == []


@pytest.mark.parametrize(("direction", "rel"), [("prev", "prev"), ("next", "next")])
def test_build_site_album_pager_links_have_rel(
    cache: Path, out: Path, direction: str, rel: str
) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "b" / "index.html")
    assert _one(page, f"nav.album-pager a.pager-{direction}").attrs.get("rel") == rel


@pytest.mark.parametrize(("direction", "title"), [("prev", "Album A"), ("next", "Album C")])
def test_build_site_album_pager_link_shows_neighbour_title(
    cache: Path, out: Path, direction: str, title: str
) -> None:
    _build(_albums(cache, 3), cache, out)
    page = _page(out / "b" / "index.html")
    assert _one(page, f"nav.album-pager a.pager-{direction}").text().endswith(title)


def test_build_site_album_pager_is_labelled_nav(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "a" / "index.html")
    assert _one(page, "nav.album-pager").attrs.get("aria-label") == "More albums"


def test_build_site_pager_next_skips_unpublished_album(cache: Path, out: Path) -> None:
    a, b, c = _three_albums(cache)
    _build([a, make_album("empty", []), b, c], cache, out)
    assert _pager_href(out, "a", "next") == "/b/"


def test_build_site_pager_prev_skips_unpublished_album(cache: Path, out: Path) -> None:
    a, b, c = _three_albums(cache)
    _build([a, make_album("empty", []), b, c], cache, out)
    assert _pager_href(out, "b", "prev") == "/a/"


def test_build_site_base_path_prefixes_pager_links(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out, base_path="/portfolio/")
    assert _pager_href(out, "a", "next") == "/portfolio/b/"


@pytest.mark.parametrize(("count", "expected"), [(3, "3 photos"), (1, "1 photo")])
def test_build_site_album_page_count_pluralised(
    cache: Path, out: Path, count: int, expected: str
) -> None:
    _build([_album_of(cache, count)], cache, out)
    assert _one(_page(out / "a" / "index.html"), "p.album-count").text() == expected


# build_site: unpublished and broken albums


def test_build_site_empty_album_has_no_page(cache: Path, out: Path) -> None:
    _build([_album_with_photo(cache, "a", (255, 0, 0)), make_album("empty", [])], cache, out)
    assert not (out / "empty").exists()


def test_build_site_empty_album_not_in_index(cache: Path, out: Path) -> None:
    _build([_album_with_photo(cache, "a", (255, 0, 0)), make_album("empty", [])], cache, out)
    assert 'href="/empty/"' not in _read(out / "index.html")


def test_build_site_unreadable_photo_skipped(cache: Path, out: Path, tmp_path: Path) -> None:
    expected = _expected(write_original(cache, "good"), tmp_path / "scratch")
    write_corrupt_original(cache, "bad")
    _build([make_album("a", [make_photo("bad"), make_photo("good")])], cache, out)
    assert expected.display.jpeg_name in _read(out / "a" / "index.html")


def test_build_site_unreadable_photo_logs_warning(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_original(cache, "good")
    write_corrupt_original(cache, "bad")
    with caplog.at_level(logging.WARNING):
        _build([make_album("a", [make_photo("bad"), make_photo("good")])], cache, out)
    assert any(
        record.levelno == logging.WARNING and "bad.jpg" in record.getMessage()
        for record in caplog.records
    )


def test_build_site_all_photos_unreadable_album_unpublished(cache: Path, out: Path) -> None:
    write_corrupt_original(cache, "bad")
    good = _album_with_photo(cache, "good", (255, 0, 0))
    _build([good, make_album("broken", [make_photo("bad")])], cache, out)
    assert not (out / "broken").exists()


def test_build_site_missing_original_raises_build_error(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    (cache / "originals").mkdir(parents=True)
    with pytest.raises(BuildError):
        _build([make_album("a", [make_photo("never-synced")])], cache, out)


# build_site: slugs


@pytest.mark.parametrize("slug", ["../evil", "A B", "", "a/b", "-a", "a-", "a--b", "Book"])
def test_build_site_invalid_slug_raises_build_error(cache: Path, out: Path, slug: str) -> None:
    from reel.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album(slug, [make_photo("p1")], title="T")], cache, out)


def test_build_site_traversal_slug_writes_nothing_outside_out(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album("../evil", [make_photo("p1")], title="T")], cache, out)
    assert not (out.parent / "evil").exists()


def test_reserved_slugs_match_site_paths() -> None:
    from reel.build import RESERVED_SLUGS

    assert frozenset({"work", "static", "images"}) == RESERVED_SLUGS


@pytest.mark.parametrize("slug", ["work", "static", "images"])
def test_build_site_reserved_slug_raises_build_error(cache: Path, out: Path, slug: str) -> None:
    from reel.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album(slug, [make_photo("p1")])], cache, out)


def test_build_site_duplicate_slug_raises_build_error(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    write_original(cache, "p1")
    write_original(cache, "p2", color=(0, 0, 255))
    albums = [make_album("a", [make_photo("p1")]), make_album("a", [make_photo("p2")])]
    with pytest.raises(BuildError):
        _build(albums, cache, out)


def test_build_site_slug_with_digits_and_hyphens_accepted(cache: Path, out: Path) -> None:
    write_original(cache, "p1")
    _build([make_album("book-2", [make_photo("p1")])], cache, out)
    assert (out / "book-2" / "index.html").is_file()


# build_site: untrusted input

PAYLOAD_TITLE = '<script>alert("x")</script>'


def _untrusted_albums(cache: Path) -> list[Album]:
    """Three albums titled with a script payload, so it shows in feature, cards, and pager."""
    albums = _three_albums(cache)
    return [album.model_copy(update={"title": PAYLOAD_TITLE}) for album in albums]


@pytest.mark.parametrize("page", ["index.html", "a/index.html", "b/index.html"])
def test_build_site_untrusted_title_escaped(cache: Path, out: Path, page: str) -> None:
    _build(_untrusted_albums(cache), cache, out)
    assert "<script>" not in _read(out / page)


def test_build_site_untrusted_title_escaped_in_feature(cache: Path, out: Path) -> None:
    _build(_untrusted_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert _one(page, "a.feature h2.feature-title").text() == PAYLOAD_TITLE


def test_build_site_untrusted_title_escaped_in_cards(cache: Path, out: Path) -> None:
    _build(_untrusted_albums(cache), cache, out)
    titles = _page(out / "index.html").find_all("li.album-card h2.album-title")
    assert [title.text() for title in titles] == [PAYLOAD_TITLE, PAYLOAD_TITLE]


@pytest.mark.parametrize("direction", ["prev", "next"])
def test_build_site_untrusted_title_escaped_in_pager(
    cache: Path, out: Path, direction: str
) -> None:
    _build(_untrusted_albums(cache), cache, out)
    link = _one(_page(out / "b" / "index.html"), f"nav.album-pager a.pager-{direction}")
    assert link.text().endswith(PAYLOAD_TITLE)


def test_build_site_output_has_no_drive_links(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    pages = [_read(path) for path in out.rglob("*.html")]
    assert not any("drive.google.com" in page for page in pages)


# build_site: rebuilding and protecting existing output


def test_build_site_rebuild_removes_stale_album_dir(cache: Path, out: Path) -> None:
    albums = _three_albums(cache)
    _build(albums, cache, out)
    _build(albums[:2], cache, out)
    assert not (out / "c").exists()


def test_build_site_rebuild_removes_stale_album_from_index(cache: Path, out: Path) -> None:
    albums = _three_albums(cache)
    _build(albums, cache, out)
    _build(albums[:2], cache, out)
    assert 'href="/c/"' not in _read(out / "index.html")


def test_build_site_foreign_non_empty_out_raises_build_error(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    out.mkdir()
    (out / "important.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_build_site_foreign_non_empty_out_left_untouched(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    out.mkdir()
    (out / "important.txt").write_text("keep me", encoding="utf-8")
    before = _snapshot(out)
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)
    assert _snapshot(out) == before


def test_build_site_existing_empty_out_is_used(cache: Path, out: Path) -> None:
    out.mkdir()
    _build(_three_albums(cache), cache, out)
    assert (out / "index.html").is_file()


def test_build_site_failed_rebuild_keeps_previous_output(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    albums = _three_albums(cache)
    _build(albums, cache, out)
    before = _snapshot(out)
    broken = [*albums, make_album("d", [make_photo("never-synced")])]
    with pytest.raises(BuildError):
        _build(broken, cache, out)
    assert _snapshot(out) == before


def test_build_site_index_cover_has_webp_source(cache: Path, out: Path, tmp_path: Path) -> None:
    expected = _expected(write_original(cache, "p1"), tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert f'srcset="/images/{expected.thumbnail.webp_name} ' in _read(out / "index.html")


def test_build_site_unreadable_cover_falls_back_to_first_photo(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    expected = _expected(write_original(cache, "p1"), tmp_path / "scratch")
    write_corrupt_original(cache, "cov")
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    assert expected.thumbnail.jpeg_name in _read(out / "index.html")


def test_build_site_unsafe_file_id_raises_build_error(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album("a", [make_photo("../p1")])], cache, out)


def test_build_site_out_is_file_raises_build_error(cache: Path, out: Path) -> None:
    from reel.build import BuildError

    out.write_text("not a directory", encoding="utf-8")
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_build_site_failed_swap_keeps_previous_output(
    cache: Path, out: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reel.build import BuildError, staging_dir_for

    albums = _three_albums(cache)
    _build(albums, cache, out)
    before = _snapshot(out)
    staging = staging_dir_for(out)
    original_rename = Path.rename

    def failing_rename(self: Path, target: Path) -> Path:
        if self == staging:
            raise PermissionError("locked")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing_rename)
    with pytest.raises(BuildError):
        _build(albums, cache, out)
    assert _snapshot(out) == before


def test_build_site_write_error_raises_build_error(
    cache: Path, out: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from reel.build import BuildError

    def failing_copytree(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_srcset_lists_each_url_once() -> None:
    from reel.build import srcset

    assert (
        srcset([("/a.jpg", 600), ("/a.jpg", 600), ("/b.jpg", 2000)]) == "/a.jpg 600w, /b.jpg 2000w"
    )


def test_build_site_index_offers_display_size_for_covers(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    expected = _expected(write_original(cache, "p1", size=(1200, 800)), tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert f"/images/{expected.display.jpeg_name} 1200w" in _read(out / "index.html")


def test_build_site_index_marks_work_nav_current(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert 'aria-current="page"' in _read(out / "work" / "index.html")


def test_build_site_album_page_work_nav_not_current(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert 'aria-current="page"' not in _read(out / "a" / "index.html")


def _build_with_scripts(cache: Path, out: Path, tmp_path: Path) -> None:
    from reel.build import build_site
    from reel.models import Manifest

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "theme.js").write_text("console.log('hi');", encoding="utf-8")
    build_site(Manifest(albums=_three_albums(cache)), cache, out, "Site", scripts_dir=scripts)


def test_build_site_copies_compiled_scripts(cache: Path, out: Path, tmp_path: Path) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert (out / "static" / "theme.js").is_file()


def test_build_site_pages_load_compiled_scripts(cache: Path, out: Path, tmp_path: Path) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert '<script src="/static/theme.js" defer>' in _read(out / "a" / "index.html")


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_without_scripts_has_no_script_tag(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert "<script" not in _read(out / page)


def test_base_path_from_url_space_in_path_is_percent_encoded() -> None:
    from reel.build import base_path_from_url

    assert base_path_from_url("https://x.com/my portfolio") == "/my%20portfolio/"


def test_base_path_from_url_already_encoded_path_not_double_encoded() -> None:
    from reel.build import base_path_from_url

    assert base_path_from_url("https://x.com/my%20portfolio/") == "/my%20portfolio/"


# mosaic_shapes

_SHAPE_SPANS = {"small": (1, 1), "wide": (2, 1), "big": (2, 2), "full": (4, 2)}
_GRID_COLUMNS = 4


def _auto_place(shapes: list[str]) -> list[set[tuple[int, int]]]:
    """Cells (row, column) each shape occupies under CSS grid sparse auto-placement."""
    occupied: set[tuple[int, int]] = set()
    placements: list[set[tuple[int, int]]] = []
    row, column = 0, 0
    for shape in shapes:
        col_span, row_span = _SHAPE_SPANS[shape]
        while True:
            cells = {(row + r, column + c) for r in range(row_span) for c in range(col_span)}
            if column + col_span <= _GRID_COLUMNS and not cells & occupied:
                break
            column += 1
            if column + col_span > _GRID_COLUMNS:
                row, column = row + 1, 0
        occupied |= cells
        placements.append(cells)
        column += col_span
    return placements


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (1, ["full"]),
        (2, ["big", "big"]),
        (3, ["big", "wide", "wide"]),
        (4, ["big", "small", "small", "wide"]),
        (5, ["big", "small", "small", "wide", "full"]),
        (7, ["big", "small", "small", "wide", "wide", "big", "wide"]),
        (8, ["big", "small", "small", "wide", "wide", "big", "small", "small"]),
    ],
)
def test_mosaic_shapes_count_returns_expected_shapes(count: int, expected: list[str]) -> None:
    from reel.build import mosaic_shapes

    assert mosaic_shapes(count) == expected


def test_mosaic_shapes_remainder_three_after_odd_groups_puts_big_in_middle() -> None:
    from reel.build import mosaic_shapes

    assert mosaic_shapes(15)[12:] == ["wide", "big", "wide"]


def test_mosaic_shapes_remainder_three_after_even_groups_puts_big_first() -> None:
    from reel.build import mosaic_shapes

    assert mosaic_shapes(19)[16:] == ["big", "wide", "wide"]


@pytest.mark.parametrize("count", range(21))
def test_mosaic_shapes_tile_four_column_grid_without_holes(count: int) -> None:
    from reel.build import mosaic_shapes

    cells = set().union(*_auto_place(mosaic_shapes(count)))
    rows = 2 * math.ceil(count / 4)
    assert cells == {(r, c) for r in range(rows) for c in range(_GRID_COLUMNS)}


@pytest.mark.parametrize("count", range(1, 21))
def test_mosaic_shapes_each_group_of_four_fills_its_own_block(count: int) -> None:
    from reel.build import mosaic_shapes

    placements = _auto_place(mosaic_shapes(count))
    outside = [
        index
        for index, cells in enumerate(placements)
        if {row // 2 for row, _ in cells} != {index // 4}
    ]
    assert outside == []


def test_mosaic_shapes_negative_count_raises_value_error() -> None:
    from reel.build import mosaic_shapes

    with pytest.raises(ValueError):
        mosaic_shapes(-1)


# mosaic_sizes


@pytest.mark.parametrize(
    ("width", "height", "shape", "desktop"),
    [
        (1500, 1000, "small", "38vw"),
        (1000, 2000, "small", "25vw"),
        (3000, 1000, "wide", "75vw"),
        (1000, 1000, "full", "100vw"),
        (2000, 1000, "big", "100vw"),
        (1000, 2000, "big", "50vw"),
        (1000, 1000, "wide", "50vw"),
        (3000, 1000, "full", "150vw"),
    ],
)
def test_mosaic_sizes_returns_cover_crop_width(
    width: int, height: int, shape: str, desktop: str
) -> None:
    from reel.build import mosaic_sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=width, height=height)
    assert mosaic_sizes(variant, shape) == f"(max-width: 767px) 100vw, {desktop}"


def test_mosaic_sizes_exact_multiple_not_rounded_up_by_float_error() -> None:
    from reel.build import mosaic_sizes
    from reel.images import ImageVariant

    # 25 * 1120 / 1000 is exactly 28, but 25 * (1120 / 1000) is 28.000000000000004 in floats.
    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=1120, height=1000)
    assert mosaic_sizes(variant, "small") == "(max-width: 767px) 100vw, 28vw"


def test_mosaic_sizes_unknown_shape_raises_value_error() -> None:
    from reel.build import mosaic_sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=1000, height=1000)
    with pytest.raises(ValueError):
        mosaic_sizes(variant, "huge")


# build_site: album mosaic and lightbox


def _album_of(cache: Path, count: int) -> Album:
    photos = []
    for index in range(count):
        write_original(cache, f"p{index}", color=(index * 40 % 256, 80, 160))
        photos.append(make_photo(f"p{index}"))
    return make_album("a", photos, title="Book One")


def _tile_shapes(html: str) -> list[str]:
    return re.findall(r'class="tile tile--(\w+)"', html)


def test_build_site_single_photo_album_has_full_tile(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 1)], cache, out)
    assert _tile_shapes(_read(out / "a" / "index.html")) == ["full"]


def test_build_site_four_photo_album_tiles_have_group_shapes(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 4)], cache, out)
    assert _tile_shapes(_read(out / "a" / "index.html")) == ["big", "small", "small", "wide"]


def test_build_site_album_tile_links_display_jpeg_with_base_path(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    source = write_original(cache, "p1", size=(1200, 800))
    expected = _expected(source, tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out, base_path="/portfolio/")
    html = _read(out / "a" / "index.html")
    assert f'href="/portfolio/images/{expected.display.jpeg_name}" data-lightbox' in html


def test_build_site_album_tile_link_not_thumbnail(cache: Path, out: Path, tmp_path: Path) -> None:
    source = write_original(cache, "p1", size=(1200, 800))
    expected = _expected(source, tmp_path / "scratch")
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert f'href="/images/{expected.thumbnail.jpeg_name}"' not in _read(out / "a" / "index.html")


def test_build_site_album_tile_link_has_position_label(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 3)], cache, out)
    assert 'aria-label="Open photo 1 of 3"' in _read(out / "a" / "index.html")


def test_build_site_album_tile_last_link_label_counts_all_photos(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 3)], cache, out)
    assert 'aria-label="Open photo 3 of 3"' in _read(out / "a" / "index.html")


def test_build_site_album_tile_sizes_follow_shape(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 400))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    # A 3:1 photo in a 2:1 full tile is cropped to 1.5x the 100vw tile width.
    assert 'sizes="(max-width: 767px) 100vw, 150vw"' in _read(out / "a" / "index.html")


def test_build_site_album_page_has_visible_heading(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 1)], cache, out)
    html = _read(out / "a" / "index.html")
    assert re.search(r'<h1 class="album-heading">\s*Book One\s*</h1>', html)


def test_build_site_album_page_body_has_page_album_class(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert '<body class="page-album">' in _read(out / "a" / "index.html")


@pytest.mark.parametrize("page", ["index.html", "work/index.html"])
def test_build_site_index_body_has_no_page_album_class(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert "page-album" not in _read(out / page)


def test_build_site_with_scripts_album_page_has_lightbox(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert '<dialog class="lightbox"' in _read(out / "a" / "index.html")


@pytest.mark.parametrize(
    "control",
    [
        'class="lightbox-image"',
        'class="lightbox-counter"',
        'aria-label="Close"',
        'aria-label="Previous photo"',
        'aria-label="Next photo"',
    ],
)
def test_build_site_with_scripts_lightbox_has_control(
    cache: Path, out: Path, tmp_path: Path, control: str
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    html = _read(out / "a" / "index.html")
    assert control in html[html.index('<dialog class="lightbox"') :]


def test_build_site_without_scripts_album_page_has_no_lightbox(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert "<dialog" not in _read(out / "a" / "index.html")


# album_card_spans

_CARD_SPANS = {3, 4, 6, 12}
_CARD_COLUMNS = 12


def _rows(spans: list[int]) -> list[list[int]]:
    """Spans grouped into rows as CSS grid auto-placement wraps them on 12 columns."""
    rows: list[list[int]] = []
    for span in spans:
        if not rows or sum(rows[-1]) + span > _CARD_COLUMNS:
            rows.append([])
        rows[-1].append(span)
    return rows


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (1, [12]),
        (2, [6, 6]),
        (3, [4, 4, 4]),
        (4, [3, 3, 3, 3]),
        (5, [4, 4, 4, 6, 6]),
        (6, [3, 3, 3, 3, 6, 6]),
        (7, [3, 3, 3, 3, 4, 4, 4]),
        (9, [3, 3, 3, 3, 4, 4, 4, 6, 6]),
    ],
)
def test_album_card_spans_count_returns_expected_spans(count: int, expected: list[int]) -> None:
    from reel.build import album_card_spans

    assert album_card_spans(count) == expected


@pytest.mark.parametrize("count", range(21))
def test_album_card_spans_returns_one_span_per_card(count: int) -> None:
    from reel.build import album_card_spans

    assert len(album_card_spans(count)) == count


@pytest.mark.parametrize("count", range(21))
def test_album_card_spans_every_row_fills_twelve_columns(count: int) -> None:
    from reel.build import album_card_spans

    row_widths = [sum(row) for row in _rows(album_card_spans(count))]
    assert all(width == _CARD_COLUMNS for width in row_widths)


@pytest.mark.parametrize("count", range(21))
def test_album_card_spans_uses_only_allowed_spans(count: int) -> None:
    from reel.build import album_card_spans

    assert set(album_card_spans(count)) <= _CARD_SPANS


def test_album_card_spans_negative_count_raises_value_error() -> None:
    from reel.build import album_card_spans

    with pytest.raises(ValueError):
        album_card_spans(-1)


# cover_sizes


@pytest.mark.parametrize(
    ("width", "height", "width_vw", "box_aspect", "desktop"),
    [
        (1000, 2000, 66, Fraction(16, 9), "66vw"),
        (1600, 900, 66, Fraction(16, 9), "66vw"),
        (3000, 1000, 66, Fraction(16, 9), "112vw"),
        (1000, 1000, 25, Fraction(4, 5), "32vw"),
        (1000, 1000, 100, Fraction(16, 5), "100vw"),
        (1600, 400, 100, Fraction(16, 5), "125vw"),
    ],
)
def test_cover_sizes_returns_cover_crop_width(
    width: int, height: int, width_vw: int, box_aspect: Fraction, desktop: str
) -> None:
    from reel.build import cover_sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=width, height=height)
    assert cover_sizes(variant, width_vw, box_aspect) == f"(max-width: 767px) 100vw, {desktop}"


def test_cover_sizes_exact_multiple_not_rounded_up_by_float_error() -> None:
    from reel.build import cover_sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=1120, height=1000)
    assert cover_sizes(variant, 25, Fraction(1)) == "(max-width: 767px) 100vw, 28vw"


@pytest.mark.parametrize(
    ("shape", "width_vw", "aspect"),
    [("small", 25, 1), ("wide", 50, 2), ("big", 50, 1), ("full", 100, 2)],
)
def test_mosaic_sizes_matches_cover_sizes_for_tile_box(
    shape: str, width_vw: int, aspect: int
) -> None:
    from reel.build import cover_sizes, mosaic_sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=3000, height=1000)
    assert mosaic_sizes(variant, shape) == cover_sizes(variant, width_vw, Fraction(aspect))


# build_site: index heading and counts


def test_build_site_index_heading_is_work(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert _one(_page(out / "index.html"), "h1.page-heading").text() == "Work"


@pytest.mark.parametrize(
    ("album_count", "photos_each", "expected"),
    [
        (3, 2, "3 albums · 6 photographs"),
        (1, 1, "1 album · 1 photograph"),
        (1, 2, "1 album · 2 photographs"),
        (2, 1, "2 albums · 2 photographs"),
    ],
)
def test_build_site_index_meta_counts_albums_and_photos(
    cache: Path, out: Path, album_count: int, photos_each: int, expected: str
) -> None:
    _build(_albums(cache, album_count, photos_each), cache, out)
    assert _one(_page(out / "index.html"), "p.page-meta").text() == expected


def test_build_site_index_meta_no_albums_uses_plurals(cache: Path, out: Path) -> None:
    _build([], cache, out)
    assert _one(_page(out / "index.html"), "p.page-meta").text() == "0 albums · 0 photographs"


def test_build_site_index_meta_does_not_count_cover_file(cache: Path, out: Path) -> None:
    write_original(cache, "p1", color=(255, 0, 0))
    write_original(cache, "cov", color=(0, 0, 255))
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    assert _one(_page(out / "index.html"), "p.page-meta").text() == "1 album · 1 photograph"


def test_build_site_index_meta_skips_unpublished_albums(cache: Path, out: Path) -> None:
    _build([*_albums(cache, 2), make_album("empty", [])], cache, out)
    assert _one(_page(out / "index.html"), "p.page-meta").text() == "2 albums · 2 photographs"


def test_build_site_index_meta_does_not_count_unreadable_photos(cache: Path, out: Path) -> None:
    write_original(cache, "good")
    write_corrupt_original(cache, "bad")
    _build([make_album("a", [make_photo("bad"), make_photo("good")])], cache, out)
    assert _one(_page(out / "index.html"), "p.page-meta").text() == "1 album · 1 photograph"


# build_site: index feature card


def test_build_site_index_feature_links_first_album(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert _one(page, "section.albums a.feature").attrs.get("href") == "/a/"


def test_build_site_index_albums_section_has_preview_hook(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert "data-album-preview" in _one(_page(out / "index.html"), "section.albums").attrs


def test_build_site_index_feature_label_is_latest_album(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert _one(page, "a.feature span.feature-label").text() == "Latest album"


def test_build_site_index_feature_title_is_first_album(cache: Path, out: Path) -> None:
    _build(_albums(cache, 3), cache, out)
    page = _page(out / "index.html")
    assert _one(page, "a.feature h2.feature-title").text() == "Album A"


@pytest.mark.parametrize(("photos_each", "expected"), [(3, "3 photos"), (1, "1 photo")])
def test_build_site_index_feature_count_pluralised(
    cache: Path, out: Path, photos_each: int, expected: str
) -> None:
    _build(_albums(cache, 2, photos_each), cache, out)
    page = _page(out / "index.html")
    assert _one(page, "a.feature p.feature-count").text() == expected


def test_build_site_index_feature_has_picture_in_frame(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert len(page.find_all("a.feature div.feature-frame picture img")) == 1


def test_build_site_index_feature_title_in_text_block(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert len(page.find_all("a.feature div.feature-text h2.feature-title")) == 1


def test_build_site_index_feature_sizes_from_wide_box(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 400))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    image = _one(_page(out / "index.html"), "a.feature img")
    # A 3:1 cover in a 66vw-wide 16:9 frame is cropped to 66 * 27/16 = 111.4vw.
    assert image.attrs.get("sizes") == "(max-width: 767px) 100vw, 112vw"


def test_build_site_single_album_index_has_feature(cache: Path, out: Path) -> None:
    _build(_albums(cache, 1), cache, out)
    assert len(_page(out / "index.html").find_all("a.feature")) == 1


def test_build_site_single_album_index_has_no_grid(cache: Path, out: Path) -> None:
    _build(_albums(cache, 1), cache, out)
    assert _page(out / "index.html").find_all("ul.album-grid") == []


@pytest.mark.parametrize("selector", ["a.feature", "ul.album-grid"])
def test_build_site_no_albums_index_has_no_feature_or_grid(
    cache: Path, out: Path, selector: str
) -> None:
    _build([], cache, out)
    assert _page(out / "index.html").find_all(selector) == []


# build_site: index album grid


def _cards(out: Path) -> list[Element]:
    return _page(out / "index.html").find_all("section.albums ul.album-grid li.album-card")


def test_build_site_index_grid_lists_other_albums_in_order(cache: Path, out: Path) -> None:
    _build(_albums(cache, 4), cache, out)
    titles = [_one(card, "h2.album-title").text() for card in _cards(out)]
    assert titles == ["Album B", "Album C", "Album D"]


def test_build_site_index_grid_links_other_albums(cache: Path, out: Path) -> None:
    _build(_albums(cache, 4), cache, out)
    hrefs = [_one(card, "a").attrs.get("href") for card in _cards(out)]
    assert hrefs == ["/b/", "/c/", "/d/"]


def test_build_site_index_grid_card_has_picture_in_frame(cache: Path, out: Path) -> None:
    _build(_albums(cache, 2), cache, out)
    (card,) = _cards(out)
    assert len(card.find_all("a div.album-frame picture img")) == 1


@pytest.mark.parametrize(("photos_each", "expected"), [(2, "2 photos"), (1, "1 photo")])
def test_build_site_index_grid_card_count_pluralised(
    cache: Path, out: Path, photos_each: int, expected: str
) -> None:
    _build(_albums(cache, 2, photos_each), cache, out)
    (card,) = _cards(out)
    assert _one(card, "p.album-count").text() == expected


def _card_spans(out: Path) -> list[int]:
    spans: list[int] = []
    for card in _cards(out):
        found = [re.fullmatch(r"album-card--span-(\d+)", name) for name in card.classes]
        spans.extend(int(match.group(1)) for match in found if match)
    return spans


@pytest.mark.parametrize(
    ("album_count", "expected"),
    [(2, [12]), (3, [6, 6]), (5, [3, 3, 3, 3]), (6, [4, 4, 4, 6, 6])],
)
def test_build_site_index_grid_cards_have_span_classes(
    cache: Path, out: Path, album_count: int, expected: list[int]
) -> None:
    _build(_albums(cache, album_count), cache, out)
    assert _card_spans(out) == expected


def test_build_site_index_card_sizes_from_span_box(cache: Path, out: Path) -> None:
    write_original(cache, "a-p1")
    write_original(cache, "b-p1", size=(1200, 400))
    write_original(cache, "c-p1", color=(0, 0, 255))
    albums = [make_album(slug, [make_photo(f"{slug}-p1")]) for slug in ("a", "b", "c")]
    _build(albums, cache, out)
    image = _one(_cards(out)[0], "img")
    # Span 6 is a 50vw frame of aspect 8/5; a 3:1 cover is cropped to 50 * 15/8 = 93.75vw.
    assert image.attrs.get("sizes") == "(max-width: 767px) 100vw, 94vw"


def test_build_site_index_card_sizes_round_fractional_box_up(cache: Path, out: Path) -> None:
    albums = []
    for index, slug in enumerate("abcd"):
        write_original(cache, f"{slug}-p1", color=(index * 60, 0, 0), size=(30, 30))
        albums.append(make_album(slug, [make_photo(f"{slug}-p1")]))
    _build(albums, cache, out)
    image = _one(_cards(out)[0], "img")
    # Span 4 is a 33.3vw frame of aspect 16/15; a square cover is not cropped wider than it.
    assert image.attrs.get("sizes") == "(max-width: 767px) 100vw, 34vw"


_SIZES_PATTERN = re.compile(r"\(max-width: 767px\) 100vw, \d+vw")


def test_build_site_index_card_links_carry_feature_sizes(cache: Path, out: Path) -> None:
    _build(_albums(cache, 4), cache, out)
    values = [_one(card, "a").attrs.get("data-feature-sizes") or "" for card in _cards(out)]
    assert [bool(_SIZES_PATTERN.fullmatch(value)) for value in values] == [True, True, True]


def test_build_site_index_card_feature_sizes_follow_cover_aspect(cache: Path, out: Path) -> None:
    write_original(cache, "a-p1")
    write_original(cache, "b-p1", size=(1200, 400))
    write_original(cache, "c-p1", size=(1200, 800), color=(0, 0, 255))
    albums = [make_album(slug, [make_photo(f"{slug}-p1")]) for slug in ("a", "b", "c")]
    _build(albums, cache, out)
    values = [_one(card, "a").attrs.get("data-feature-sizes") for card in _cards(out)]
    # In the 66vw 16:9 feature frame a 3:1 cover is cropped to 112vw; a 3:2 cover fits at 66vw.
    assert values == ["(max-width: 767px) 100vw, 112vw", "(max-width: 767px) 100vw, 66vw"]


# build_site: header and footer


def _build_years() -> set[int]:
    return {date.today().year, datetime.now(UTC).year}


@pytest.mark.parametrize("page", ["index.html", "work/index.html", "a/index.html"])
def test_build_site_footer_shows_site_title(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out, site_title="My Portfolio")
    assert "My Portfolio" in _one(_page(out / page), "footer.site-footer").text()


@pytest.mark.parametrize("page", ["index.html", "work/index.html", "a/index.html"])
def test_build_site_footer_shows_build_year(cache: Path, out: Path, page: str) -> None:
    years = _build_years()
    _build(_three_albums(cache), cache, out)
    years |= _build_years()
    footer = _one(_page(out / page), "footer.site-footer").text()
    assert any(f"© {year}" in footer for year in years)


def test_build_site_untrusted_site_title_escaped_in_footer(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out, site_title=PAYLOAD_TITLE)
    assert PAYLOAD_TITLE in _one(_page(out / "index.html"), "footer.site-footer").text()


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_header_has_site_title_link(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out, site_title="My Portfolio")
    link = _one(_page(out / page), "header.site-header a.site-title")
    assert (link.text(), link.attrs.get("href")) == ("My Portfolio", "/")


# build_site: theme toggle


def _toggle(out: Path, page: str) -> Element:
    return _one(_page(out / page), "header.site-header nav.site-nav button.theme-toggle")


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_with_scripts_nav_has_theme_toggle(
    cache: Path, out: Path, tmp_path: Path, page: str
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert _toggle(out, page).attrs.get("type") == "button"


def test_build_site_with_scripts_theme_toggle_starts_hidden(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert "hidden" in _toggle(out, "index.html").attrs


def test_build_site_with_scripts_theme_toggle_labelled_for_dark(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert _toggle(out, "index.html").attrs.get("aria-label") == "Switch to dark mode"


def test_build_site_with_scripts_theme_toggle_has_icon(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert _toggle(out, "index.html").find_all("svg") != []


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_without_scripts_has_no_theme_toggle(cache: Path, out: Path, page: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert _page(out / page).find_all("button.theme-toggle") == []


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_with_scripts_head_applies_stored_theme(
    cache: Path, out: Path, tmp_path: Path, page: str
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    head = _one(_page(out / page), "head")
    inline = [script for script in head.find_all("script") if "src" not in script.attrs]
    assert any("reel-theme" in script.text() for script in inline)


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_with_scripts_stored_theme_applied_before_stylesheet(
    cache: Path, out: Path, tmp_path: Path, page: str
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    head = _one(_page(out / page), "head")
    order = [
        "theme" if element.tag == "script" and "reel-theme" in element.text() else "stylesheet"
        for element in head.descendants()
        if (element.tag == "script" and "src" not in element.attrs)
        or (element.tag == "link" and element.attrs.get("rel") == "stylesheet")
    ]
    assert order[:2] == ["theme", "stylesheet"]
