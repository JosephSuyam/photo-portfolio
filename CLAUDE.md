# Project Instructions

## Project context
A photographer portfolio website modeled on https://reel.format.com/, driven entirely by a
Google Drive folder: root folder = portfolio, each **subfolder = one album**, each **image = a photo**.

**Pages (MVP):**
- `/` and `/work`: album index (cover image + title per album, linking to the album page).
- `/<album-slug>`: all photos in the album, plus a "Next" link to the following album.
- Out of scope until asked: Bio, Blog, Contact, client proofing galleries.

**Approach: static site generated from a Drive sync.** Drive is never called at page-view time.
1. `sync`: pull the folder tree and images from Drive into `.cache/`.
2. `build`: process images and render HTML with Jinja2 into `dist/`.
3. `serve`/deploy: `dist/` is plain static files.
Why: fast pages, no Drive rate limits or auth in the browser, and Drive links expire and must
never be exposed publicly.

**Stack:** Python 3.12+ with `uv`; `google-api-python-client` + `google-auth` (service account,
read-only); `Pillow`; `Jinja2`; `typer`; `pydantic` v2; `ruff`, `mypy`, `pytest`.

**Layout**
```
src/reel/
  config.py     settings from env (.env)
  models.py     Album, Photo (pydantic)
  drive.py      DriveClient interface + real adapter (the only module that talks to Google)
  sync.py       incremental sync into .cache/ + manifest.json
  images.py     resize / WebP / thumbnail generation
  build.py      manifest -> Jinja2 -> dist/
  cli.py        `reel sync | build | serve | all`
  templates/    base.html, index.html, album.html
  static/       css, js
tests/          mirrors src/reel/, fixtures in tests/fixtures/
docs/           architecture, setup, Drive folder conventions
```

## Commands (single source of truth)
- Install: `uv sync`
- Lint / format: `uv run ruff check .` / `uv run ruff format .`
- Typecheck: `uv run mypy src`
- Test: `uv run pytest` (one file: `uv run pytest tests/test_drive.py`, one case: `uv run pytest -k "<name>"`)
- Sync / build / preview: `uv run reel sync` / `uv run reel build` / `uv run reel serve` (http://localhost:8000)
- Full check (what "done" means): `uv run ruff check . && uv run mypy src && uv run pytest`

Always use these exact commands. If one is wrong, fix it here.

## Configuration
`.env` (never committed; `.env.example` documents the shape): `GOOGLE_APPLICATION_CREDENTIALS`,
`DRIVE_ROOT_FOLDER_ID`, `SITE_TITLE`, `SITE_BASE_URL`.
The root folder must be shared (Viewer) with the service account's email. Scope is
`https://www.googleapis.com/auth/drive.readonly`. This project **never writes to Drive**.
Real env vars override `.env`. VS Code can inject `.env` into terminals at startup, so after
editing `.env`, restart the editor/session or stale values win.

## Drive folder conventions
- Albums are the immediate subfolders of the root. Deeper nesting is ignored.
- **Album order:** folder name, natural sort ("Book 2" before "Book 10"). A numeric prefix
  (`01 Book I`) forces order and is stripped from the display title.
- **Photo order:** filename, natural sort.
- **Cover:** a file named `cover.*` if present, otherwise the first photo.
- **Supported types:** JPEG, PNG, WebP. Everything else (docs, videos, shortcuts) is skipped with a logged warning.
- **Slugs:** from the cleaned album title; unique (suffix `-2` on collision).
- Empty albums are not published.
- Handle pagination (`nextPageToken`) and shared drives (`supportsAllDrives=True`).
- Drive lists a folder the service account can't access as **empty**, not 403/404. Sync must
  call `get_folder(root)` first so an unshared root fails loudly instead of publishing nothing.
- Drive file and folder names are untrusted input: sanitize before using as paths or HTML.

## Image pipeline rules
- Never modify originals in `.cache/`. Derived files go to `dist/`.
- Per photo: thumbnail (~600px wide) and display size (~2000px long edge), WebP with JPEG
  fallback. Strip EXIF location data by default.
- Respect EXIF orientation. Preserve aspect ratio. Never upscale.
- Incremental sync: re-download only when `md5Checksum`/`modifiedTime` changed. Remove cache
  entries for photos or albums deleted from Drive.
- Output filenames are content-hashed so they can be cached forever.

## Orchestrator + specialists
The main session plans, delegates, verifies, and reports. Specialists are in `.claude/agents/`
and carry their own detailed rules; procedures are in `.claude/skills/`. Only the orchestrator
delegates (subagents cannot spawn subagents).

| Need          | Who                        |
|---------------|----------------------------|
| Explore/plan  | built-in `Explore`, `Plan` |
| Write code    | `implementer`              |
| Unit tests    | `test-writer`              |
| Debug         | `debugger`                 |
| Code review   | `code-reviewer`            |
| Run checks    | `run-tests` skill          |
| Docs          | `doc-writer`               |

Delegate work that is large, noisy, or benefits from independent eyes. Do small edits yourself.
Give every subagent the goal, relevant file paths, constraints, and expected output format.

## Workflow
1. **Understand** the code and tests; ask if requirements are ambiguous.
2. **Plan** briefly for changes touching 3+ files or any public interface.
3. **Test first** when feasible. Bug fixes start with a failing test.
4. **Implement** the smallest change that satisfies the task.
5. **Verify** with the Full check. **Review** with `code-reviewer`; fix blocking findings, re-verify.
6. **Document** via `doc-writer` if behavior, config, folder conventions, or CLI changed.
7. **Report** what changed, what was verified, and open risks.

## Definition of Done
- [ ] `ruff`, `mypy`, and `pytest` pass (actually run, output seen)
- [ ] New or changed behavior has tests, including an edge case and a failure path
- [ ] Reviewer reported no unresolved blocking issues
- [ ] Docs updated where needed
- [ ] No debug prints, commented-out blocks, or stray TODOs without an issue reference

Never claim success without running the checks. If something cannot be run, say so.
Never make a test pass by weakening, skipping, or mocking away the thing under test.
Tests never hit the real Google Drive or the network. No new dependency without asking.

## Safety and permissions
- Never read, print, or commit `.env`, the service-account JSON, or tokens.
- Never commit photos, `.cache/`, or `dist/`.
- Never write to or delete anything in Google Drive.
- Ask before: deleting files, force-pushing, rewriting history, deploying, installing
  dependencies, or anything that spends paid credits.
- Work on a branch, never directly on `main`. Small, conventional commits.

## Learning
When you learn something durable (Drive API quirk, wrong command, flaky test cause), propose a
one-line addition here or to the relevant agent/skill; don't silently rewrite either. Keep this
file under ~250 lines. Throwaway files go in `.tmp/` (gitignored).
