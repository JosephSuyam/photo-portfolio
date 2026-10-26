# reel

A static photographer portfolio generated from a Google Drive folder. Each subfolder of the root folder becomes an album; each image inside it becomes a photo. Optional `about.json` and `contact.json` in the root add About and Contact pages (samples in [docs/examples/](docs/examples/)), and the optional `CONTACT_FORM_URL` setting adds a message form to the Contact page. See [Drive folder conventions](docs/drive-conventions.md) and [Setup](docs/setup.md#contact-form-optional).

The look follows [reel.format.com](https://reel.format.com/): white or black themes, Bodoni headlines, a full-bleed feature of the latest album over a grid of cover cards, and album pages of uncropped photos in justified rows.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 20+, then `uv sync` and `npm install`.
2. Copy `.env.example` to `.env` and fill it in (see [docs/setup.md](docs/setup.md)).
3. `uv run reel sync`, then `uv run reel build`, then `uv run reel serve` and open http://localhost:8000.

## Run locally

1. `uv run reel sync` downloads new or changed photos from Drive into `.cache/`.
2. `uv run reel build` compiles the site's TypeScript and renders `dist/`.
3. `uv run reel serve` serves `dist/` at http://localhost:8000. Stop it with `Ctrl+C`.

`serve` doesn't sync or build, so re-run steps 1 and 2 after changing photos in Drive (`uv run reel all` does both).

While editing templates, CSS, or TypeScript, `uv run reel watch` rebuilds on every change and reloads open pages. Add `--port 8000` if `reel serve` isn't already running.

`serve` options:

- `--port 9000`: listen on a different port.
- `--directory path/to/site`: serve a folder other than `dist/`.

The server listens on `localhost` only. It is for previewing, not for hosting.

## Development

- Lint: `uv run ruff check .`
- Typecheck: `uv run mypy src`
- Test: `uv run pytest`
- TypeScript typecheck: `npm run typecheck`
- Browser tests: `npm run test:e2e` (Playwright, using your installed Microsoft Edge; builds a sample site from generated images, so it needs no Drive access)

## Docs

- [Setup](docs/setup.md)
- [Drive folder conventions](docs/drive-conventions.md)
- [Architecture](docs/architecture.md)

## Credits

Headlines use [Bodoni Moda](https://fonts.google.com/specimen/Bodoni+Moda), self-hosted in `src/reel/static/fonts/` and licensed under the SIL Open Font License 1.1 (see `src/reel/static/fonts/OFL.txt`).
