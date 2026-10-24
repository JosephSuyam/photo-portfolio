# reel

A static photographer portfolio generated from a Google Drive folder. Each subfolder of the
root folder becomes an album; each image inside it becomes a photo.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/), then `uv sync`.
2. Copy `.env.example` to `.env` and fill it in (see [docs/setup.md](docs/setup.md)).
3. `uv run reel sync`, then `uv run reel build`, then `uv run reel serve` and open http://localhost:8000.

## Run locally

1. `uv run reel build` renders `.cache/manifest.json` and the cached originals into `dist/`.
2. `uv run reel serve` serves `dist/` at http://localhost:8000. Stop it with `Ctrl+C`.

`serve` doesn't build anything, so run `build` again after changes.

> `reel sync` is not implemented yet, so nothing writes `.cache/` from Drive. Until it lands,
> `build` stops with "Run `reel sync` first" unless you provide a manifest yourself (see
> [docs/architecture.md](docs/architecture.md) for its format).

`serve` options:

- `--port 9000`: listen on a different port.
- `--directory path/to/site`: serve a folder other than `dist/`.

The server listens on `localhost` only. It is for previewing, not for hosting.

## Development

- Lint: `uv run ruff check .`
- Typecheck: `uv run mypy src`
- Test: `uv run pytest`

## Docs

- [Setup](docs/setup.md)
- [Drive folder conventions](docs/drive-conventions.md)
- [Architecture](docs/architecture.md)
