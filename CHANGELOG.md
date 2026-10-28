# Changelog

## Unreleased

- "Cinematic" redesign: heavy uppercase Helvetica titles replace Bodoni, and the header sits over the photos. White text on photos keeps a dark fade behind it in both themes; About and Contact follow the theme. Bodoni Moda (`static/fonts/`) and the hover-preview script are removed.
- Album index: one full-screen cover per album (16:9, 9:16 on phones), scroll-snapped one album at a time, with the title, photo count, and "01 / 03". Snapping is off with reduced motion. Replaces the featured album and cover cards.
- Album pages: open on the cover filling the screen; clicking it opens the lightbox (a separate `cover.*` file comes first as "1 / n+1"). Clicks on the title and count text don't open it, and the text stays selectable. Without JavaScript the cover links to its JPEG. Album titles are 5vw (9vw on phones), the same as on the index.
- Album pages: a mosaic of square-cropped photos replaces the justified rows: 4 columns on desktop, 2 on tablets, 1 on phones, with large 2x2 tiles on alternating sides. The last tiles stretch to fill the final row, so it has no holes. The lightbox still shows each photo whole.
- Album pages end on a large "Next album" banner with "← Previous" in its corner.
- "Portfolio" redesign: a white page (black in dark mode) with Bodoni display headlines over Helvetica text. Every page opens with the site title centered over a spaced uppercase menu, with the theme toggle at the top right. The 1.5 s theme cross-fade is unchanged.
- Album index: "Work" and the counts centered, then the first album as a full-bleed 21:9 feature (4:5 on phones) with its label, title, and count in white over the photo. The other albums follow edge to edge, two per row in 3:2 frames; a lone last card spans the row at 3:1, the same height. Titles and counts sit on the photos, and hovering a card zooms it slightly (not with reduced motion). Hovering or focusing a card still previews it in the feature.
- Album pages: justified rows replace the mosaic. Every photo is shown whole at its own aspect ratio, rows share one height, and the last row isn't stretched. Phones get one column.
- About and Contact are centered columns. The Contact form still appears only when `CONTACT_FORM_URL` is set.
- Bodoni Moda is self-hosted under `static/fonts/` (SIL Open Font License 1.1, `OFL.txt`) and loads with `font-display: swap` and a relative URL, so it works under a base path. No font CDN is called when a page is viewed.
- About and Contact pages (`/about/`, `/contact/`) from optional `about.json` and `contact.json` files in the Drive root (samples in `docs/examples/`). About: a large `lede`, then `paragraphs`. Contact: the `email` shown large, then `details` as labelled entries; `http(s)://` values and email addresses become links. A missing file leaves out the page and its nav link; invalid JSON or a wrong shape skips the page with a warning naming the field. Album folders named "About" or "Contact" now get `about-2` / `contact-2`.
- Optional `CONTACT_FORM_URL` (https only) adds a "Send a message" form that posts to a form service such as Formspree. Unset, the Contact page shows links only.
- Header nav: "Work", then "About" and "Contact" when those pages exist. The footer stays at the bottom of short pages.
- Clicking the theme toggle cross-fades the colours over 1.5 s. Page loads and OS theme changes still switch instantly, and so does the toggle when reduced motion is set.
- Light and dark themes: dark mode follows the OS setting, or a header toggle that is remembered in this browser and applied before the page paints. Without JavaScript the OS setting applies and the toggle is hidden. Every page has the same header (site title, "Work", theme toggle) and a centered footer (site title, © build year). The header scrolls with the page.
- Album index (`/`, `/work/`): a "Work" heading with "N albums · M photographs". The first album in Drive order is featured, labelled "Latest album", and the rest follow as cover cards with title and photo count. Hovering a card (mouse or pen) or reaching it with the keyboard previews that album in the feature. Replaces the horizontal strip and sideways wheel scrolling.
- Album pages: title and photo count, then the photos. "Next" is replaced by a Previous/Next pager, and both links wrap around.
- Phones: one column on every page.
- Album pages scroll vertically (photos fade in and zoom on hover unless reduced motion is set). Clicking a photo opens a lightbox with previous/next buttons, arrow keys, swipe, and an "n / total" counter. Without JavaScript the photo links to its display JPEG.
- `portfolio sync`: incremental, read-only sync of albums and photos from Google Drive.
- Site script is now TypeScript, compiled by `portfolio build`; Playwright browser tests in `e2e/`.
- `portfolio serve` accepts many parallel image requests (the default backlog of 5 refused some).
- Responsive `srcset` images (WebP with JPEG fallback) on every page.
- `portfolio build`: renders the cached manifest into `dist/` with WebP/JPEG thumbnails and display images, metadata stripped, built in a staging directory and swapped in atomically.
- Project scaffold: package layout, settings loading, Drive client interface and read-only adapter, base templates, CLI with `serve`.
