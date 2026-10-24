"""In-memory `DriveClient` for tests. Never touches the network."""

from datetime import UTC, datetime
from pathlib import Path

from reel.drive import FOLDER_MIME_TYPE, DriveClient, DriveError, DriveFile

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


class FakeDriveClient:
    """A Drive folder tree held in dicts. Records downloads so tests can assert on them."""

    def __init__(self) -> None:
        self._children: dict[str, list[DriveFile]] = {}
        self._folders: dict[str, DriveFile] = {}
        self._content: dict[str, bytes] = {}
        self.downloads: list[str] = []

    def add_root(self, folder_id: str, name: str = "portfolio") -> DriveFile:
        """Register a root folder visible to the service account."""
        entry = DriveFile(id=folder_id, name=name, mime_type=FOLDER_MIME_TYPE, modified_time=_EPOCH)
        self._folders[folder_id] = entry
        return entry

    def add_folder(self, parent_id: str, folder_id: str, name: str) -> DriveFile:
        """Add a subfolder under `parent_id`."""
        entry = DriveFile(id=folder_id, name=name, mime_type=FOLDER_MIME_TYPE, modified_time=_EPOCH)
        self._children.setdefault(parent_id, []).append(entry)
        self._folders[folder_id] = entry
        return entry

    def add_file(
        self,
        parent_id: str,
        file_id: str,
        name: str,
        content: bytes = b"",
        mime_type: str = "image/jpeg",
        md5_checksum: str | None = None,
        modified_time: datetime = _EPOCH,
    ) -> DriveFile:
        """Add a file under `parent_id` with the given content."""
        entry = DriveFile(
            id=file_id,
            name=name,
            mime_type=mime_type,
            md5_checksum=md5_checksum or f"md5-{file_id}",
            modified_time=modified_time,
        )
        self._children.setdefault(parent_id, []).append(entry)
        self._content[file_id] = content
        return entry

    def get_folder(self, folder_id: str) -> DriveFile:
        """Return a registered folder; unknown ids behave like an unshared folder."""
        if folder_id not in self._folders:
            raise DriveError(
                f"Drive lookup of folder {folder_id} failed with status 404: File not found."
                " If this is the root folder, check it is shared with the service account."
            )
        return self._folders[folder_id]

    def list_children(self, folder_id: str) -> list[DriveFile]:
        """Return the children of `folder_id` (empty if unknown)."""
        return list(self._children.get(folder_id, []))

    def download(self, file_id: str, dest: Path) -> None:
        """Write stored content to `dest` and record the download."""
        self.downloads.append(file_id)
        dest.write_bytes(self._content[file_id])


# A type checker flags this line if the fake drifts from the DriveClient Protocol.
_conforms: DriveClient = FakeDriveClient()
