# Changelog

## Unreleased

- `reel sync`: incremental, read-only sync of albums and photos from Google Drive.
- Site script is now TypeScript, compiled by `reel build`; Playwright browser tests in `e2e/`.
- `reel serve` accepts many parallel image requests (the default backlog of 5 refused some).
- Site UI follows reel.format.com: dark theme, full-height horizontal strips for the album
  index and album pages (wheel scrolls sideways), two-column grid on phones, responsive
  `srcset` images.
- `reel build`: renders the cached manifest into `dist/` with WebP/JPEG thumbnails and
  display images, metadata stripped, built in a staging directory and swapped in atomically.
- Project scaffold: package layout, settings loading, Drive client interface and read-only
  adapter, base templates, CLI with `serve`.
