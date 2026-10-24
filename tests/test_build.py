import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from reel.build import make_environment
from reel.models import Album
from tests.fixtures.albums import (
    make_album,
    make_photo,
    write_corrupt_original,
    write_original,
)

if TYPE_CHECKING:
    from reel.images import ProcessedPhoto

# Names added by the `reel build` feature are imported inside tests so the template tests
# keep running independently of the build implementation.

PAYLOAD = "<script>x</script>"
ESCAPED = "&lt;script&gt;x&lt;/script&gt;"


def test_album_template_untrusted_title_escaped() -> None:
    template = make_environment().get_template("album.html")
    html = template.render(
        site_title="Site",
        base_path="/",
        album={"title": PAYLOAD, "photos": []},
        next_album=None,
    )
    assert ESCAPED in html and PAYLOAD not in html


def test_index_template_untrusted_title_escaped() -> None:
    template = make_environment().get_template("index.html")
    html = template.render(
        site_title="Site",
        base_path="/",
        albums=[{"title": PAYLOAD, "slug": "x", "cover": {"src": "c.jpg"}}],
    )
    assert ESCAPED in html and PAYLOAD not in html


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
    html = _read(out / "index.html")
    positions = [html.index(f'href="/{slug}/"') for slug in ("c", "a", "b")]
    assert positions == sorted(positions)


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


def test_build_site_album_page_next_links_following_album(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert 'href="/b/"' in _read(out / "a" / "index.html")


def test_build_site_album_page_last_next_wraps_to_first(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert 'href="/a/"' in _read(out / "c" / "index.html")


def test_build_site_single_album_has_no_next_link(cache: Path, out: Path) -> None:
    _build([_album_with_photo(cache, "a", (255, 0, 0))], cache, out)
    assert "next-album" not in _read(out / "a" / "index.html")


def test_build_site_next_skips_unpublished_album(cache: Path, out: Path) -> None:
    a = _album_with_photo(cache, "a", (255, 0, 0))
    c = _album_with_photo(cache, "c", (0, 0, 255))
    _build([a, make_album("empty", []), c], cache, out)
    assert 'href="/c/"' in _read(out / "a" / "index.html")


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


@pytest.mark.parametrize("page", ["index.html", "a/index.html"])
def test_build_site_untrusted_title_escaped(cache: Path, out: Path, page: str) -> None:
    write_original(cache, "p1")
    _build([make_album("a", [make_photo("p1")], title=PAYLOAD_TITLE)], cache, out)
    assert "<script>" not in _read(out / page)


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


def test_sizes_portrait_desktop_width_follows_aspect_ratio() -> None:
    from reel.build import sizes
    from reel.images import ImageVariant

    variant = ImageVariant(webp_name="x.webp", jpeg_name="x.jpg", width=1000, height=2000)
    assert sizes(variant, height_vh=80, mobile_width_vw=80) == "(max-width: 767px) 80vw, 40vh"


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
    (scripts / "site.js").write_text("console.log('hi');", encoding="utf-8")
    build_site(Manifest(albums=_three_albums(cache)), cache, out, "Site", scripts_dir=scripts)


def test_build_site_copies_compiled_scripts(cache: Path, out: Path, tmp_path: Path) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert (out / "static" / "site.js").is_file()


def test_build_site_pages_load_compiled_scripts(cache: Path, out: Path, tmp_path: Path) -> None:
    _build_with_scripts(cache, out, tmp_path)
    assert '<script src="/static/site.js" defer>' in _read(out / "a" / "index.html")


def test_build_site_without_scripts_has_no_script_tag(cache: Path, out: Path) -> None:
    _build(_three_albums(cache), cache, out)
    assert "<script" not in _read(out / "index.html")


def test_base_path_from_url_space_in_path_is_percent_encoded() -> None:
    from reel.build import base_path_from_url

    assert base_path_from_url("https://x.com/my portfolio") == "/my%20portfolio/"


def test_base_path_from_url_already_encoded_path_not_double_encoded() -> None:
    from reel.build import base_path_from_url

    assert base_path_from_url("https://x.com/my%20portfolio/") == "/my%20portfolio/"
