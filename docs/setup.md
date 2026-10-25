# Setup

1. In Google Cloud, create a project, enable the **Google Drive API**, and create a
   **service account**. Download its JSON key and store it **outside** this repo.
2. In Google Drive, share the portfolio root folder with the service account's email address
   as **Viewer**.
3. Copy `.env.example` to `.env` and set:
   - `GOOGLE_APPLICATION_CREDENTIALS`: path to the JSON key
   - `DRIVE_ROOT_FOLDER_ID`: the last part of the root folder's URL
   - `SITE_TITLE`, `SITE_BASE_URL` (optional)
   - `CONTACT_FORM_URL` (optional, see [Contact form](#contact-form-optional))
4. Optional: for About and Contact pages, edit
   [`docs/examples/about.json`](examples/about.json) and
   [`docs/examples/contact.json`](examples/contact.json) and upload them to the Drive root,
   next to the album folders. Format and rules:
   [Drive folder conventions](drive-conventions.md#about-and-contact-pages).

The app only requests the `drive.readonly` scope and never writes to Drive.

A 404 or 403 on the root folder usually means it is not shared with the service account.

Environment variables override `.env`. If you edit `.env` while VS Code is open, restart it:
its terminals may still carry the old values.

## Contact form (optional)

Adds a "Send a message" form to the Contact page. The site is static, so a form service
receives the messages. The Contact page needs a usable `contact.json`; without one,
`reel build` warns that the form is not shown.

1. Pick a service that accepts a plain HTML form POST, e.g. [Formspree](https://formspree.io/).
   Create a form and copy its `https://` endpoint.
2. Set it in `.env`:

   ```
   CONTACT_FORM_URL=https://formspree.io/f/your-form-id
   ```

   Only `https://` URLs are accepted. Otherwise `reel sync` and `reel build` stop with
   `CONTACT_FORM_URL must be an https:// URL.`
3. Restart VS Code if it injects `.env`, then run `uv run reel build`.
4. To remove the form, unset `CONTACT_FORM_URL` and build again: the Contact page then shows
   links only.

The form posts `name`, `email`, and `message`, plus an empty hidden honeypot field `_gotcha`
that spam bots tend to fill in. The endpoint is visible in the page's HTML, as with any form.
The service's free-tier limits, cost, and where it stores visitor messages are your choice
and responsibility. Tests never call the service.
