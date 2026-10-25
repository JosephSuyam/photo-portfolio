# Changelog

## Unreleased

- "Editorial Light" redesign of the whole site: a light page with serif headlines. Dark mode
  follows the OS setting, or a header toggle that is remembered in this browser and applied
  before the page paints. Without JavaScript the OS setting applies and the toggle is hidden.
  Every page has the same header (site title, "Work", theme toggle) and a centered footer
  (site title, © build year). The header scrolls with the page.
- Album index (`/`, `/work/`): a "Work" heading with "N albums · M photographs". The first
  album in Drive order gets a wide feature card labelled "Latest album". The rest fill a grid
  of equal-height cards (cover, title, photo count) in rows of 4, and the last rows stretch
  so there are no gaps. Hovering a card (mouse or pen) or reaching it with the keyboard previews that album in the feature card.
  Replaces the horizontal strip and sideways wheel scrolling.
- Album pages: serif title and photo count, then the mosaic. "Next" is replaced by a
  Previous/Next pager, and both links wrap around.
- Phones: one column on every page.
- Album pages scroll vertically, with a 4-column mosaic of cropped tiles (hover zoom, fade-in
  unless reduced motion is set). Clicking a photo opens a lightbox with previous/next
  buttons, arrow keys, swipe, and an "n / total" counter. Without JavaScript the photo links
  to its display JPEG. Phones get one column of uncropped photos.
- `reel sync`: incremental, read-only sync of albums and photos from Google Drive.
- Site script is now TypeScript, compiled by `reel build`; Playwright browser tests in `e2e/`.
- `reel serve` accepts many parallel image requests (the default backlog of 5 refused some).
- Responsive `srcset` images (WebP with JPEG fallback) on every page.
- `reel build`: renders the cached manifest into `dist/` with WebP/JPEG thumbnails and
  display images, metadata stripped, built in a staging directory and swapped in atomically.
- Project scaffold: package layout, settings loading, Drive client interface and read-only
  adapter, base templates, CLI with `serve`.
