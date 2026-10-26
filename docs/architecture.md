# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums, photos, and the root `about.json` / `contact.json`, downloads only what changed (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`, `pages.py`, `scripts.py`): compiles `src/reel/ts/` with the project's local `tsc` into a temporary folder, makes content-hashed thumbnails and display images (WebP + JPEG), then renders Jinja2 templates into `dist/`. Scripts:
  - `theme.ts`: light/dark toggle in the header
  - `album-preview.ts`: index hover/focus preview in the feature card
  - `lightbox.ts`: album photo viewer
- **serve**: `dist/` is plain static files. `reel serve` previews them on localhost.

## Sync

- Calls `get_folder(root)` first, because Drive lists an unshared folder as empty.
- Album titles, slugs, order, and covers follow [Drive folder conventions](drive-conventions.md).
- Downloads only files whose `md5Checksum` or `modifiedTime` changed (or that are missing locally), removes originals no longer in Drive, then writes the manifest atomically. If a download fails, the previous manifest is kept.

## Cache contract (sync -> build)

- `.cache/manifest.json`: `{"albums": [Album, ...], "about": TextFile | null, "contact": TextFile | null}` (see `models.py`), already ordered, titled, and slugged by sync. Build renders albums in this order. `about`/`contact` are optional, so older manifests without them still load.
- `.cache/originals/<file_id>`: the downloaded original for each photo and page file, with the same incremental download and stale-removal rules. File IDs must match `[A-Za-z0-9_-]+`.

## Build output

```
dist/
  index.html, work/index.html   album index: "Work", feature card, grid of album cards
  <slug>/index.html             album page: title, photo count, justified rows, lightbox, Previous/Next pager
  about/index.html              About page (only with a usable about.json)
  contact/index.html            Contact page (only with a usable contact.json)
  images/<hash>.webp|.jpg       thumbnails (600px wide) and display images (2000px long edge)
  static/                       site.css, compiled JavaScript (theme.js, album-preview.js, lightbox.js)
  static/fonts/                 bodoni-moda-latin.woff2 and its licence, OFL.txt
  .reel-build                   marker: this directory was written by `reel build`
```

- Slugs must be lowercase letters and digits with single hyphens, unique, and not `work`, `static`, `images`, `about`, or `contact`; otherwise the build fails.
- A photo that can't be decoded is skipped with a warning. A page file that is too large, not UTF-8, not valid JSON, or the wrong shape leaves its page out with a warning. A missing original fails the build.
- The site is built in `.dist.staging/` and swapped in only on success, so a failed build leaves the previous `dist/` as it was. Build refuses to replace a non-empty `dist/` without the `.reel-build` marker.
- Derived images carry no EXIF or other source metadata (only the ICC color profile).
- Every build re-processes every photo; caching derived images is a planned optimization.

Drive is never called at page-view time, and Drive links never appear in the output.

`drive.py` defines a `DriveClient` protocol. `GoogleDriveClient` is the real adapter; tests use an in-memory fake in `tests/fixtures/fake_drive.py`.

## Every page

- `base.html`: header (site title; "Work", "About", "Contact" links, the last two only when that page exists; theme toggle) and a centered footer (site title, © build year). The header is a centered column: the site title in Bodoni over a spaced uppercase menu, with the theme toggle at its top right. It scrolls with the page. The footer stays at the bottom of short pages.
- **Type**: headlines (site title, page and album headings, card and feature titles, the About lede, the Contact email, pager titles) use `--display`; body text uses `--sans` (Helvetica Neue, Helvetica, Arial).

  ```css
  --display: "Bodoni Moda", "Bodoni MT", Didot, Georgia, serif;
  ```

  Bodoni Moda (latin subset, variable weight 400-900) is self-hosted: `src/reel/static/fonts/` is copied with the rest of `static/` into `dist/static/fonts/`, and `site.css` loads it with `@font-face` from the relative URL `fonts/bodoni-moda-latin.woff2`, so it works under a base path such as `/portfolio/`. `font-display: swap` shows the fallback until it loads. No font CDN is called at page-view time. The font came from the Google Fonts API (fonts.gstatic.com) and is licensed under the SIL Open Font License 1.1 (`OFL.txt` beside it, from github.com/google/fonts, `ofl/bodonimoda`).
- **Theme**: light by default. Dark tokens apply when `<html data-theme="dark">` is set, or when the OS prefers dark and `data-theme` isn't `"light"` (`site.css`). `theme.ts` unhides the toggle. A click flips the current effective theme, sets `data-theme`, and stores it in `localStorage["reel-theme"]`. Before setting it, the click adds `theme-transition` to `<html>` for 1.5 s (`THEME_TRANSITION_MS`, kept in sync with `site.css`; another click restarts the timer). The colour tokens (`--bg`, `--fg`, `--muted`, `--line`) are registered with `@property`, so that class cross-fades them on the root alone and everything using them follows; per-element colour transitions would restart every frame under an animating parent and lag. Page loads and OS changes switch instantly, and with `prefers-reduced-motion: reduce` the click does too. A small inline script in `<head>` applies the stored theme before first paint. The toggle and the inline script are rendered only when the build has scripts. Without JavaScript the OS setting applies and the toggle stays hidden.
- **Colours**: light is white (`--bg #ffffff`, `--fg #1a1a1a`), dark is black (`--bg #000000`, `--fg #f2f2f2`). Text set on photos (feature and cards) is always white over a dark gradient, in both themes.
- **Phones** (<= 767px): one column on every page. The header stays a centered column with a smaller title; a title too long for the screen wraps instead of overflowing.

## About and Contact

`pages.py` reads the root JSON files ([format](drive-conventions.md#about-and-contact-pages)) and validates them with pydantic models (`AboutFile`, `ContactFile`, `ContactDetail`; unknown keys ignored, strings stripped, no type coercion). Validation warnings name the field (`details.1.label`) but never echo the file's contents. All Drive text is autoescaped; only `http(s)://` and email values become links.

Both pages are a centered column (max 640px).

- **About**: "About" heading, the lede centered in large Bodoni, then the paragraphs. With a Contact page it ends with a centered "Commissions and print enquiries: Contact" link.
- **Contact**: "Contact" heading, the first email as a large, underlined, centered `mailto:` link, then the other entries (label above value) in a centered row that wraps.
- **Form**: only when `CONTACT_FORM_URL` is set ([Setup](setup.md#contact-form-optional)). A plain HTML POST of `name`, `email`, `message`, and a visually hidden honeypot `_gotcha` straight to the form service; no JavaScript.

## Album index

- "Work" heading and "N albums · M photographs" (singular for 1), both centered.
- The first album, in manifest (Drive) order, gets a full-bleed feature: its cover across the whole viewport width at 21:9 (4:5 on phones), with "Latest album", the title, and the photo count overlaid bottom-left in white. With one album the feature is all there is. With none, there is no feature and no grid.
- The other albums go edge to edge (no page gutter) into a 12-column grid with 4px gaps, two cards per row. `album_card_spans()` in `build.py` gives each card a column span:

  ```
  0 cards           []
  1 card            [12]
  even count        [6, 6, ...]
  odd count         [6] * (n - 1) + [12]   e.g. 3 -> [6, 6, 12], 5 -> [6, 6, 6, 6, 12]
  ```

  A negative count raises `ValueError`. Every frame is as tall as a 3:2 frame in a row of two (via container units), so a lone last card is 3:1. `card_aspect(span)` is `3/2 * span / 6` (3:2 for span 6, 3:1 for 12) and feeds `cover_sizes()`, which gives the `sizes` value for the feature and the cards. Phones get one column of 3:2 cards (spans ignored).
- Each card's title (Bodoni) and photo count are overlaid bottom-left in white on a dark gradient. With a mouse or pen, hovering a card zooms its photo to 1.03 over 0.6 s; not with `prefers-reduced-motion: reduce`.
- `FEATURE_WIDTH_VW = 100`, `FEATURE_ASPECT = 21/9`, `GRID_COLUMNS = 12`, `CARDS_PER_ROW = 2`, and `CARD_FRAME_ASPECT = 3/2` in `build.py` must stay in sync with `site.css`.
- **Preview**: `album-preview.ts` shows a card's album in the feature card (cover, title, count, link, and the cover's own feature `sizes` from `data-feature-sizes`) when a mouse or pen hovers it or the keyboard focuses it, and hides "Latest album" while it does. Taps on touch screens just open the album. When the pointer leaves the albums section (and keyboard focus isn't inside it), or focus leaves it, the first album comes back, also after Back restores the page. Moving from a card up to the feature card keeps the preview, so the previewed album can be clicked.

## Album page

- **Heading**: the album title (Bodoni) and photo count, centered.
- **Justified rows**: photos flow in rows of equal height that fill the width, each at its own aspect ratio, so nothing is cropped. Each `li.tile` carries its ratio (display width / height, 4 decimals):

  ```html
  <li class="tile" style="--ratio: 1.5000">   <!-- a 3000x2000 photo -->
  ```

  In `site.css` a tile's flex basis is `ratio * 28vw` (a row is about 28vw tall before it stretches) and it grows in proportion to its ratio; a spacer after the last tile keeps the last row from stretching. `ROW_HEIGHT_VW = 28` in `build.py` must match.
- **`sizes`**: `justified_sizes()` assumes a row stretches to at most twice its base height: `min(100, ceil(ratio * 28 * 2))vw` on desktop, `100vw` on phones. For example 3000x2000 -> 84vw, 1000x1000 -> 56vw, 2000x864 -> 100vw, 1080x1929 -> 32vw.
- Tiles fade in, and zoom on hover (mouse or pen) or keyboard focus; neither with `prefers-reduced-motion: reduce`.
- **Phones** (<= 767px): one column, each photo full width at its own ratio.
- **Lightbox**: each tile links to its display JPEG. `lightbox.ts` turns a plain click into a `<dialog>` viewer (prev/next buttons, arrow keys, swipe, Escape/close/backdrop to close, "n / total" counter). The dialog is rendered only when the build has scripts; without JavaScript the link opens the JPEG. All compiled scripts load on every page and do nothing where their elements are missing. The lightbox stays dark in both themes.
- **Pager**: below the photos, "← Previous" and "Next →" (album titles in Bodoni, side by side; stacked on phones) link to the neighboring albums and wrap around (`previous_album_index()`, `next_album_index()`). With two albums both links go to the other album. With one album there is no pager.
