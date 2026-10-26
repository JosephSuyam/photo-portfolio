---
name: preview-site
description: Build the site, serve it, and take headless Edge screenshots at desktop and phone sizes so UI changes are checked by looking, not just by reading HTML. Use after any template, CSS, TypeScript, or image-pipeline change, or when the user says something "doesn't show up".
---

# Preview the site

Tests prove behavior; screenshots catch layout problems (overlaps, cropped images, wrong grid). Always tell the user which **data source** you previewed. Generated placeholder images look like colored blocks or gradients and can be mistaken for "photos not showing".

## 1. Pick the data source
- **Real photos** (default when `.env` is configured): `uv run reel sync`, then `uv run reel build`. Sync only reads Drive. Check `.env` exists without reading it.
- **Fixture** (no Drive access, or to reproduce a test): `uv run python e2e/serve_fixture.py --port 8124` builds generated images into `.tmp/e2e/dist` and serves them (run in background).

## 2. Serve
- Real site: if nothing answers on http://localhost:8000 (`curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/`), start `uv run reel serve` in the background. A running server picks up a rebuild on its own (`dist/` is swapped atomically); restart it only after changing `src/reel/server.py` or `cli.py`.
- Never use a bare `http.server`: its listen backlog of 5 refuses parallel image requests. Use `reel serve` or `reel.server.make_preview_server`.

## 3. Screenshot with headless Edge
Write screenshots to `.tmp/shots/` (gitignored). For each page, run:
```
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
  --hide-scrollbars --user-data-dir="$(cygpath -aw .tmp/edge-profile)" --window-size=<w>,<h> \
  --virtual-time-budget=4000 --screenshot="$(cygpath -aw .tmp/shots/<name>.png)" <url>
```
Paths must be absolute (`cygpath -aw`): Edge resolves relative paths against its own working directory and silently writes nothing.
- Pages: `/work/` and at least one album page (two if albums differ, e.g. portrait vs landscape).
- Sizes: desktop `1440,900`; phone `520,900`; whole horizontal strip `5200,900` (shows the end of an album, including the "Next" block).
- Headless Edge never makes the viewport narrower than about 500px. A smaller window only crops the screenshot, so content looks cut off when it isn't. For true phone widths, rely on the Playwright `mobile` project instead.
- `--virtual-time-budget` gives lazy-loaded images time to load. A blank image slot means a real problem: check the server log.

## 4. Look and check
- Read each PNG. Compare the layout with https://reel.format.com/ when the change is about looks.
- Check the server output for 4xx/5xx responses (ignore `/favicon.ico`).

## Report
- Data source: real (album count from the sync output) or fixture.
- Each screenshot's full path and one line on what it shows.
- Problems found, with the likely file (`site.css`, a template, `build.py`).
