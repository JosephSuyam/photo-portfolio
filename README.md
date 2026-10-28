# portfolio

A static photographer portfolio generated from a Google Drive folder. Each subfolder of the root folder becomes an album; each image inside it becomes a photo. Optional `about.json` and `contact.json` in the root add About and Contact pages (samples in [docs/examples/](docs/examples/)), and the optional `CONTACT_FORM_URL` setting adds a message form to the Contact page. See [Drive folder conventions](docs/drive-conventions.md) and [Setup](docs/setup.md#contact-form-optional).

The look is image-first: white or black themes, heavy uppercase Helvetica titles set on full-screen photos, an index of one full-screen scene per album, and album pages that open with the cover, then a gap-free mosaic of cropped photos that open whole in a lightbox.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 20+, then `uv sync` and `npm install`.
2. Copy `.env.example` to `.env` and fill it in (see [docs/setup.md](docs/setup.md)).
3. `uv run portfolio sync`, then `uv run portfolio build`, then `uv run portfolio serve` and open http://localhost:8000.

## Run locally

1. `uv run portfolio sync` downloads new or changed photos from Drive into `.cache/`.
2. `uv run portfolio build` compiles the site's TypeScript and renders `dist/`.
3. `uv run portfolio serve` serves `dist/` at http://localhost:8000. Stop it with `Ctrl+C`.

`serve` doesn't sync or build, so re-run steps 1 and 2 after changing photos in Drive (`uv run portfolio all` does both).

While editing templates, CSS, or TypeScript, `uv run portfolio watch` rebuilds on every change and reloads open pages. Add `--port 8000` if `portfolio serve` isn't already running.

`uv run portfolio subscribe` points Drive change notifications at the deployed site for 24 hours, for instant redeploys (see [Setup](docs/setup.md#instant-redeploy-on-drive-changes-optional)).

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
