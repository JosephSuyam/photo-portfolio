# Setup

1. In Google Cloud, create a project, enable the **Google Drive API**, and create a **service account**. Download its JSON key and store it **outside** this repo.
2. In Google Drive, share the portfolio root folder with the service account's email address as **Viewer**.
3. Copy `.env.example` to `.env` and set:
   - `GOOGLE_APPLICATION_CREDENTIALS`: path to the JSON key
   - `DRIVE_ROOT_FOLDER_ID`: the last part of the root folder's URL
   - `SITE_TITLE`, `SITE_BASE_URL` (optional)
   - `CONTACT_FORM_URL` (optional, see [Contact form](#contact-form-optional))
4. Optional: for About and Contact pages, edit [`docs/examples/about.json`](examples/about.json) and [`docs/examples/contact.json`](examples/contact.json) and upload them to the Drive root, next to the album folders. Format and rules: [Drive folder conventions](drive-conventions.md#about-and-contact-pages).

The app only requests the `drive.readonly` scope and never writes to Drive.

A 404 or 403 on the root folder usually means it is not shared with the service account.

Environment variables override `.env`. If you edit `.env` while VS Code is open, restart it: its terminals may still carry the old values.

## Photo on About or Contact (optional)

Gives the page a split layout: the photo fills the left half and stays put while the text scrolls; on phones it sits on top.

1. Upload the image to the Drive root, next to `about.json` / `contact.json`, named `about.<ext>` or `contact.<ext>` (JPEG, PNG, or WebP), e.g. `about.jpg`. Case doesn't matter (`About.JPG` works); other names (`about-me.jpg`) don't. More rules: [Drive folder conventions](drive-conventions.md#about-and-contact-pages).
2. Run `uv run portfolio all`.

The page needs its `.json` too; a photo alone creates no page. To remove the photo, delete it from Drive and run `uv run portfolio all` again: the page goes back to the centered layout.

## Contact form (optional)

Adds a "Send a message" form to the Contact page. The site is static, so a form service receives the messages. The Contact page needs a usable `contact.json`; without one, `portfolio build` warns that the form is not shown.

1. Pick a service that accepts a plain HTML form POST, e.g. [Formspree](https://formspree.io/). Create a form and copy its `https://` endpoint.
2. Set it in `.env`:

   ```
   CONTACT_FORM_URL=https://formspree.io/f/your-form-id
   ```

   Only `https://` URLs are accepted. Otherwise `portfolio sync` and `portfolio build` stop with `CONTACT_FORM_URL must be an https:// URL.`
3. Restart VS Code if it injects `.env`, then run `uv run portfolio build`.
4. To remove the form, unset `CONTACT_FORM_URL` and build again: the Contact page then shows links only.

The form posts `name`, `email`, and `message`, plus an empty hidden honeypot field `_gotcha` that spam bots tend to fill in. The endpoint is visible in the page's HTML, as with any form. The service's free-tier limits, cost, and where it stores visitor messages are your choice and responsibility. Tests never call the service.

## Instant redeploy on Drive changes (optional)

Without this, the Deploy workflow picks up Drive changes on its 12-hour schedule. With it, a Drive change redeploys within about a minute: Drive push channel -> Vercel function `/api/drive-webhook` (built from `src/portfolio/api/drive-webhook.mjs` into `dist/api/`) -> GitHub `repository_dispatch` event `drive-changed` -> Deploy workflow. Every push, manual, or scheduled Deploy run (the 12-hour schedule stays as a fallback; webhook-triggered runs skip this) renews the channel with `portfolio subscribe`; each channel lasts 24 hours, so it survives long gaps in GitHub's schedule.

1. Generate a random token of at most 256 characters, e.g. `openssl rand -hex 32`.
2. Create a fine-grained GitHub personal access token for this repository only, with **Contents: Read and write**.
3. In the Vercel project, add these Production environment variables:
   - `WEBHOOK_TOKEN`: the token from step 1
   - `GITHUB_DISPATCH_TOKEN`: the access token from step 2
   - `GITHUB_REPO`: `owner/name`
4. In the GitHub `production` environment, add:
   - secret `DRIVE_WEBHOOK_TOKEN`: the same token as `WEBHOOK_TOKEN`
   - variable `DRIVE_WEBHOOK_URL`: `https://<site-domain>/api/drive-webhook`. The function sits at the deployment root, even when `SITE_BASE_URL` has a path.
5. Deploy once so the function exists. Then set `DRIVE_WEBHOOK_URL` and `DRIVE_WEBHOOK_TOKEN` in `.env` (see `.env.example`) and run `uv run portfolio subscribe`, or start the Deploy workflow by hand (Actions -> Deploy -> Run workflow on `main`).
6. Check: change something in Drive. A Deploy run with event `repository_dispatch` should start within about a minute.

Notes:
- `repository_dispatch` runs on the repository's default branch, which must be `main`.
- Drive also notifies about changes outside the portfolio folder. Runs with no Drive or code change skip the build and deploy.
- The endpoint answers 403 to requests without the token.
