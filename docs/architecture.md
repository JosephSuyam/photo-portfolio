# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums, photos, and the root `about.json` /
  `contact.json`, downloads only what changed
  (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`, `pages.py`, `scripts.py`): compiles `src/reel/ts/` with the
  project's local `tsc` into a temporary folder, makes content-hashed thumbnails and display
  images (WebP + JPEG), then renders Jinja2 templates into `dist/`. Scripts:
  - `theme.ts`: light/dark toggle in the header
  - `album-preview.ts`: index hover/focus preview in the feature card
  - `lightbox.ts`: album photo viewer
- **serve**: `dist/` is plain static files. `reel serve` previews them on localhost.

## Sync

- Calls `get_folder(root)` first, because Drive lists an unshared folder as empty.
- Album titles, slugs, order, and covers follow [Drive folder conventions](drive-conventions.md).
- Downloads only files whose `md5Checksum` or `modifiedTime` changed (or that are missing
  locally), removes originals no longer in Drive, then writes the manifest atomically. If a
  download fails, the previous manifest is kept.

## Cache contract (sync -> build)

- `.cache/manifest.json`: `{"albums": [Album, ...], "about": TextFile | null, "contact":
  TextFile | null}` (see `models.py`), already ordered, titled, and slugged by sync. Build
  renders albums in this order. `about`/`contact` are optional, so older manifests without
  them still load.
- `.cache/originals/<file_id>`: the downloaded original for each photo and page file, with
  the same incremental download and stale-removal rules. File IDs must match
  `[A-Za-z0-9_-]+`.

## Build output

```
dist/
  index.html, work/index.html   album index: "Work", feature card, grid of album cards
  <slug>/index.html             album page: title, photo count, mosaic, lightbox, Previous/Next pager
  about/index.html              About page (only with a usable about.json)
  contact/index.html            Contact page (only with a usable contact.json)
  images/<hash>.webp|.jpg       thumbnails (600px wide) and display images (2000px long edge)
  static/                       site.css and compiled JavaScript (theme.js, album-preview.js, lightbox.js)
  .reel-build                   marker: this directory was written by `reel build`
```

- Slugs must be lowercase letters and digits with single hyphens, unique, and not `work`,
  `static`, `images`, `about`, or `contact`; otherwise the build fails.
- A photo that can't be decoded is skipped with a warning. A page file that is too large,
  not UTF-8, not valid JSON, or the wrong shape leaves its page out with a warning. A
  missing original fails the build.
- The site is built in `.dist.staging/` and swapped in only on success, so a failed build
  leaves the previous `dist/` as it was. Build refuses to replace a non-empty `dist/` without
  the `.reel-build` marker.
- Derived images carry no EXIF or other source metadata (only the ICC color profile).
- Every build re-processes every photo; caching derived images is a planned optimization.

Drive is never called at page-view time, and Drive links never appear in the output.

`drive.py` defines a `DriveClient` protocol. `GoogleDriveClient` is the real adapter; tests use
an in-memory fake in `tests/fixtures/fake_drive.py`.

## Every page

- `base.html`: header (site title; "Work", "About", "Contact" links, the last two only when
  that page exists; theme toggle) and a centered footer (site title, © build year). The
  header scrolls with the page. The footer stays at the bottom of short pages.
- **Theme**: light by default. Dark tokens apply when `<html data-theme="dark">` is set, or
  when the OS prefers dark and `data-theme` isn't `"light"` (`site.css`). `theme.ts` unhides
  the toggle. A click flips the current effective theme, sets `data-theme`, and stores it in
  `localStorage["reel-theme"]`. Before setting it, the click adds `theme-transition` to
  `<html>` for 1.5 s (`THEME_TRANSITION_MS`, kept in sync with `site.css`; another click
  restarts the timer). The colour tokens (`--bg`, `--fg`, `--muted`, `--line`) are registered
  with `@property`, so that class cross-fades them on the root alone and everything using
  them follows; per-element colour transitions would restart every frame under an animating
  parent and lag. Page loads and OS changes switch instantly, and with
  `prefers-reduced-motion: reduce` the click does too. A small inline script in `<head>`
  applies the stored theme before first paint. The toggle and the inline script are rendered
  only when the build has scripts. Without JavaScript the OS setting applies and the toggle
  stays hidden.
- **Phones** (<= 767px): one column on every page. When the header doesn't fit on one line,
  the nav wraps onto its own row below the site title; the title itself never breaks.

## About and Contact

`pages.py` reads the root JSON files ([format](drive-conventions.md#about-and-contact-pages))
and validates them with pydantic models (`AboutFile`, `ContactFile`, `ContactDetail`; unknown
keys ignored, strings stripped, no type coercion). Validation warnings name the field
(`details.1.label`) but never echo the file's contents. All Drive text is autoescaped; only
`http(s)://` and email values become links.

- **About**: "About" heading, the lede in large serif, then the paragraphs in a narrow
  column. With a Contact page it ends with a "Commissions and print enquiries: Contact" link.
- **Contact**: "Contact" heading, the first email as a large `mailto:` link, then the other
  entries (label above value) in as many columns of at least 220px as fit (about four on a
  laptop screen; one on phones).
- **Form**: only when `CONTACT_FORM_URL` is set ([Setup](setup.md#contact-form-optional)).
  A plain HTML POST of `name`, `email`, `message`, and a visually hidden honeypot `_gotcha`
  straight to the form service; no JavaScript.

## Album index

- "Work" heading and "N albums · M photographs" (singular for 1).
- The first album, in manifest (Drive) order, gets a feature card labelled "Latest album":
  a 16:9 cover, 66vw wide on desktop (4:5 with the text below on phones). With one album the
  feature card is the only card. With none, there is no feature card and no grid.
- The other albums go into a 12-column grid. `album_card_spans()` in `build.py` gives each
  card a column span so that every row is full:

  ```
  full rows         4 cards, span 3 each
  1 card in total   [12]
  2 left            [6, 6]
  3 left            [4, 4, 4]
  1 left            the last 5 cards become [4, 4, 4] + [6, 6]
  e.g. 6 cards      [3, 3, 3, 3, 6, 6]
  ```

  `site.css` gives every card frame the same height (a 4:5 frame in a row of four, via
  container units); `card_aspect()` approximates each span's frame shape for `sizes`
  (4:5 for span 3, 16:15 for 4, 8:5 for 6, 16:5 for 12). `cover_sizes()` gives the `sizes` value for the feature and the cards (the
  mosaic uses it too). The `FEATURE_*`, `GRID_COLUMNS`, `CARDS_PER_ROW`, and
  `LAST_ROW_SPANS` constants must stay in sync with `site.css`.
- **Preview**: `album-preview.ts` shows a card's album in the feature card (cover, title,
  count, link, and the cover's own feature `sizes` from `data-feature-sizes`) when a mouse
  or pen hovers it or the keyboard focuses it, and hides "Latest album" while it does. Taps
  on touch screens just open the album. When the pointer leaves the albums section (and
  keyboard focus isn't inside it), or focus leaves it, the first album comes back, also
  after Back restores the page. Moving from a card up to the feature card keeps the
  preview, so the previewed album can be clicked.

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
  where their elements are missing. The lightbox stays dark in both themes.
- **Pager**: a serif title and photo count above the mosaic. Below it, "← Previous" and
  "Next →" link to the neighboring albums and wrap around (`previous_album_index()`,
  `next_album_index()`). With two albums both links go to the other album. With one album
  there is no pager.
