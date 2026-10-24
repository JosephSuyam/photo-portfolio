# Setup

1. In Google Cloud, create a project, enable the **Google Drive API**, and create a
   **service account**. Download its JSON key and store it **outside** this repo.
2. In Google Drive, share the portfolio root folder with the service account's email address
   as **Viewer**.
3. Copy `.env.example` to `.env` and set:
   - `GOOGLE_APPLICATION_CREDENTIALS`: path to the JSON key
   - `DRIVE_ROOT_FOLDER_ID`: the last part of the root folder's URL
   - `SITE_TITLE`, `SITE_BASE_URL` (optional)

The app only requests the `drive.readonly` scope and never writes to Drive.

A 404 or 403 on the root folder usually means it is not shared with the service account.

Environment variables override `.env`. If you edit `.env` while VS Code is open, restart it:
its terminals may still carry the old values.
