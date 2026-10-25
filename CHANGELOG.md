# Changelog

## Unreleased

- Album pages scroll vertically: bold uppercase title, a 4-column mosaic of cropped tiles
  (hover zoom, fade-in unless reduced motion is set), then "Next". Clicking a photo opens a
  lightbox with previous/next buttons, arrow keys, swipe, and an "n / total" counter; without
  JavaScript the photo links to its display JPEG. Phones get one column of uncropped photos.
  The header on album pages scrolls away instead of staying fixed.
- `reel sync`: incremental, read-only sync of albums and photos from Google Drive.
- Site script is now TypeScript, compiled by `reel build`; Playwright browser tests in `e2e/`.
- `reel serve` accepts many parallel image requests (the default backlog of 5 refused some).
- Site UI follows reel.format.com: dark theme, a full-height horizontal strip for the album
  index (wheel scrolls sideways), two-column grid on phones, responsive `srcset` images.
- `reel build`: renders the cached manifest into `dist/` with WebP/JPEG thumbnails and
  display images, metadata stripped, built in a staging directory and swapped in atomically.
- Project scaffold: package layout, settings loading, Drive client interface and read-only
  adapter, base templates, CLI with `serve`.
