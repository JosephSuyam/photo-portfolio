# reel

A static photographer portfolio generated from a Google Drive folder. Each subfolder of the
root folder becomes an album; each image inside it becomes a photo.

## Quick start

1. Install [uv](https://docs.astral.sh/uv/), then `uv sync`.
2. Copy `.env.example` to `.env` and fill it in (see [docs/setup.md](docs/setup.md)).
3. `uv run reel sync`, then `uv run reel build`, then `uv run reel serve` and open http://localhost:8000.

## Development

- Lint: `uv run ruff check .`
- Typecheck: `uv run mypy src`
- Test: `uv run pytest`

## Docs

- [Setup](docs/setup.md)
- [Drive folder conventions](docs/drive-conventions.md)
- [Architecture](docs/architecture.md)
