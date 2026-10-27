"""Google Drive access. This is the only module that talks to Google, and it only reads."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from googleapiclient.errors import HttpError
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
_FILE_FIELDS = "id, name, mimeType, md5Checksum, modifiedTime"
_FIELDS = f"nextPageToken, files({_FILE_FIELDS})"
# googleapiclient retries rate-limit (403/429) and 5xx responses with exponential backoff.
_NUM_RETRIES = 5


class DriveError(Exception):
    """A Drive API call failed after retries."""


class DriveFile(BaseModel):
    """A file or folder entry as returned by the Drive v3 `files.list` endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    mime_type: str = Field(alias="mimeType")
    md5_checksum: str | None = Field(default=None, alias="md5Checksum")
    modified_time: datetime = Field(alias="modifiedTime")

    @property
    def is_folder(self) -> bool:
        """Whether this entry is a Drive folder."""
        return self.mime_type == FOLDER_MIME_TYPE

    @property
    def is_shortcut(self) -> bool:
        """Whether this entry is a Drive shortcut (always skipped)."""
        return self.mime_type == SHORTCUT_MIME_TYPE


class DriveClient(Protocol):
    """Read-only view of a Drive folder tree. Tests use an in-memory fake."""

    def get_folder(self, folder_id: str) -> DriveFile:
        """Return the folder `folder_id`, or raise `DriveError` if it is missing or unshared.

        Call this on the root before listing it: Drive lists an inaccessible folder as empty.
        """
        ...

    def list_children(self, folder_id: str) -> list[DriveFile]:
        """Return every non-trashed direct child of `folder_id`, across all pages."""
        ...

    def download(self, file_id: str, dest: Path) -> None:
        """Write the content of `file_id` to `dest`."""
        ...


def _drive_error(exc: HttpError, action: str) -> DriveError:
    status = exc.resp.status
    logger.error("Drive %s failed: status=%s reason=%s", action, status, exc.reason)
    hint = ""
    if status in (403, 404):
        hint = " If this is the root folder, check it is shared with the service account."
    reason = str(exc.reason).rstrip(".")
    return DriveError(f"Drive {action} failed with status {status}: {reason}.{hint}")


class GoogleDriveClient:
    """`DriveClient` backed by the real Drive v3 API."""

    def __init__(self, service: Any) -> None:
        """Wrap an already-built Drive v3 service. Use `from_credentials` in production."""
        self._service = service

    @classmethod
    def from_credentials(cls, credentials_path: Path) -> "GoogleDriveClient":
        """Build a client authenticated as the service account in `credentials_path`."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        # google-auth leaves this constructor unannotated.
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            str(credentials_path), scopes=SCOPES
        )
        return cls(build("drive", "v3", credentials=credentials, cache_discovery=False))

    def get_folder(self, folder_id: str) -> DriveFile:
        """Return the folder `folder_id`, or raise `DriveError` if it is missing or unshared.

        Call this on the root before listing it: Drive lists an inaccessible folder as empty.
        """
        try:
            item = (
                self._service.files()
                .get(fileId=folder_id, fields=f"{_FILE_FIELDS}, trashed", supportsAllDrives=True)
                .execute(num_retries=_NUM_RETRIES)
            )
        except HttpError as exc:
            raise _drive_error(exc, f"lookup of folder {folder_id}") from exc
        entry = DriveFile.model_validate(item)
        if not entry.is_folder:
            logger.error("Drive item %s is not a folder (mimeType=%s)", folder_id, entry.mime_type)
            raise DriveError(f"Drive item {folder_id} is not a folder.")
        # files.get returns trashed items, whose children list_children would filter out.
        if item.get("trashed"):
            logger.error("Drive folder %s is in the trash", folder_id)
            raise DriveError(f"Drive folder {folder_id} is in the trash.")
        return entry

    def list_children(self, folder_id: str) -> list[DriveFile]:
        """Return every non-trashed direct child of `folder_id`, across all pages."""
        escaped_id = folder_id.replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{escaped_id}' in parents and trashed = false"
        children: list[DriveFile] = []
        page_token: str | None = None
        while True:
            try:
                response = (
                    self._service.files()
                    .list(
                        q=query,
                        fields=_FIELDS,
                        pageSize=1000,
                        pageToken=page_token,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute(num_retries=_NUM_RETRIES)
                )
            except HttpError as exc:
                raise _drive_error(exc, f"listing of folder {folder_id}") from exc
            children.extend(DriveFile.model_validate(item) for item in response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return children

    def download(self, file_id: str, dest: Path) -> None:
        """Write the content of `file_id` to `dest`, atomically.

        Downloads go to a `.part` file first so a failed transfer never leaves a truncated
        original that incremental sync would mistake for a current one.
        """
        from googleapiclient.http import MediaIoBaseDownload

        partial = dest.with_name(dest.name + ".part")
        request = self._service.files().get_media(fileId=file_id, supportsAllDrives=True)
        try:
            with partial.open("wb") as handle:
                downloader = MediaIoBaseDownload(handle, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk(num_retries=_NUM_RETRIES)
        except HttpError as exc:
            partial.unlink(missing_ok=True)
            raise _drive_error(exc, f"download of file {file_id}") from exc
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.replace(dest)
