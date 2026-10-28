"""Build a sample site from generated photos and serve it for the Playwright tests.

Usage: uv run python e2e/serve_fixture.py --port 8123

The fixture has six albums (the first with an explicit cover.* file) of gradient images in
mixed orientations. "Landscapes" has eleven photos of mixed ratios, a mosaic block of six and a
five-photo remainder. The fifth album has a very long title, to catch horizontal overflow.
"Still Life", the last, has a single photo, shown as one full-width mosaic tile.
Every (size, colour) pair is unique, so no two photos share a content-hashed file.
The root also has an about.json (a lede and two paragraphs) and a Contact.json (an email, a
link, and a plain entry), and the contact page gets a form posting to a fake https URL that
the tests intercept. It never touches Google Drive or the network.
"""

import argparse
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from portfolio.build import build_site
from portfolio.models import Album, Manifest, Photo, TextFile, original_path
from portfolio.scripts import PROJECT_ROOT, compile_scripts
from portfolio.server import make_preview_server

FIXTURE_DIR = PROJECT_ROOT / ".tmp" / "e2e"
SITE_TITLE = "Reel E2E"
_MODIFIED = datetime(2026, 1, 1, tzinfo=UTC)
CONTACT_FORM_URL = "https://forms.example.test/f/reel-e2e"
# about.json is written with CRLF line endings and a BOM, as a Windows editor might save it.
ABOUT_JSON = (
    "\ufeff{\r\n"
    '  "_comment": "Fixture about page; keys like this one are ignored.",\r\n'
    '  "lede": "I photograph quiet places at the edges of cities, mostly at dusk.",\r\n'
    '  "paragraphs": [\r\n'
    '    "Most of this work is made on medium-format film and printed by hand\\n'
    'in a small darkroom.",\r\n'
    '    "Prints and commissions are available on request."\r\n'
    "  ]\r\n"
    "}\r\n"
)
CONTACT_JSON = json.dumps(
    {
        "_comment": "Fixture contact page.",
        "email": "studio@example.test",
        "details": [
            {"label": "Instagram", "value": "https://instagram.example.test/reel-e2e/"},
            {"label": "Based in", "value": "Lisbon, Portugal"},
        ],
    },
    indent=2,
)

# (album title, slug, [(width, height), ...], has cover file)
ALBUMS = [
    ("Book I", "book-i", [(1600, 2400), (2400, 1600), (1600, 2400)], True),
    ("Book II", "book-ii", [(2600, 1600), (1700, 2400)], False),
    ("Portraits", "portraits", [(1600, 2100), (1600, 2000), (2400, 1700), (1600, 2500)], False),
    (
        "Landscapes",
        "landscapes",
        [
            (2400, 1600),
            (1600, 2400),
            (1800, 1800),
            (2400, 1200),
            (1600, 2000),
            (2400, 1600),
            (1200, 1800),
            (1800, 1200),
            (2000, 1500),
            (1500, 2000),
            (2200, 1400),
        ],
        False,
    ),
    (
        "The Long Road North Through Every Small Coastal Town In The Middle Of Deep Winter",
        "the-long-road-north",
        [(2300, 1500), (1500, 2300)],
        False,
    ),
    ("Still Life", "still-life", [(2000, 1400)], False),
]
_COLORS = [
    ((200, 80, 60), (40, 30, 80)),
    ((40, 140, 120), (240, 220, 160)),
    ((30, 60, 160), (220, 120, 40)),
]


def _gradient(path: Path, size: tuple[int, int], colors: tuple[tuple[int, ...], ...]) -> None:
    top, bottom = colors
    column = Image.new("RGB", (1, 256))
    for y in range(256):
        column.putpixel(
            (0, y), tuple(t + (b - t) * y // 255 for t, b in zip(top, bottom, strict=True))
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    column.resize(size).save(path, "JPEG", quality=90)


def _photo(cache: Path, file_id: str, name: str, size: tuple[int, int], index: int) -> Photo:
    _gradient(original_path(cache, file_id), size, _COLORS[index % len(_COLORS)])
    return Photo(file_id=file_id, name=name, mime_type="image/jpeg", modified_time=_MODIFIED)


def make_manifest(cache: Path) -> Manifest:
    """Write generated originals into `cache` and return the matching manifest."""
    albums = []
    for a, (title, slug, sizes, has_cover) in enumerate(ALBUMS):
        photos = [
            _photo(cache, f"{slug}-{p}", f"{p + 1:03}.jpg", size, a + p)
            for p, size in enumerate(sizes)
        ]
        cover = (
            _photo(cache, f"{slug}-cover", "cover.jpg", (2000, 2000), a + 2) if has_cover else None
        )
        albums.append(
            Album(folder_id=slug, name=title, title=title, slug=slug, photos=photos, cover=cover)
        )
    return Manifest(
        albums=albums,
        about=_text_file(cache, "page-about", "about.json", ABOUT_JSON),
        contact=_text_file(cache, "page-contact", "Contact.json", CONTACT_JSON),
    )


def _text_file(cache: Path, file_id: str, name: str, text: str) -> TextFile:
    original_path(cache, file_id).write_bytes(text.encode("utf-8"))
    return TextFile(
        file_id=file_id, name=name, mime_type="application/json", modified_time=_MODIFIED
    )


def build_fixture_site() -> Path:
    """Rebuild the fixture site from scratch and return its output directory."""
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
    cache, dist = FIXTURE_DIR / "cache", FIXTURE_DIR / "dist"
    manifest = make_manifest(cache)
    (cache / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="portfolio-scripts-") as scripts_dir:
        compile_scripts(Path(scripts_dir))
        build_site(
            manifest,
            cache,
            dist,
            SITE_TITLE,
            scripts_dir=Path(scripts_dir),
            contact_form_url=CONTACT_FORM_URL,
        )
    return dist


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8123)
    port = parser.parse_args().port
    dist = build_fixture_site()
    with make_preview_server(dist, port) as server:
        print(f"Serving fixture site on http://localhost:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
