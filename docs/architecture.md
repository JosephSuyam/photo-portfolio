# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums and photos, downloads only what changed
  (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`, `scripts.py`): compiles `src/reel/ts/` (`site.ts`:
  wheel scrolls the index sideways; `lightbox.ts`: album photo viewer) with the
  project's local `tsc` into a temporary folder, makes content-hashed thumbnails and display images
  (WebP + JPEG), then renders Jinja2 templates into `dist/`.
- **serve**: `dist/` is plain static files. `reel serve` previews them on localhost.

## Sync

- Calls `get_folder(root)` first, because Drive lists an unshared folder as empty.
- Album titles, slugs, order, and covers follow [Drive folder conventions](drive-conventions.md).
- Downloads only files whose `md5Checksum` or `modifiedTime` changed (or that are missing
  locally), removes originals no longer in Drive, then writes the manifest atomically. If a
  download fails, the previous manifest is kept.

## Cache contract (sync -> build)

- `.cache/manifest.json`: `{"albums": [Album, ...]}` (see `models.py`), already ordered,
  titled, and slugged by sync. Build renders albums in this order.
- `.cache/originals/<file_id>`: the downloaded original for each photo. File IDs must match
  `[A-Za-z0-9_-]+`.

## Build output

```
dist/
  index.html, work/index.html   album index (horizontal strip of covers)
  <slug>/index.html             album page: title, photo mosaic, lightbox, "Next" (wraps to the first album)
  images/<hash>.webp|.jpg       thumbnails (600px wide) and display images (2000px long edge)
  static/                       CSS and compiled JavaScript (site.js, lightbox.js)
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

## Album page

- **Mosaic**: `mosaic_shapes()` in `build.py` gives each photo a tile shape on a 4-column grid
  of square cells: `small` (1x1), `wide` (2x1), `big` (2x2), `full` (4x2). Each group of 4
  photos fills a 4x2 block, with the big tile alternating sides:

  ```
  group 1, 3, ...   [big, small, small, wide]
  group 2, 4, ...   [wide, big, small, small]
  leftover 1        [full]
  leftover 2        [big, big]
  leftover 3        [big, wide, wide] after 0, 2, 4, ... groups; else [wide, big, wide]
  ```

  So the mosaic never has holes. Tiles crop with `object-fit: cover`; `mosaic_sizes()` picks
  the `sizes` value from the shape and the photo's aspect ratio. The `MOSAIC_*` constants in
  `build.py` and the grid in `site.css` must be kept in sync.
- **Phones** (<= 767px): one column, photos uncropped at their natural aspect ratio.
- **Lightbox**: each tile links to its display JPEG. `lightbox.ts` turns a plain click into a
  `<dialog>` viewer (prev/next buttons, arrow keys, swipe, Escape/close/backdrop to close,
  "n / total" counter). The dialog is rendered only when the build has scripts; without
  JavaScript the link opens the JPEG. All compiled scripts load on every page and do nothing
  where their elements are missing.
- **Header**: on album pages it scrolls away with the page instead of staying fixed.
