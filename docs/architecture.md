# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums and photos, downloads only what changed
  (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`): makes content-hashed thumbnails and display images
  (WebP + JPEG), then renders Jinja2 templates into `dist/`.
- **serve**: `dist/` is plain static files.

Drive is never called at page-view time, and Drive links never appear in the output.

`drive.py` defines a `DriveClient` protocol. `GoogleDriveClient` is the real adapter; tests use
an in-memory fake in `tests/fixtures/fake_drive.py`.
