# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums and photos, downloads only what changed
  (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`): makes content-hashed thumbnails and display images
  (WebP + JPEG), then renders Jinja2 templates into `dist/`.
- **serve**: `dist/` is plain static files.

## Cache contract (sync -> build)

- `.cache/manifest.json`: `{"albums": [Album, ...]}` (see `models.py`), already ordered,
  titled, and slugged by sync. Build renders albums in this order.
- `.cache/originals/<file_id>`: the downloaded original for each photo. File IDs must match
  `[A-Za-z0-9_-]+`.

## Build output

```
dist/
  index.html, work/index.html   album index
  <slug>/index.html             album page, "Next" wraps to the first album
  images/<hash>.webp|.jpg       thumbnails (600px wide) and display images (2000px long edge)
  static/                       CSS
  .reel-build                   marker: this directory was written by `reel build`
```

- Slugs must be lowercase letters and digits with single hyphens, unique, and not `work`,
  `static`, or `images`; otherwise the build fails.
- A photo that can't be decoded is skipped with a warning. A missing original fails the build.
- The site is built in `.dist.staging/` and swapped in only on success, so a failed build
  leaves the previous `dist/` as it was. Build refuses to replace a non-empty `dist/` without
  the `.reel-build` marker.
- Derived images carry no EXIF or other source metadata (only the ICC color profile).
- Every build re-processes every photo; caching derived images is a planned optimization.

Drive is never called at page-view time, and Drive links never appear in the output.

`drive.py` defines a `DriveClient` protocol. `GoogleDriveClient` is the real adapter; tests use
an in-memory fake in `tests/fixtures/fake_drive.py`.
