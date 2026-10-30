# Project Instructions

## Project
A photographer portfolio, generated from a Google Drive folder: root = portfolio, each **subfolder = one album**, each **image = a photo**.
- Pages: `/` and `/work/` (album index: one full-screen, scroll-snapped cover per album), `/<album-slug>/` (cover hero that opens in the lightbox, title, gap-free mosaic of square-cropped photos with lightbox, next-album banner with Previous). `/about/` and `/contact/` (from root `about.json` / `contact.json`, omitted when absent; samples in `docs/examples/`). Light/dark theme toggle. Blog, client proofing: out of scope until asked.
- Pipeline: `sync` (Drive -> `.cache/` + `manifest.json`) -> `build` (images, Jinja2, compiled TypeScript -> `dist/`) -> `serve`/deploy (static files). Drive is never called at page-view time and Drive links never appear in output (they expire and must not be public).
- Stack: Python 3.12+ via `uv` (pinned to 3.12 via `.python-version`; CI uses it) (google-api-python-client, google-auth, Pillow, Jinja2, typer, pydantic v2, ruff, mypy, pytest); npm for TypeScript 7 (tsconfig needs `rootDir`) and Playwright (runs on the installed Edge).
- Layout: `src/portfolio/` (`drive.py` is the only module that talks to Google; `ts/` site script), `tests/` mirrors it (`FakeDriveClient` in `tests/fixtures/`), `e2e/` Playwright + fixture site (generated images, no Drive), `docs/`.

## Commands (single source of truth; agents and skills refer here)
- Install: `uv sync && npm install` | Format: `uv run ruff format .`
- One test: `uv run pytest -k "<name>"` | `npx playwright test -g "<name>"`
- Site: `uv run portfolio sync` / `build` / `serve` (localhost:8000); `portfolio all` = sync + build; `portfolio watch` rebuilds on change with live reload; `portfolio subscribe` renews the Drive change webhook
- Ports: 8000 is the user's preview server (don't take it over or stop it unless asked); Playwright uses 8123.

## Configuration
`.env` (never committed; shape in `.env.example`): `GOOGLE_APPLICATION_CREDENTIALS`, `DRIVE_ROOT_FOLDER_ID`, `SITE_TITLE`, `SITE_BASE_URL`, optional `CONTACT_FORM_URL` (https form endpoint; unset = no form), optional `DRIVE_WEBHOOK_URL` + `DRIVE_WEBHOOK_TOKEN` (for `subscribe`; setup in `docs/setup.md`). Real env vars override it; VS Code injects `.env` at startup, so restart it after edits. Root folder shared (Viewer) with the service account; scope `drive.readonly`. The path in `SITE_BASE_URL` becomes the site's base path (e.g. `/portfolio/`).

## Drive conventions
- Albums: immediate subfolders of the root, natural sort by name ("Book 2" before "Book 10"); a numeric prefix (`01 Book I`) forces order. Deeper nesting ignored; empty albums unpublished.
- Title: folder name trimmed, minus a sort prefix (`01 Book I` -> `Book I`; 1-3 digits + space/`.`/`_`/`-`). Slug from the title (`book-i`), unique (`-2`), never `work`, `static`, `images`, `about`, `contact`, or `api`.
- Photos: JPEG, PNG, WebP, natural sort by filename; other files and shortcuts skipped with a warning. Cover: a `cover.*` file (not shown among photos), else the first photo.
- Drive lists an unshared folder as **empty**, so sync calls `get_folder(root)` first. Handle pagination and shared drives (`supportsAllDrives=True`). Names and ids are untrusted: sanitize.

## Image, sync, and build rules
- Cache contract (sync -> build): `.cache/manifest.json` (`Manifest` in `models.py`) and originals at `.cache/originals/<file_id>`. Details in `docs/architecture.md`.
- Originals in `.cache/` are never modified; derived files go to `dist/`, named by content hash.
- Per photo: 600px-wide thumbnail and 2000px-long-edge display, WebP + JPEG. Apply EXIF orientation, never upscale, strip all metadata except the ICC profile.
- Re-download only when `md5Checksum`/`modifiedTime` changed or the file is missing. Delete originals removed from Drive only after the new manifest is written.
- Build writes to a staging folder and swaps it into `dist/`; a failed build leaves the old site. It refuses to replace a `dist/` without its `.portfolio-build` marker, so never hand-edit or hand-delete `dist/`.
- `portfolio build` compiles `src/portfolio/ts/` into `dist/static/`; compiled JS is never committed. Without Node it warns and builds without the script.

## How we work
The `orchestrator` agent (`claude --agent orchestrator`) plans, delegates, verifies, and summarizes; only it delegates (other agents have no Agent tool). Agents: `implementer` (code), `test-writer` (pytest + Playwright), `debugger`, `code-reviewer`, `doc-writer`; skills: `run-tests` (Full check), `preview-site` (screenshots), `ship` (Full check, push, PR into `develop`, merge, CI on `develop`). Delegate large or noisy work with goal, paths, constraints, and output format; do small edits yourself.

1. Understand; ask if ambiguous; plan briefly for 3+ files or a public interface.
2. The smallest change that works. No new tests unless the user asks (features: see 4).
3. `uv run ruff check . && uv run mypy src` and a manual run (`portfolio watch`; UI: `preview-site`). Then `code-reviewer`: fix blocking and should-fix findings. Docs only when the user asks (features: see 4).
4. Features by default also get tests (`test-writer`), docs (`doc-writer`), `run-tests`, and the built-in `/security-review`.

**Done means:** ruff and mypy green and the change seen working; no open blocking review findings; no debug prints, commented-out code, or TODOs without an issue. Never weaken, skip, or mock away what a test checks. Tests never touch the real Drive or the network. If something cannot be run, say so.

**End every task with a summary** (plain language, skimmable in a minute; skip empty parts):
- **Result:** one or two sentences on what the user can do or see now.
- **What changed:** a table (Area | Change | Files) when there are three or more changes.
- **How it was verified:** ruff/mypy results; manual checks and what was seen.
- **Decisions and open items:** choices made for the user, risks, failures or skipped checks (with output; never hide them), and the next step as a question if it needs the user.

## Safety
- Never read, print, or commit `.env`, the service-account key, or tokens; error messages must not echo the key's path or contents. Never commit photos, `.cache/`, or `dist/`. Never write to or delete anything in Drive.
- `.claude/hooks/guard.py` (PreToolUse) enforces the git, secret, and `dist/`/`.cache/` rules here and makes the user confirm any merge or push into `main` unless their latest typed prompt has "deploy to main", "deploy to prod", or "push to main" as its own clause ("ship it, deploy to main"; not "should we deploy to main?"); a block is a rule, not a bug to route around (if it only matched message text, pass the text from a `.tmp/` file with `git commit -F` or `--body-file`).
- Ask before: deleting files, installing dependencies, merging or pushing (`/ship` approves a feature branch into `develop`; `main` always needs an explicit yes, such as "deploy to main"), force-pushing, rewriting history, deploying, or spending paid credits.
- CI/CD runs only on pushes to `develop` and `main`, never on feature branches or their PRs (add environment branches to `ci.yml` when they exist). Before any merge or push into them, the `run-tests` Full check must be green locally.
- Work on feature branches merged into `develop`. Small conventional commits; before committing, check `git status` and leave out unrelated work. Never `git checkout -- .` or reset the main checkout to tidy up: uncommitted work lives there.
- Windows, Git Bash. Multi-line edits: Edit tool or a script in `.tmp/` (inline heredocs with nested quotes break). Throwaway files go in `.tmp/`.

## Learning
Propose a one-line addition here or to an agent/skill when you learn something durable (API quirk, wrong command, flaky-test cause); don't silently rewrite.
