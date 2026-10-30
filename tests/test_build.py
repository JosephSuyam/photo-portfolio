import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from portfolio.models import Album, Photo
from tests.fixtures.albums import (
    make_album,
    make_photo,
    write_corrupt_original,
    write_original,
)
from tests.fixtures.html import Element, parse_html
from tests.fixtures.pages import make_text_file, write_text_original

if TYPE_CHECKING:
    from portfolio.images import ProcessedPhoto

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
    from portfolio.build import build_site
    from portfolio.models import Manifest

    build_site(Manifest(albums=albums), cache, out, site_title, base_path)


def _expected(source: Path, scratch: Path) -> "ProcessedPhoto":
    """Derived names for `source`; content hashing makes them independent of the out dir."""
    from portfolio.images import process_photo

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
    from portfolio.build import base_path_from_url

    assert base_path_from_url(url) == expected


# load_manifest


def test_load_manifest_valid_file_returns_manifest(tmp_path: Path) -> None:
    from portfolio.build import load_manifest
    from portfolio.models import Manifest

    manifest = Manifest(albums=[make_album("a", [make_photo("p1")])])
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    assert load_manifest(path) == manifest


def test_load_manifest_missing_file_mentions_portfolio_sync(tmp_path: Path) -> None:
    from portfolio.build import BuildError, load_manifest

    with pytest.raises(BuildError, match="portfolio sync"):
        load_manifest(tmp_path / "manifest.json")


def test_load_manifest_invalid_json_raises_build_error(tmp_path: Path) -> None:
    from portfolio.build import BuildError, load_manifest

    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BuildError):
        load_manifest(path)


def test_load_manifest_wrong_schema_raises_build_error(tmp_path: Path) -> None:
    from portfolio.build import BuildError, load_manifest

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"albums": [{"slug": "a"}]}), encoding="utf-8")
    with pytest.raises(BuildError):
        load_manifest(path)


# build_site: output layout


@pytest.mark.parametrize(
    "relative",
    ["index.html", "work/index.html", "a/index.html", "c/index.html", ".portfolio-build"],
)
def test_build_site_writes_expected_file(cache: Path, out: Path, relative: str) -> None:
    _build(_three_albums(cache), cache, out)
    assert (out / relative).is_file()


def test_build_site_copies_stylesheet(cache: Path, out: Path) -> None:
    from portfolio.build import STATIC_DIR

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
    links = _page(out / "index.html").find_all("section.scenes article.scene a")
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


def test_build_site_cover_not_in_photos_not_among_mosaic_tiles(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    write_original(cache, "p1", color=(255, 0, 0))
    expected = _expected(write_original(cache, "cov", color=(0, 0, 255)), tmp_path / "scratch")
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    html = _read(out / "a" / "index.html")
    mosaic = html[html.index('<ul class="mosaic">') : html.index("</ul>")]
    assert expected.display.jpeg_name not in mosaic


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


@pytest.mark.parametrize(
    ("make", "expected"),
    [
        (lambda cache: _album_with_cover_file(cache, 3), "4 photos"),
        (lambda cache: _album_of(cache, 3), "3 photos"),
        (lambda cache: _album_with_identical_cover(cache, 2), "2 photos"),
    ],
    ids=["separate-cover", "no-cover", "identical-cover"],
)
def test_build_site_album_page_count_includes_separate_cover_only(
    cache: Path, out: Path, make: Callable[[Path], Album], expected: str
) -> None:
    _build([make(cache)], cache, out)
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
    from portfolio.build import BuildError

    (cache / "originals").mkdir(parents=True)
    with pytest.raises(BuildError):
        _build([make_album("a", [make_photo("never-synced")])], cache, out)


# build_site: slugs


@pytest.mark.parametrize("slug", ["../evil", "A B", "", "a/b", "-a", "a-", "a--b", "Book"])
def test_build_site_invalid_slug_raises_build_error(cache: Path, out: Path, slug: str) -> None:
    from portfolio.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album(slug, [make_photo("p1")], title="T")], cache, out)


def test_build_site_traversal_slug_writes_nothing_outside_out(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album("../evil", [make_photo("p1")], title="T")], cache, out)
    assert not (out.parent / "evil").exists()


def test_reserved_slugs_match_site_paths() -> None:
    from portfolio.build import RESERVED_SLUGS

    assert frozenset({"work", "static", "images", "about", "contact", "api"}) == RESERVED_SLUGS


@pytest.mark.parametrize("slug", ["work", "static", "images", "about", "contact", "api"])
def test_build_site_reserved_slug_raises_build_error(cache: Path, out: Path, slug: str) -> None:
    from portfolio.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album(slug, [make_photo("p1")])], cache, out)


def test_build_site_duplicate_slug_raises_build_error(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError

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
    """Three albums titled with a script payload, so it shows in scenes, heroes, and pager."""
    albums = _three_albums(cache)
    return [album.model_copy(update={"title": PAYLOAD_TITLE}) for album in albums]


@pytest.mark.parametrize("page", ["index.html", "a/index.html", "b/index.html"])
def test_build_site_untrusted_title_escaped(cache: Path, out: Path, page: str) -> None:
    _build(_untrusted_albums(cache), cache, out)
    assert "<script>" not in _read(out / page)


def test_build_site_untrusted_title_escaped_in_scenes(cache: Path, out: Path) -> None:
    _build(_untrusted_albums(cache), cache, out)
    titles = _page(out / "index.html").find_all("article.scene h2.scene-title")
    assert [title.text() for title in titles] == [PAYLOAD_TITLE] * 3


def test_build_site_untrusted_title_escaped_in_album_hero(cache: Path, out: Path) -> None:
    _build(_untrusted_albums(cache), cache, out)
    page = _page(out / "a" / "index.html")
    assert _one(page, "section.album-hero h1.album-heading").text() == PAYLOAD_TITLE


def test_build_site_untrusted_title_escaped_in_hero_link_label(cache: Path, out: Path) -> None:
    _build(_untrusted_albums(cache), cache, out)
    link = _one(_page(out / "a" / "index.html"), "a.album-hero-link")
    assert link.attrs.get("aria-label") == f"Open cover photo of {PAYLOAD_TITLE}"


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
    from portfolio.build import BuildError

    out.mkdir()
    (out / "important.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_build_site_foreign_non_empty_out_left_untouched(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError

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
    from portfolio.build import BuildError

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
    from portfolio.build import BuildError

    write_original(cache, "p1")
    with pytest.raises(BuildError):
        _build([make_album("a", [make_photo("../p1")])], cache, out)


def test_build_site_out_is_file_raises_build_error(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError

    out.write_text("not a directory", encoding="utf-8")
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_build_site_failed_swap_keeps_previous_output(
    cache: Path, out: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from portfolio.build import BuildError, staging_dir_for

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

    from portfolio.build import BuildError

    def failing_copytree(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)
    with pytest.raises(BuildError):
        _build(_three_albums(cache), cache, out)


def test_srcset_lists_each_url_once() -> None:
    from portfolio.build import srcset

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
    from portfolio.build import build_site
    from portfolio.models import Manifest

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
    from portfolio.build import base_path_from_url

    assert base_path_from_url("https://x.com/my portfolio") == "/my%20portfolio/"


def test_base_path_from_url_already_encoded_path_not_double_encoded() -> None:
    from portfolio.build import base_path_from_url

    assert base_path_from_url("https://x.com/my%20portfolio/") == "/my%20portfolio/"


# mosaic_shapes

_BLOCK = ["big", "small", "small", "big", "small", "small"]


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (1, ["full"]),
        (2, ["big", "big"]),
        (3, ["big", "wide", "wide"]),
        (4, ["big", "small", "small", "wide"]),
        (5, ["big", "small", "small", "big", "wide"]),
        (6, _BLOCK),
        (7, [*_BLOCK, "full"]),
        (8, [*_BLOCK, "big", "big"]),
        (9, [*_BLOCK, "big", "wide", "wide"]),
        (10, [*_BLOCK, "big", "small", "small", "wide"]),
        (11, [*_BLOCK, "big", "small", "small", "big", "wide"]),
        (12, [*_BLOCK, *_BLOCK]),
        (13, [*_BLOCK, *_BLOCK, "full"]),
    ],
)
def test_mosaic_shapes_blocks_then_closed_remainder(count: int, expected: list[str]) -> None:
    from portfolio.build import mosaic_shapes

    assert mosaic_shapes(count) == expected


def test_mosaic_shapes_negative_count_raises_value_error() -> None:
    from portfolio.build import mosaic_shapes

    with pytest.raises(ValueError, match="-1"):
        mosaic_shapes(-1)


# mosaic_sizes


@pytest.mark.parametrize(
    ("width", "height", "shape", "expected"),
    [
        # A 3:2 photo overflows a square tile: 1.5x its 100 / 50 / 25vw box.
        (3000, 2000, "small", "(max-width: 767px) 150vw, (max-width: 1024px) 75vw, 38vw"),
        # A 2:1 photo fits a 2:1 tile exactly and overflows only the square phone tile.
        (2000, 1000, "wide", "(max-width: 767px) 200vw, (max-width: 1024px) 100vw, 50vw"),
        # A tall photo is cropped top and bottom, so it is never wider than its tile.
        (1000, 2000, "big", "(max-width: 767px) 100vw, (max-width: 1024px) 100vw, 50vw"),
    ],
)
def test_mosaic_sizes_returns_cropped_width_per_breakpoint(
    width: int, height: int, shape: str, expected: str
) -> None:
    from portfolio.build import mosaic_sizes
    from portfolio.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=width, height=height)
    assert mosaic_sizes(variant, shape) == expected


# build_site: album mosaic and lightbox


def _album_of(cache: Path, count: int) -> Album:
    photos = []
    for index in range(count):
        write_original(cache, f"p{index}", color=(index * 40 % 256, 80, 160))
        photos.append(make_photo(f"p{index}"))
    return make_album("a", photos, title="Book One")


def _tiles(out: Path) -> list[Element]:
    return _page(out / "a" / "index.html").find_all("ul.mosaic li.tile")


def test_build_site_album_tiles_have_shape_class_in_photo_order(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 8)], cache, out)
    shapes = ["big", "small", "small", "big", "small", "small", "big", "big"]
    assert [tile.classes for tile in _tiles(out)] == [["tile", f"tile--{s}"] for s in shapes]


def test_build_site_album_tiles_all_lazy(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 3)], cache, out)
    loading = [_one(tile, "img").attrs.get("loading") for tile in _tiles(out)]
    assert loading == ["lazy"] * 3


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


def test_build_site_album_tile_sizes_from_tile_shape(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 800))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    image = _one(_tiles(out)[0], "img")
    # A lone photo is a full tile: 2:1 on desktop and tablet, square on phones.
    assert image.attrs.get("sizes") == "(max-width: 767px) 150vw, (max-width: 1024px) 100vw, 100vw"


def test_build_site_album_tile_source_sizes_match_image(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 800))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    (tile,) = _tiles(out)
    assert _one(tile, "source").attrs.get("sizes") == _one(tile, "img").attrs.get("sizes")


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


# cover_sizes


@pytest.mark.parametrize(
    ("width", "height", "phone", "desktop"),
    [
        (1000, 2000, 100, 100),
        (1080, 1929, 100, 100),
        (900, 1600, 100, 100),
        (1600, 900, 317, 100),
        (3000, 2000, 267, 100),
        (3000, 1000, 534, 169),
    ],
)
def test_cover_sizes_returns_cover_crop_width_per_box(
    width: int, height: int, phone: int, desktop: int
) -> None:
    from portfolio.build import cover_sizes
    from portfolio.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=width, height=height)
    assert cover_sizes(variant) == f"(max-width: 767px) {phone}vw, {desktop}vw"


def test_cover_sizes_exact_multiple_not_rounded_up_by_float_error() -> None:
    from portfolio.build import cover_sizes
    from portfolio.images import ImageVariant

    # 1792/900 is exactly 1.12 x 16/9; float division gives 112.00000000000001.
    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=1792, height=900)
    assert cover_sizes(variant) == "(max-width: 767px) 354vw, 112vw"


@pytest.mark.parametrize(
    ("name", "expected"),
    [("SCENE_ASPECT", Fraction(16, 9)), ("PHONE_SCENE_ASPECT", Fraction(9, 16))],
)
def test_scene_aspect_constant_matches_design(name: str, expected: Fraction) -> None:
    import portfolio.build

    assert getattr(portfolio.build, name) == expected


# build_site: index scenes


def _scenes(out: Path) -> list[Element]:
    return _page(out / "index.html").find_all("section.scenes article.scene")


def test_build_site_index_heading_is_work(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert _one(_page(out / "index.html"), "h1.visually-hidden").text() == "Work"


def test_build_site_index_scene_titles_follow_album_order(cache: Path, out: Path) -> None:
    _build(_albums(cache, 4), cache, out)
    titles = [_one(scene, "h2.scene-title").text() for scene in _scenes(out)]
    assert titles == ["Album A", "Album B", "Album C", "Album D"]


def test_build_site_index_scenes_link_their_albums(cache: Path, out: Path) -> None:
    _build(_albums(cache, 4), cache, out)
    hrefs = [_one(scene, "a").attrs.get("href") for scene in _scenes(out)]
    assert hrefs == ["/a/", "/b/", "/c/", "/d/"]


def test_build_site_index_scene_title_in_text_block(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    page = _page(out / "index.html")
    assert len(page.find_all("article.scene a div.scene-text h2.scene-title")) == 3


def test_build_site_index_scene_has_one_picture(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    counts = [len(scene.find_all("a picture img")) for scene in _scenes(out)]
    assert counts == [1, 1, 1]


@pytest.mark.parametrize(("photos_each", "expected"), [(3, "3 photos"), (1, "1 photo")])
def test_build_site_index_scene_count_pluralised(
    cache: Path, out: Path, photos_each: int, expected: str
) -> None:
    _build(_albums(cache, 2, photos_each), cache, out)
    counts = [_one(scene, "p.scene-count").text() for scene in _scenes(out)]
    assert counts == [f"{expected} — View album →"] * 2


@pytest.mark.parametrize(
    ("album_count", "expected"),
    [(1, ["01 / 01"]), (3, ["01 / 03", "02 / 03", "03 / 03"])],
)
def test_build_site_index_scene_numbers_count_scenes(
    cache: Path, out: Path, album_count: int, expected: list[str]
) -> None:
    _build(_albums(cache, album_count), cache, out)
    assert [_one(scene, "span.scene-number").text() for scene in _scenes(out)] == expected


def test_build_site_index_scene_numbers_past_nine_keep_two_digits(cache: Path, out: Path) -> None:
    _build(_albums(cache, 10), cache, out)
    numbers = [_one(scene, "span.scene-number").text() for scene in _scenes(out)]
    assert numbers[-2:] == ["09 / 10", "10 / 10"]


def test_build_site_index_scene_numbers_hidden_from_screen_readers(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    hidden = [_one(scene, "span.scene-number").attrs.get("aria-hidden") for scene in _scenes(out)]
    assert hidden == ["true"] * 3


def test_build_site_index_only_first_scene_cover_eager(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    loading = [_one(scene, "img").attrs.get("loading") for scene in _scenes(out)]
    assert loading == [None, "lazy", "lazy"]


def test_build_site_index_scene_sizes_from_wide_cover(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 400))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    image = _one(_page(out / "index.html"), "article.scene img")
    # A 3:1 cover is cropped to 168.75vw in a 16:9 scene and 533.3vw in a 9:16 phone scene.
    assert image.attrs.get("sizes") == "(max-width: 767px) 534vw, 169vw"


def test_build_site_index_scene_narrower_cover_not_cropped_wider(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 800))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    image = _one(_page(out / "index.html"), "article.scene img")
    assert image.attrs.get("sizes") == "(max-width: 767px) 267vw, 100vw"


def test_build_site_index_scene_sizes_follow_each_cover_aspect(cache: Path, out: Path) -> None:
    write_original(cache, "a-p1", size=(1200, 800))
    write_original(cache, "b-p1", size=(1200, 400), color=(0, 0, 255))
    albums = [make_album(slug, [make_photo(f"{slug}-p1")]) for slug in ("a", "b")]
    _build(albums, cache, out)
    sizes = [_one(scene, "img").attrs.get("sizes") for scene in _scenes(out)]
    assert sizes == ["(max-width: 767px) 267vw, 100vw", "(max-width: 767px) 534vw, 169vw"]


def test_build_site_index_scene_sizes_round_fractional_width_up(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(400, 200))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    image = _one(_page(out / "index.html"), "article.scene img")
    # A 2:1 cover is cropped to 112.5vw in a 16:9 scene and 355.6vw in a 9:16 phone scene.
    assert image.attrs.get("sizes") == "(max-width: 767px) 356vw, 113vw"


def test_build_site_index_scene_source_sizes_match_image(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 400))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    scene = _one(_page(out / "index.html"), "article.scene")
    assert _one(scene, "source").attrs.get("sizes") == _one(scene, "img").attrs.get("sizes")


def test_build_site_single_album_index_has_one_scene(cache: Path, out: Path) -> None:
    _build(_albums(cache, 1), cache, out)
    assert len(_scenes(out)) == 1


def test_build_site_no_albums_index_has_no_scenes_section(cache: Path, out: Path) -> None:
    _build([], cache, out)
    assert _page(out / "index.html").find_all("section.scenes") == []


# build_site: album hero


def _hero(out: Path) -> Element:
    return _one(_page(out / "a" / "index.html"), "section.album-hero")


def test_build_site_album_hero_comes_before_mosaic(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 2)], cache, out)
    html = _read(out / "a" / "index.html")
    assert html.index('<section class="album-hero">') < html.index('<ul class="mosaic">')


def test_build_site_album_hero_holds_heading_and_count(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 2)], cache, out)
    hero = _hero(out)
    texts = [_one(hero, selector).text() for selector in ("h1.album-heading", "p.album-count")]
    assert texts == ["Book One", "2 photos"]


def test_build_site_album_hero_shows_cover_file(cache: Path, out: Path, tmp_path: Path) -> None:
    write_original(cache, "p1", color=(255, 0, 0))
    cover = write_original(cache, "cov", color=(0, 0, 255), size=(1200, 800))
    expected = _expected(cover, tmp_path / "scratch")
    album = make_album("a", [make_photo("p1")], cover=make_photo("cov", "cover.jpg"))
    _build([album], cache, out)
    srcset = _one(_hero(out), "img").attrs.get("srcset") or ""
    assert f"/images/{expected.display.jpeg_name} 1200w" in srcset


def test_build_site_album_hero_cover_eager(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 2)], cache, out)
    assert "loading" not in _one(_hero(out), "img").attrs


def test_build_site_album_hero_sizes_follow_cover_aspect(cache: Path, out: Path) -> None:
    write_original(cache, "p1", size=(1200, 400))
    _build([make_album("a", [make_photo("p1")])], cache, out)
    assert _one(_hero(out), "img").attrs.get("sizes") == "(max-width: 767px) 534vw, 169vw"


def _album_with_cover_file(cache: Path, count: int) -> Album:
    album = _album_of(cache, count)
    write_original(cache, "cov", color=(0, 0, 255), size=(1200, 800))
    return album.model_copy(update={"cover": make_photo("cov", "cover.jpg")})


def _album_with_identical_cover(cache: Path, count: int) -> Album:
    album = _album_of(cache, count)
    # Same pixels as p0, so the cover shares the first photo's content-hashed file.
    write_original(cache, "cov", color=(0, 80, 160))
    return album.model_copy(update={"cover": make_photo("cov", "cover.jpg")})


def _tile_labels(out: Path) -> list[str | None]:
    return [_one(tile, "a").attrs.get("aria-label") for tile in _tiles(out)]


def test_build_site_album_hero_link_opens_cover_file_display_jpeg_with_base_path(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    album = _album_with_cover_file(cache, 2)
    expected = _expected(cache / "originals" / "cov", tmp_path / "scratch")
    _build([album], cache, out, base_path="/portfolio/")
    link = _one(_hero(out), "a.album-hero-link")
    assert link.attrs.get("href") == f"/portfolio/images/{expected.display.jpeg_name}"


def test_build_site_album_hero_link_is_labelled_lightbox_link(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 2)], cache, out)
    attrs = _one(_hero(out), "a.album-hero-link").attrs
    assert (attrs.get("aria-label"), "data-lightbox" in attrs) == (
        "Open cover photo of Book One",
        True,
    )


def test_build_site_album_hero_link_wraps_cover_picture(cache: Path, out: Path) -> None:
    _build([_album_of(cache, 2)], cache, out)
    assert len(_one(_hero(out), "a.album-hero-link").find_all("picture img")) == 1


def test_build_site_album_hero_link_without_cover_file_is_first_tile_link(
    cache: Path, out: Path
) -> None:
    _build([_album_of(cache, 2)], cache, out)
    first_tile_href = _one(_tiles(out)[0], "a").attrs.get("href")
    assert _one(_hero(out), "a.album-hero-link").attrs.get("href") == first_tile_href


def test_build_site_album_tile_labels_with_cover_file_count_cover_first(
    cache: Path, out: Path
) -> None:
    _build([_album_with_cover_file(cache, 3)], cache, out)
    assert _tile_labels(out) == ["Open photo 2 of 4", "Open photo 3 of 4", "Open photo 4 of 4"]


def test_build_site_album_tile_labels_without_cover_file_count_photos(
    cache: Path, out: Path
) -> None:
    _build([_album_of(cache, 3)], cache, out)
    assert _tile_labels(out) == ["Open photo 1 of 3", "Open photo 2 of 3", "Open photo 3 of 3"]


def test_build_site_album_tile_labels_cover_file_identical_to_first_photo_count_photos(
    cache: Path, out: Path
) -> None:
    _build([_album_with_identical_cover(cache, 2)], cache, out)
    assert _tile_labels(out) == ["Open photo 1 of 2", "Open photo 2 of 2"]


# build_site: next-album banner


def test_build_site_pager_next_shows_next_album_cover(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    write_original(cache, "a-p1", color=(255, 0, 0))
    cover = write_original(cache, "b-p1", color=(0, 255, 0), size=(1200, 800))
    expected = _expected(cover, tmp_path / "scratch")
    albums = [make_album(slug, [make_photo(f"{slug}-p1")]) for slug in ("a", "b")]
    _build(albums, cache, out)
    image = _one(_page(out / "a" / "index.html"), "a.pager-next picture img")
    assert f"/images/{expected.display.jpeg_name} 1200w" in (image.attrs.get("srcset") or "")


def test_build_site_pager_next_cover_lazy(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    image = _one(_page(out / "a" / "index.html"), "a.pager-next img")
    assert image.attrs.get("loading") == "lazy"


def test_build_site_pager_prev_has_no_cover(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert _page(out / "a" / "index.html").find_all("a.pager-prev img") == []


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
    assert any("portfolio-theme" in script.text() for script in inline)


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_with_scripts_stored_theme_applied_before_stylesheet(
    cache: Path, out: Path, tmp_path: Path, page: str
) -> None:
    _build_with_scripts(cache, out, tmp_path)
    head = _one(_page(out / page), "head")
    order = [
        "theme" if element.tag == "script" and "portfolio-theme" in element.text() else "stylesheet"
        for element in head.descendants()
        if (element.tag == "script" and "src" not in element.attrs)
        or (element.tag == "link" and element.attrs.get("rel") == "stylesheet")
    ]
    assert order[:2] == ["theme", "stylesheet"]


# build_site: about and contact pages


def _about_json(lede: object, *paragraphs: object) -> str:
    return json.dumps({"lede": lede, "paragraphs": list(paragraphs)})


def _contact_json(email: str | None, *details: tuple[str, str]) -> str:
    return json.dumps(
        {"email": email, "details": [{"label": label, "value": value} for label, value in details]}
    )


ABOUT_LEDE = "I photograph quiet streets."
ABOUT_PARAGRAPHS = ["Mostly at night, on film.", "Prints on request."]
ABOUT_TEXT = _about_json(ABOUT_LEDE, "Mostly at night,\non film.", "Prints on request.")
CONTACT_TEXT = _contact_json(
    "hello@example.com",
    ("Instagram", "https://instagram.com/me/"),
    ("Based in", "Lisbon"),
)
UNPARSEABLE = "Email: hello@example.com\nnot JSON at all"
FORM_URL = "https://forms.example.test/f/reel"
ALL_PAGES = [
    "index.html",
    "work/index.html",
    "a/index.html",
    "about/index.html",
    "contact/index.html",
]


def _build_pages(
    cache: Path,
    out: Path,
    about: str | bytes | None = ABOUT_TEXT,
    contact: str | bytes | None = CONTACT_TEXT,
    contact_form_url: str | None = None,
    base_path: str = "/",
    albums: list[Album] | None = None,
    about_photo: Photo | None = None,
    contact_photo: Photo | None = None,
) -> int:
    """Build three albums plus the given about.json / contact.json texts (None = not in Drive)."""
    from portfolio.build import build_site
    from portfolio.models import Manifest

    about_file = contact_file = None
    if about is not None:
        write_text_original(cache, "t-about", about)
        about_file = make_text_file("t-about", "about.json")
    if contact is not None:
        write_text_original(cache, "t-contact", contact)
        contact_file = make_text_file("t-contact", "contact.json")
    manifest = Manifest(
        albums=_three_albums(cache) if albums is None else albums,
        about=about_file,
        contact=contact_file,
        about_photo=about_photo,
        contact_photo=contact_photo,
    )
    return build_site(manifest, cache, out, "Site", base_path, contact_form_url=contact_form_url)


def _nav_links(out: Path, page: str) -> list[Element]:
    return _one(_page(out / page), "header.site-header nav.site-nav").find_all("a")


def _nav_texts(out: Path, page: str) -> list[str]:
    return [link.text() for link in _nav_links(out, page)]


def _current_nav_texts(out: Path, page: str) -> list[str]:
    return [
        link.text() for link in _nav_links(out, page) if link.attrs.get("aria-current") == "page"
    ]


def _form(out: Path) -> Element:
    return _one(_page(out / "contact" / "index.html"), "form.contact-form")


def _form_field(out: Path, name: str) -> Element:
    fields = [
        element
        for element in _form(out).descendants()
        if element.tag in ("input", "textarea") and element.attrs.get("name") == name
    ]
    assert len(fields) == 1, f"expected exactly one field named {name!r}, found {len(fields)}"
    return fields[0]


def _facts(out: Path) -> list[tuple[str, str, str | None]]:
    """(label, value text, link href or None) for each `.contact-facts` entry."""
    items = _one(_page(out / "contact" / "index.html"), "ul.contact-facts").find_all("li")
    facts = []
    for item in items:
        value = _one(item, "span.contact-value")
        link = value.find("a")
        facts.append(
            (
                _one(item, "span.label").text(),
                value.text(),
                link.attrs.get("href") if link else None,
            )
        )
    return facts


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_text_page_present_writes_page(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out)
    assert (out / page / "index.html").is_file()


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_text_page_absent_writes_no_page(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out, about=None, contact=None)
    assert not (out / page).exists()


def test_build_site_only_contact_present_writes_no_about_page(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about=None)
    assert not (out / "about").exists()


def test_build_site_text_pages_do_not_change_album_count(cache: Path, out: Path) -> None:
    assert _build_pages(cache, out) == 3


def test_build_site_text_pages_written_without_albums(cache: Path, out: Path) -> None:
    _build_pages(cache, out, albums=[])
    assert (out / "about" / "index.html").is_file()


def test_build_site_text_page_removed_from_manifest_removed_on_rebuild(
    cache: Path, out: Path
) -> None:
    _build_pages(cache, out)
    _build_pages(cache, out, about=None)
    assert not (out / "about").exists()


# build_site: navigation


@pytest.mark.parametrize("page", ALL_PAGES)
def test_build_site_both_text_pages_nav_lists_work_about_contact(
    cache: Path, out: Path, page: str
) -> None:
    _build_pages(cache, out)
    assert _nav_texts(out, page) == ["Work", "About", "Contact"]


@pytest.mark.parametrize("page", ["index.html", "a/index.html", "contact/index.html"])
def test_build_site_no_about_page_nav_omits_about(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out, about=None)
    assert _nav_texts(out, page) == ["Work", "Contact"]


@pytest.mark.parametrize("page", ["index.html", "a/index.html", "about/index.html"])
def test_build_site_no_contact_page_nav_omits_contact(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out, contact=None)
    assert _nav_texts(out, page) == ["Work", "About"]


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_no_text_pages_nav_lists_only_work(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out, about=None, contact=None)
    assert _nav_texts(out, page) == ["Work"]


@pytest.mark.parametrize(
    ("page", "current"),
    [
        ("index.html", ["Work"]),
        ("work/index.html", ["Work"]),
        ("a/index.html", []),
        ("about/index.html", ["About"]),
        ("contact/index.html", ["Contact"]),
    ],
)
def test_build_site_nav_marks_only_current_page(
    cache: Path, out: Path, page: str, current: list[str]
) -> None:
    _build_pages(cache, out)
    assert _current_nav_texts(out, page) == current


@pytest.mark.parametrize("base_path", ["/", "/portfolio/"])
def test_build_site_nav_links_use_base_path(cache: Path, out: Path, base_path: str) -> None:
    _build_pages(cache, out, base_path=base_path)
    hrefs = [link.attrs.get("href") for link in _nav_links(out, "a/index.html")]
    assert hrefs == [f"{base_path}work/", f"{base_path}about/", f"{base_path}contact/"]


# build_site: about page


def test_build_site_about_page_title(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _one(_page(out / "about" / "index.html"), "title").text() == "About | Site"


def test_build_site_about_page_heading(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _one(_page(out / "about" / "index.html"), "h1.page-heading").text() == "About"


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_text_page_body_has_page_text_class(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out)
    assert "page-text" in _one(_page(out / page / "index.html"), "body").classes


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_text_page_has_no_meta_line(cache: Path, out: Path, page: str) -> None:
    _build_pages(cache, out)
    assert _page(out / page / "index.html").find_all(".page-meta") == []


def test_build_site_about_page_lede_is_first_paragraph(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    page = _page(out / "about" / "index.html")
    assert _one(page, "section.text-column p.lede").text() == ABOUT_LEDE


def test_build_site_about_page_prose_has_other_paragraphs(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    prose = _one(_page(out / "about" / "index.html"), "section.text-column div.prose")
    assert [p.text() for p in prose.find_all("p")] == ABOUT_PARAGRAPHS


def test_build_site_about_page_single_paragraph_has_no_prose(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about=_about_json("Just one line."))
    assert _page(out / "about" / "index.html").find_all("div.prose") == []


def test_build_site_about_page_signoff_links_contact(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    link = _one(_page(out / "about" / "index.html"), "section.text-column p.signoff a.text-link")
    assert (link.text(), link.attrs.get("href")) == ("Contact", "/contact/")


def test_build_site_about_page_signoff_link_uses_base_path(cache: Path, out: Path) -> None:
    _build_pages(cache, out, base_path="/portfolio/")
    link = _one(_page(out / "about" / "index.html"), "p.signoff a.text-link")
    assert link.attrs.get("href") == "/portfolio/contact/"


def test_build_site_about_page_without_contact_has_no_signoff(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=None)
    assert _page(out / "about" / "index.html").find_all("p.signoff") == []


def test_build_site_about_page_with_unparseable_contact_has_no_signoff(
    cache: Path, out: Path
) -> None:
    _build_pages(cache, out, contact=UNPARSEABLE)
    assert _page(out / "about" / "index.html").find_all("p.signoff") == []


# build_site: contact page


def test_build_site_contact_page_title(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _one(_page(out / "contact" / "index.html"), "title").text() == "Contact | Site"


def test_build_site_contact_page_heading(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _one(_page(out / "contact" / "index.html"), "h1.page-heading").text() == "Contact"


def test_build_site_contact_page_email_is_mailto_link(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    link = _one(_page(out / "contact" / "index.html"), "a.contact-email")
    assert (link.text(), link.attrs.get("href")) == (
        "hello@example.com",
        "mailto:hello@example.com",
    )


def test_build_site_contact_page_without_email_has_no_email_link(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json(None, ("Based in", "Lisbon")))
    assert _page(out / "contact" / "index.html").find_all("a.contact-email") == []


def test_build_site_contact_page_facts_list_entries_in_order(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _facts(out) == [
        ("Instagram", "instagram.com/me", "https://instagram.com/me/"),
        ("Based in", "Lisbon", None),
    ]


def test_build_site_contact_page_email_value_entry_links_mailto(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json(None, ("Studio", "studio@example.com")))
    assert _facts(out) == [("Studio", "studio@example.com", "mailto:studio@example.com")]


def test_build_site_contact_page_javascript_value_not_linked(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json(None, ("Website", "javascript:alert(1)")))
    assert _facts(out) == [("Website", "javascript:alert(1)", None)]


def test_build_site_contact_page_only_email_has_no_facts(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json("hello@example.com"))
    assert _page(out / "contact" / "index.html").find_all("ul.contact-facts") == []


# build_site: text pages with untrusted text

HTML_PAYLOAD = '<script>alert("x")</script> & <b>bold</b>'


def test_build_site_about_lede_html_escaped(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about=_about_json(HTML_PAYLOAD))
    assert _one(_page(out / "about" / "index.html"), "p.lede").text() == HTML_PAYLOAD


def test_build_site_about_prose_html_escaped(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about=_about_json("Lede.", HTML_PAYLOAD))
    prose = _one(_page(out / "about" / "index.html"), "div.prose")
    assert [p.text() for p in prose.find_all("p")] == [HTML_PAYLOAD]


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_text_page_html_payload_never_raw(cache: Path, out: Path, page: str) -> None:
    _build_pages(
        cache,
        out,
        about=_about_json(HTML_PAYLOAD),
        contact=_contact_json(None, ("Note", HTML_PAYLOAD)),
    )
    assert "<script>" not in _read(out / page / "index.html")


def test_build_site_contact_fact_label_and_value_html_escaped(cache: Path, out: Path) -> None:
    _build_pages(
        cache, out, contact=_contact_json(None, ("<i>Studio</i>", "<img src=x onerror=alert(1)>"))
    )
    assert _facts(out) == [("<i>Studio</i>", "<img src=x onerror=alert(1)>", None)]


def test_build_site_contact_link_with_quote_cannot_add_attributes(cache: Path, out: Path) -> None:
    url = 'https://example.com/"onmouseover="alert(1)'
    _build_pages(cache, out, contact=_contact_json(None, ("Site", url)))
    link = _one(_page(out / "contact" / "index.html"), "span.contact-value a")
    assert "onmouseover" not in link.attrs


def test_build_site_contact_link_with_quote_keeps_href_intact(cache: Path, out: Path) -> None:
    url = 'https://example.com/"onmouseover="alert(1)'
    _build_pages(cache, out, contact=_contact_json(None, ("Site", url)))
    link = _one(_page(out / "contact" / "index.html"), "span.contact-value a")
    assert link.attrs.get("href") == url


# build_site: contact form


def test_build_site_contact_form_url_unset_has_no_form(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert _page(out / "contact" / "index.html").find_all("form") == []


def test_build_site_contact_form_url_unset_has_no_message_section(cache: Path, out: Path) -> None:
    _build_pages(cache, out)
    assert "Send a message" not in _read(out / "contact" / "index.html")


def test_build_site_contact_form_posts_to_configured_url(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    form = _form(out)
    assert (form.attrs.get("action"), form.attrs.get("method")) == (FORM_URL, "post")


def test_build_site_contact_form_is_in_labelled_section(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    section = _one(_page(out / "contact" / "index.html"), "section.contact-form-section")
    heading = _one(section, "h2.section-heading")
    assert (section.attrs.get("aria-labelledby"), heading.attrs.get("id"), heading.text()) == (
        "contact-form-heading",
        "contact-form-heading",
        "Send a message",
    )


def test_build_site_contact_form_field_names_in_order(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    names = [
        element.attrs.get("name")
        for element in _form(out).descendants()
        if element.tag in ("input", "textarea")
    ]
    assert names == ["name", "email", "message", "_gotcha"]


@pytest.mark.parametrize("name", ["name", "email", "message"])
def test_build_site_contact_form_visible_fields_required(cache: Path, out: Path, name: str) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    assert "required" in _form_field(out, name).attrs


def test_build_site_contact_form_email_field_has_email_type(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    assert _form_field(out, "email").attrs.get("type") == "email"


def test_build_site_contact_form_message_is_textarea(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    assert _form_field(out, "message").tag == "textarea"


@pytest.mark.parametrize(
    ("name", "label"), [("name", "Name"), ("email", "Email"), ("message", "Message")]
)
def test_build_site_contact_form_fields_wrapped_in_labels(
    cache: Path, out: Path, name: str, label: str
) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    labels = [
        element
        for element in _form(out).find_all("label")
        if any(child.attrs.get("name") == name for child in element.descendants())
    ]
    assert [_one(element, "span.label").text() for element in labels] == [label]


def test_build_site_contact_form_honeypot_inside_hidden_trap(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    trap = _one(_form(out), "div.form-trap")
    names = [element.attrs.get("name") for element in trap.find_all("input")]
    assert (trap.attrs.get("aria-hidden"), names) == ("true", ["_gotcha"])


def test_build_site_contact_form_honeypot_not_focusable_or_required(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    honeypot = _form_field(out, "_gotcha")
    assert (honeypot.attrs.get("tabindex"), "required" in honeypot.attrs) == ("-1", False)


def test_build_site_contact_form_has_submit_button(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    button = _one(_form(out), "button")
    assert (button.attrs.get("type"), button.text()) == ("submit", "Send message")


def test_build_site_contact_form_url_never_on_other_pages(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact_form_url=FORM_URL)
    pages = [path for path in out.rglob("*.html") if path.parent.name != "contact"]
    assert not any(FORM_URL in _read(path) for path in pages)


# build_site: text page failures


@pytest.mark.parametrize("field", ["about", "contact"])
def test_build_site_text_page_original_missing_raises_build_error(
    cache: Path, out: Path, field: str
) -> None:
    from portfolio.build import BuildError, build_site
    from portfolio.models import Manifest

    manifest = Manifest(
        albums=_three_albums(cache), **{field: make_text_file(f"t-{field}", f"{field}.json")}
    )
    with pytest.raises(
        BuildError, match=rf"'{field}\.json' is missing from .*Run `portfolio sync` again"
    ):
        build_site(manifest, cache, out, "Site")


def test_build_site_text_page_missing_message_uses_drive_name(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError, build_site
    from portfolio.models import Manifest

    manifest = Manifest(albums=[], about=make_text_file("t-about", "About.JSON"))
    with pytest.raises(BuildError, match=r"'About\.JSON' is missing from"):
        build_site(manifest, cache, out, "Site")


def test_build_site_text_page_missing_keeps_previous_output(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError, build_site
    from portfolio.models import Manifest

    _build_pages(cache, out)
    before = _snapshot(out)
    (cache / "originals" / "t-about").unlink()
    manifest = Manifest(albums=_three_albums(cache), about=make_text_file("t-about", "about.json"))
    with pytest.raises(BuildError):
        build_site(manifest, cache, out, "Site")
    assert _snapshot(out) == before


def test_build_site_text_page_unsafe_id_raises_build_error(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError, build_site
    from portfolio.models import Manifest

    manifest = Manifest(albums=[], contact=make_text_file("../evil", "contact.json"))
    with pytest.raises(BuildError):
        build_site(manifest, cache, out, "Site")


@pytest.mark.parametrize(
    "about",
    [
        "   \n\n\t\n",
        '{"lede": "x",',
        '{"paragraphs": ["no lede"]}',
        '["lede"]',
        b"caf\xe9 \xff\xfe",
        b"a" * (64 * 1024 + 1),
    ],
    ids=["blank", "invalid-json", "missing-lede", "array", "latin1", "huge"],
)
def test_build_site_unusable_about_text_omits_page(
    cache: Path, out: Path, about: str | bytes
) -> None:
    _build_pages(cache, out, about=about)
    assert not (out / "about").exists()


def test_build_site_unusable_about_text_still_builds_albums(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about="   \n")
    assert (out / "a" / "index.html").is_file()


def test_build_site_unusable_about_text_drops_nav_link(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about="   \n")
    assert _nav_texts(out, "index.html") == ["Work", "Contact"]


def test_build_site_unusable_contact_text_omits_page(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json("not-an-email"))
    assert not (out / "contact").exists()


def test_build_site_unusable_contact_text_logs_warning(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact=UNPARSEABLE)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


# build_site: CONTACT_FORM_URL without a usable contact page

FORM_WITHOUT_CONTACT_WARNING = (
    "CONTACT_FORM_URL is set but there is no usable contact.json; the form is not shown."
)


def _form_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING and "CONTACT_FORM_URL" in record.getMessage()
    ]


def test_build_site_form_url_without_contact_file_warns(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact=None, contact_form_url=FORM_URL)
    assert _form_warnings(caplog) == [FORM_WITHOUT_CONTACT_WARNING]


def test_build_site_form_url_with_unparseable_contact_warns(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact=UNPARSEABLE, contact_form_url=FORM_URL)
    assert _form_warnings(caplog) == [FORM_WITHOUT_CONTACT_WARNING]


def test_build_site_form_url_without_contact_still_builds(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=None, contact_form_url=FORM_URL)
    assert (out / "index.html").is_file()


def test_build_site_form_url_with_contact_page_does_not_warn(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact_form_url=FORM_URL)
    assert _form_warnings(caplog) == []


def test_build_site_form_url_unset_without_contact_does_not_warn(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact=None)
    assert _form_warnings(caplog) == []


@pytest.mark.parametrize("contact", [None, UNPARSEABLE], ids=["missing", "unparseable"])
def test_build_site_form_url_never_logged(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture, contact: str | None
) -> None:
    caplog.set_level(logging.DEBUG)
    _build_pages(cache, out, contact=contact, contact_form_url=FORM_URL)
    assert not any("forms.example.test" in record.getMessage() for record in caplog.records)


def test_build_site_invalid_contact_json_still_builds_other_pages(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json(None, ("", "x")))
    assert (out / "about" / "index.html").is_file()


def test_build_site_invalid_contact_json_omits_page(cache: Path, out: Path) -> None:
    _build_pages(cache, out, contact=_contact_json(None, ("", "x")))
    assert not (out / "contact").exists()


def test_build_site_invalid_json_warning_names_drive_file(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from portfolio.build import build_site
    from portfolio.models import Manifest

    caplog.set_level(logging.WARNING)
    write_text_original(cache, "t-about", '{"lede": "x",')
    build_site(Manifest(albums=[], about=make_text_file("t-about", "About.JSON")), cache, out, "S")
    assert any("Skipping 'About.JSON': not valid JSON" in message for message in caplog.messages)


def test_build_site_form_url_with_empty_contact_json_warns(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    _build_pages(cache, out, contact=_contact_json(""), contact_form_url=FORM_URL)
    assert _form_warnings(caplog) == [FORM_WITHOUT_CONTACT_WARNING]


LONG_NUMBER_ABOUT = '{"lede": "x", "_comment": ' + "9" * 5000 + "}"


def test_build_site_about_with_overlong_number_omits_page(cache: Path, out: Path) -> None:
    _build_pages(cache, out, about=LONG_NUMBER_ABOUT)
    assert not (out / "about").exists()


def test_build_site_about_with_overlong_number_still_builds(cache: Path, out: Path) -> None:
    assert _build_pages(cache, out, about=LONG_NUMBER_ABOUT) == 3


# build_site: about and contact photos (split layout)


SPLIT_CLASSES = {"split", "split-photo", "split-text"}


def _page_photo(cache: Path, page: str, size: tuple[int, int] = (40, 30)) -> Photo:
    """`<page>.jpg` from the Drive root, with its cached original (id `i-<page>`)."""
    write_original(cache, f"i-{page}", size=size)
    return make_photo(f"i-{page}", f"{page}.jpg")


def _build_page_photo(
    cache: Path, out: Path, page: str, photo: Photo, base_path: str = "/", with_text: bool = True
) -> None:
    """Build with `photo` as the About or Contact photo; `with_text=False` drops its json."""
    _build_pages(
        cache,
        out,
        about=ABOUT_TEXT if with_text or page != "about" else None,
        contact=CONTACT_TEXT if with_text or page != "contact" else None,
        base_path=base_path,
        about_photo=photo if page == "about" else None,
        contact_photo=photo if page == "contact" else None,
    )


def _build_with_photo(cache: Path, out: Path, page: str, base_path: str = "/") -> None:
    _build_page_photo(cache, out, page, _page_photo(cache, page), base_path)


def _split_img(out: Path, page: str) -> Element:
    return _one(_page(out / page / "index.html"), "div.split figure.split-photo img")


def _split_markup(out: Path, page: str) -> list[Element]:
    root = _page(out / page / "index.html")
    return [element for element in root.descendants() if SPLIT_CLASSES & set(element.classes)]


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (2000, 1000, "(max-width: 767px) 150vw, 113vw"),
        (1000, 2000, "(max-width: 767px) 100vw, 50vw"),
    ],
)
def test_split_photo_sizes_returns_crop_width_per_box(
    width: int, height: int, expected: str
) -> None:
    from portfolio.build import split_photo_sizes
    from portfolio.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=width, height=height)
    assert split_photo_sizes(variant) == expected


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_page_photo_text_inside_split_text(cache: Path, out: Path, page: str) -> None:
    _build_with_photo(cache, out, page)
    root = _page(out / page / "index.html")
    assert _one(root, "div.split div.split-text h1.page-heading").text() == page.title()


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_page_photo_img_decorative_and_eager(cache: Path, out: Path, page: str) -> None:
    _build_with_photo(cache, out, page)
    img = _split_img(out, page)
    assert (img.attrs.get("alt"), "loading" in img.attrs) == ("", False)


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_page_photo_image_file_written(cache: Path, out: Path, page: str) -> None:
    _build_with_photo(cache, out, page, base_path="/portfolio/")
    src = _split_img(out, page).attrs["src"] or ""
    assert (out / src.removeprefix("/portfolio/")).is_file()


def test_build_site_page_photo_sizes_from_display_variant(
    cache: Path, out: Path, tmp_path: Path
) -> None:
    from portfolio.build import split_photo_sizes

    photo = _page_photo(cache, "about", size=(80, 30))
    _build_pages(cache, out, about_photo=photo)
    expected = _expected(cache / "originals" / "i-about", tmp_path / "scratch")
    assert _split_img(out, "about").attrs["sizes"] == split_photo_sizes(expected.display)


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_page_without_photo_has_no_split_markup(
    cache: Path, out: Path, page: str
) -> None:
    _build_pages(cache, out)
    assert _split_markup(out, page) == []


def test_build_site_about_photo_does_not_split_contact_page(cache: Path, out: Path) -> None:
    _build_with_photo(cache, out, "about")
    assert _split_markup(out, "contact") == []


def test_build_site_corrupt_page_photo_logs_warning(
    cache: Path, out: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    write_corrupt_original(cache, "i-about")
    _build_pages(cache, out, about_photo=make_photo("i-about", "about.jpg"))
    assert any(message.startswith("Skipping 'about.jpg'") for message in caplog.messages)


def test_build_site_corrupt_page_photo_falls_back_to_centred_layout(cache: Path, out: Path) -> None:
    write_corrupt_original(cache, "i-contact")
    _build_pages(cache, out, contact_photo=make_photo("i-contact", "contact.jpg"))
    assert _split_markup(out, "contact") == []


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_photo_of_unwritten_page_not_processed(
    cache: Path, out: Path, page: str
) -> None:
    # The original is absent: processing it would raise BuildError.
    _build_page_photo(cache, out, page, make_photo(f"i-{page}"), with_text=False)
    assert not (out / page).exists()


@pytest.mark.parametrize("page", ["about", "contact"])
def test_build_site_page_photo_original_missing_raises_build_error(
    cache: Path, out: Path, page: str
) -> None:
    from portfolio.build import BuildError

    photo = make_photo(f"i-{page}", f"{page}.jpg")
    with pytest.raises(
        BuildError, match=rf"'{page}\.jpg' is missing from .*Run `portfolio sync` again"
    ):
        _build_page_photo(cache, out, page, photo)


def test_build_site_page_photo_unsafe_id_raises_build_error(cache: Path, out: Path) -> None:
    from portfolio.build import BuildError

    with pytest.raises(BuildError):
        _build_pages(cache, out, about_photo=make_photo("../evil", "about.jpg"))
