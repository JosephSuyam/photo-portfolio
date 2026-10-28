# Architecture

```
Google Drive --sync--> .cache/ + manifest.json --build--> dist/ --serve/deploy--> browser
```

- **sync** (`sync.py`, via `drive.py`): lists albums, photos, and the root `about.json` / `contact.json`, downloads only what changed (`md5Checksum`/`modifiedTime`), and removes cache entries deleted from Drive.
- **build** (`build.py`, `images.py`, `pages.py`, `scripts.py`): compiles `src/portfolio/ts/` with the project's local `tsc` into a temporary folder, makes content-hashed thumbnails and display images (WebP + JPEG), then renders Jinja2 templates into `dist/`. Scripts:
  - `theme.ts`: light/dark toggle in the header
  - `lightbox.ts`: album photo viewer
- **serve**: `dist/` is plain static files. `portfolio serve` previews them on localhost.

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
  index.html, work/index.html   album index: one full-screen scene per album
  <slug>/index.html             album page: cover hero, photo mosaic, lightbox, next-album banner
  about/index.html              About page (only with a usable about.json)
  contact/index.html            Contact page (only with a usable contact.json)
  images/<hash>.webp|.jpg       thumbnails (600px wide) and display images (2000px long edge)
  static/                       site.css, compiled JavaScript (theme.js, lightbox.js)
  api/drive-webhook.mjs         Vercel function for instant redeploys (see setup.md)
  .portfolio-build                   marker: this directory was written by `portfolio build`
```

- Slugs must be lowercase letters and digits with single hyphens, unique, and not `work`, `static`, `images`, `about`, `contact`, or `api`; otherwise the build fails.
- A photo that can't be decoded is skipped with a warning. A page file that is too large, not UTF-8, not valid JSON, or the wrong shape leaves its page out with a warning. A missing original fails the build.
- The site is built in `.dist.staging/` and swapped in only on success, so a failed build leaves the previous `dist/` as it was. Build refuses to replace a non-empty `dist/` without the `.portfolio-build` marker.
- Derived images carry no EXIF or other source metadata (only the ICC color profile).
- Every build re-processes every photo; caching derived images is a planned optimization.

Drive is never called at page-view time, and Drive links never appear in the output.

`drive.py` defines a `DriveClient` protocol. `GoogleDriveClient` is the real adapter; tests use an in-memory fake in `tests/fixtures/fake_drive.py`.

## Every page

- `base.html`: header (site title; "Work", "About", "Contact" links, the last two only when that page exists; theme toggle) and a centered footer (site title, © build year). The header is one row: the bold site title on the left, the spaced uppercase menu and the theme toggle on the right. On About and Contact it scrolls with the page in the theme colours. On the index and album pages it is transparent and white over the photos: fixed on the index, scrolling away with the cover on album pages. The footer stays at the bottom of short pages.
- **Type**: one family, `--sans` (Helvetica Neue, Helvetica, Arial), with no web fonts. Headlines (page and album headings, scene titles, the next-album title) are weight 900, uppercase, and tightly set; the menu, footer, counts, and labels are 12-13px spaced capitals.
- **Theme**: light by default. Dark tokens apply when `<html data-theme="dark">` is set, or when the OS prefers dark and `data-theme` isn't `"light"` (`site.css`). `theme.ts` unhides the toggle. A click flips the current effective theme, sets `data-theme`, and stores it in `localStorage["portfolio-theme"]`. Before setting it, the click adds `theme-transition` to `<html>` for 1.5 s (`THEME_TRANSITION_MS`, kept in sync with `site.css`; another click restarts the timer). The colour tokens (`--bg`, `--fg`, `--muted`, `--line`) are registered with `@property`, so that class cross-fades them on the root alone and everything using them follows; per-element colour transitions would restart every frame under an animating parent and lag. Page loads and OS changes switch instantly, and with `prefers-reduced-motion: reduce` the click does too. A small inline script in `<head>` applies the stored theme before first paint. The toggle and the inline script are rendered only when the build has scripts. Without JavaScript the OS setting applies and the toggle stays hidden.
- **Colours**: light is white (`--bg #ffffff`, `--fg #1a1a1a`), dark is black (`--bg #000000`, `--fg #ffffff`). Text set on photos (header, scenes, album cover, next-album banner) is always white, with a shadow and a dark scrim at the photo's top and bottom, in both themes.
- **Phones** (<= 767px): one column on every page. The header has less padding; a title or menu too long for the screen wraps instead of overflowing.

## About and Contact

`pages.py` reads the root JSON files ([format](drive-conventions.md#about-and-contact-pages)) and validates them with pydantic models (`AboutFile`, `ContactFile`, `ContactDetail`; unknown keys ignored, strings stripped, no type coercion). Validation warnings name the field (`details.1.label`) but never echo the file's contents. All Drive text is autoescaped; only `http(s)://` and email values become links.

Both pages are a centered column (max 640px).

- **About**: "About" heading, the lede centered in large type, then the paragraphs. With a Contact page it ends with a centered "Commissions and print enquiries: Contact" link.
- **Contact**: "Contact" heading, the first email as a large, underlined, centered `mailto:` link, then the other entries (label above value) in a centered row that wraps.
- **Form**: only when `CONTACT_FORM_URL` is set ([Setup](setup.md#contact-form-optional)). A plain HTML POST of `name`, `email`, `message`, and a visually hidden honeypot `_gotcha` straight to the form service; no JavaScript.

## Album index

- One full-screen scene per album, in manifest (Drive) order, under a visually hidden "Work" heading. With no albums there are no scenes.
- Each scene is a link to its album: the cover cropped to fill the screen, "01 / 03" (album number / total) top right, and bottom left the title (heavy uppercase, 5vw; 9vw on phones) over "N photos — View album →".
- Scrolling snaps scene by scene; the footer snaps too, so it stays reachable. With a mouse or pen, hovering a scene zooms its cover to 1.03 over 1.2 s. With `prefers-reduced-motion: reduce`, neither.
- **`sizes`**: `cover_sizes(variant)` gives the `sizes` value for every full-width cover (scenes, the album cover, the next-album banner). It assumes a 16:9 box (`SCENE_ASPECT`), 9:16 on phones (`PHONE_SCENE_ASPECT`); a photo wider than the box is cropped at the sides, so it is requested wider than 100vw.

## Album page

- **Cover**: the album cover fills 88% of the screen height, with the title (heavy uppercase, 5vw; 9vw on phones) and photo count bottom left. The cover links to its display JPEG and opens in the lightbox; the title and count text don't, the rest of the cover does.
- **Mosaic**: below the cover, the photos in a gap-free grid of tiles that crop them (`object-fit: cover`), 4px apart, edge to edge. 4 columns on desktop, 2 up to 1024px (`TABLET_MAX_WIDTH_PX`), 1 on phones. Rows are as tall as a column is wide, so a `small` tile is 1x1, `big` 2x2, `wide` 2x1, and `full` spans the row, 2 rows tall (1 row on tablets). On phones every tile is one square. `mosaic_shapes(count)` gives each photo its shape: blocks of six that close a 4x3 area, the big tile alternating sides:

  ```
  1 1 2 3      shapes: big, small, small, big, small, small
  1 1 4 4
  5 6 4 4
  ```

  The last 1-5 photos use a remainder that closes too, so the grid never has holes: `full`; `big, big`; `big, wide, wide`; `big, small, small, wide`; `big, small, small, big, wide`. A negative count raises `ValueError`. `MOSAIC_TILES` in `build.py` holds each shape's width (desktop, tablet) and aspect; keep it in sync with `site.css`.
- **`sizes`**: `mosaic_sizes(variant, shape)` uses the same crop rule per breakpoint. For example a 3000x2000 photo in a `small` tile: `(max-width: 767px) 150vw, (max-width: 1024px) 75vw, 38vw`.
- Tiles fade in, and zoom on hover (mouse or pen) or keyboard focus; neither with `prefers-reduced-motion: reduce`.
- **Lightbox**: the cover and each tile link to their display JPEG. `lightbox.ts` turns a plain click into a `<dialog>` viewer that shows the photo whole (prev/next buttons, arrow keys, swipe, Escape/close/backdrop to close, "n / total" counter). A separate `cover.*` file comes first ("1 / n+1"); a cover that is also one of the photos opens at that photo and isn't shown twice. Tile labels ("Open photo 2 of 5") count the same way. The dialog is rendered only when the build has scripts; without JavaScript the link opens the JPEG. All compiled scripts load on every page and do nothing where their elements are missing. The lightbox stays dark in both themes.
- **Pager**: below the photos, a full-width "Next album" banner (the next album's cover, darkened, with its title centered) and a "← Previous" link with that album's title in the banner's top-left corner. Both wrap around (`previous_album_index()`, `next_album_index()`). With two albums both links go to the other album. With one album there is no pager.
