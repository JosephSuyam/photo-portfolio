# Changelog

## Unreleased

- About and Contact pages (`/about/`, `/contact/`) from optional `about.txt` and
  `contact.txt` files in the Drive root (samples in `docs/examples/`). About: a large lede,
  then paragraphs. Contact: the first email shown large, then labelled entries; `http(s)://`
  values and email addresses become links. A missing or empty file leaves out the page and
  its nav link. Album folders named "About" or "Contact" now get `about-2` / `contact-2`.
- Optional `CONTACT_FORM_URL` (https only) adds a "Send a message" form that posts to a form
  service such as Formspree. Unset, the Contact page shows links only.
- Header nav: "Work", then "About" and "Contact" when those pages exist. On phones the nav
  wraps below the site title instead of the title breaking. The footer stays at the bottom
  of short pages.
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
