"""Build a sample site from generated photos and serve it for the Playwright tests.

Usage: uv run python e2e/serve_fixture.py --port 8123

The fixture has three albums (the first with an explicit cover.* file) of gradient images in
mixed orientations. It never touches Google Drive or the network.
"""

import argparse
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from reel.build import build_site
from reel.models import Album, Manifest, Photo, original_path
from reel.scripts import PROJECT_ROOT, compile_scripts
from reel.server import make_preview_server

FIXTURE_DIR = PROJECT_ROOT / ".tmp" / "e2e"
SITE_TITLE = "Reel E2E"
_MODIFIED = datetime(2026, 1, 1, tzinfo=UTC)

# (album title, slug, [(width, height), ...], has cover file)
ALBUMS = [
    ("Book I", "book-i", [(1600, 2400), (2400, 1600), (1600, 2400)], True),
    ("Book II", "book-ii", [(2400, 1600), (1600, 2400)], False),
    ("Portraits", "portraits", [(1600, 2000), (1600, 2000), (2400, 1600), (1600, 2400)], False),
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
    return Manifest(albums=albums)


def build_fixture_site() -> Path:
    """Rebuild the fixture site from scratch and return its output directory."""
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
    cache, dist = FIXTURE_DIR / "cache", FIXTURE_DIR / "dist"
    manifest = make_manifest(cache)
    (cache / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="reel-scripts-") as scripts_dir:
        compile_scripts(Path(scripts_dir))
        build_site(manifest, cache, dist, SITE_TITLE, scripts_dir=Path(scripts_dir))
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
