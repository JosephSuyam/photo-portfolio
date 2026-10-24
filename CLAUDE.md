# Project Instructions

## Project
A photographer portfolio modeled on https://reel.format.com/, generated from a Google Drive
folder: root = portfolio, each **subfolder = one album**, each **image = a photo**.

- Pages: `/` and `/work/` (album index: cover + title per album), `/<album-slug>/` (all photos,
  plus "Next" to the following album). Bio, Blog, Contact, client proofing: out of scope until asked.
- Pipeline: `sync` (Drive -> `.cache/` + `manifest.json`) -> `build` (images + Jinja2 + compiled
  TypeScript -> `dist/`) -> `serve`/deploy (plain static files). Drive is never called at page-view
  time and Drive links never appear in output: they expire and must not be public.
- Stack: Python 3.12+ with `uv` (google-api-python-client, google-auth, Pillow, Jinja2, typer,
  pydantic v2; ruff, mypy, pytest). npm for TypeScript 7 (`tsconfig` needs an explicit `rootDir`)
  and Playwright, which runs on the installed Edge (no browser download).

```
src/reel/   config models drive(only module that talks to Google) sync images build
            scripts(tsc) server(preview) cli | templates/ static/(css) ts/
tests/      mirrors src/reel/; fixtures in tests/fixtures/ (FakeDriveClient, image builders)
e2e/        Playwright specs + serve_fixture.py (sample site from generated images, no Drive)
docs/       setup, Drive folder conventions, architecture
```

## Commands (single source of truth; agents and skills refer here)
- Install: `uv sync && npm install`
- Format: `uv run ruff format .`
- One Python test: `uv run pytest tests/test_sync.py` or `uv run pytest -k "<name>"`
- One browser test: `npx playwright test -g "<name>"`
- Run the site: `uv run reel sync` / `uv run reel build` / `uv run reel serve` (http://localhost:8000);
  `uv run reel all` = sync + build
- **Full check** (what "done" means):
  `uv run ruff check . && uv run mypy src && uv run pytest && npm run typecheck && npm run test:e2e`

If a command is wrong, fix it here.

## Configuration
`.env` (never committed; shape in `.env.example`): `GOOGLE_APPLICATION_CREDENTIALS`,
`DRIVE_ROOT_FOLDER_ID`, `SITE_TITLE`, `SITE_BASE_URL`. Real env vars override `.env`; VS Code
injects `.env` into terminals at startup, so restart it after editing `.env`. The root folder is
shared (Viewer) with the service account; scope is `drive.readonly`.

## Drive folder conventions
- Albums: immediate subfolders of the root (deeper nesting ignored), natural sort by folder
  name ("Book 2" before "Book 10"); a numeric prefix (`01 Book I`) forces order.
- Album title: the folder name as written (trimmed). Slug: from the title (`01 Book I` ->
  `01-book-i`), unique (`-2` on collision), never `work`, `static`, or `images`.
- Photos: JPEG, PNG, WebP, natural sort by filename. Other files and shortcuts are skipped with
  a logged warning. Empty albums are not published.
- Cover: a file named `cover.*` (not shown among the photos), otherwise the first photo.
- Drive lists an unshared folder as **empty** (no 403/404), so sync calls `get_folder(root)`
  first. Handle pagination and shared drives (`supportsAllDrives=True`).
- Drive names and ids are untrusted: sanitize before using them as paths, slugs, or HTML.

## Image and sync rules
- Originals in `.cache/` are never modified. Derived files go to `dist/`, named by content hash.
- Per photo: thumbnail (600px wide) and display (2000px long edge), WebP + JPEG. Apply EXIF
  orientation, never upscale, strip all metadata except the ICC profile.
- Sync re-downloads only when `md5Checksum`/`modifiedTime` changed or the file is missing, and
  removes originals deleted from Drive only after the new manifest is written.

## How we work
The main session plans, delegates, verifies, and reports. Only it delegates.

| Need | Who |
|---|---|
| Explore / plan | built-in `Explore`, `Plan` |
| Production code | `implementer` |
| Tests (pytest and Playwright) | `test-writer` |
| Failures | `debugger` |
| Review | `code-reviewer` |
| Docs | `doc-writer` |
| Full check | `run-tests` skill |
| See the site (screenshots) | `preview-site` skill |

Delegate large, noisy, or independent-eyes work; do small edits yourself. Give each subagent the
goal, file paths, constraints, and output format.

1. Understand the code; ask if requirements are ambiguous. Plan briefly for 3+ files or a public interface.
2. Tests first; bug fixes start with a failing test.
3. Smallest change that works.
4. Run the Full check; for UI changes also look at the result with `preview-site`.
5. `code-reviewer`; fix blocking and should-fix findings, re-run the Full check.
6. Update docs when behavior, config, conventions, or the CLI change.
7. Finish with a summary of the whole process (format below).

**Summary format** (after every task; plain language, skimmable in under a minute):
```
## Summary
**Result:** one or two sentences: what the user can do or see now.

**What changed**
| Area | Change | Files |
|---|---|---|
| ... | ... | [path](path) |

**How it was verified**
- Full check: ruff ✓, mypy ✓, pytest ✓ (N passed), typecheck ✓, e2e ✓ (N passed)
- Anything checked by hand (screenshots, real sync), with what was seen

**Decisions and open items**
- Choices made on the user's behalf, risks, and anything skipped or failing (say so plainly)
- Next step, as a question if it needs the user
```
Lead with the outcome, not the steps. Use a table when listing three or more changes. Skip
empty sections. Mention failures and skipped checks with their output, never hide them.

**Done means:** Full check actually run and green; new behavior tested, including an edge case
and a failure path; no unresolved blocking review findings; docs current; no debug prints,
commented-out code, or TODOs without an issue reference. If something cannot be run, say so.
Never make a test pass by weakening, skipping, or mocking away the thing under test. Tests never
touch the real Drive or the network.

## Safety
- Never read, print, or commit `.env`, the service-account key, or tokens.
- Never commit photos, `.cache/`, or `dist/`. Never write to or delete anything in Drive.
- Ask before: deleting files, installing dependencies, force-pushing, rewriting history,
  deploying, or spending paid credits.
- Work on a branch, never `main`. Small conventional commits. Before committing, check
  `git status` and leave out unrelated uncommitted work (it may belong to another branch).

## Environment
Windows; the Bash tool is Git Bash. For multi-line edits use the Edit tool, or write a script to
`.tmp/` and run it: inline heredocs with nested quotes break. Throwaway files go in `.tmp/`.

## Learning
When you learn something durable (API quirk, wrong command, flaky-test cause), propose a one-line
addition here or to the relevant agent/skill; don't silently rewrite them. Keep this file short.
