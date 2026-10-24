"""In-memory `DriveClient` for tests. Never touches the network."""

from datetime import UTC, datetime
from pathlib import Path

from reel.drive import FOLDER_MIME_TYPE, DriveClient, DriveError, DriveFile

_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


class FakeDriveClient:
    """A Drive folder tree held in dicts. Records calls so tests can assert on them.

    `calls` logs every `get_folder`/`list_children` call as `(method, id)` in order,
    `downloads` logs every downloaded file id, and ids in `failing_downloads` raise
    `DriveError` instead of writing anything.
    """

    def __init__(self) -> None:
        self._children: dict[str, list[DriveFile]] = {}
        self._folders: dict[str, DriveFile] = {}
        self._content: dict[str, bytes] = {}
        self.downloads: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.failing_downloads: set[str] = set()

    @property
    def listed(self) -> list[str]:
        """Folder ids passed to `list_children`, in call order."""
        return [item_id for method, item_id in self.calls if method == "list_children"]

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

    def update_file(
        self,
        file_id: str,
        content: bytes | None = None,
        md5_checksum: str | None = None,
        modified_time: datetime | None = None,
    ) -> None:
        """Change an existing file in place, as an edit in Drive would."""
        if not any(
            entry.id == file_id for siblings in self._children.values() for entry in siblings
        ):
            raise KeyError(file_id)
        for siblings in self._children.values():
            for index, entry in enumerate(siblings):
                if entry.id != file_id:
                    continue
                changes: dict[str, object] = {}
                if md5_checksum is not None:
                    changes["md5_checksum"] = md5_checksum
                if modified_time is not None:
                    changes["modified_time"] = modified_time
                siblings[index] = entry.model_copy(update=changes)
        if content is not None:
            self._content[file_id] = content

    def remove(self, item_id: str) -> None:
        """Delete a file or folder (and its listing) as if it was removed from Drive."""
        for parent_id, siblings in self._children.items():
            self._children[parent_id] = [entry for entry in siblings if entry.id != item_id]
        self._children.pop(item_id, None)
        self._folders.pop(item_id, None)
        self._content.pop(item_id, None)

    def get_folder(self, folder_id: str) -> DriveFile:
        """Return a registered folder; unknown ids behave like an unshared folder."""
        self.calls.append(("get_folder", folder_id))
        if folder_id not in self._folders:
            raise DriveError(
                f"Drive lookup of folder {folder_id} failed with status 404: File not found."
                " If this is the root folder, check it is shared with the service account."
            )
        return self._folders[folder_id]

    def list_children(self, folder_id: str) -> list[DriveFile]:
        """Return the children of `folder_id` (empty if unknown)."""
        self.calls.append(("list_children", folder_id))
        return list(self._children.get(folder_id, []))

    def download(self, file_id: str, dest: Path) -> None:
        """Write stored content to `dest` and record the download."""
        self.downloads.append(file_id)
        if file_id in self.failing_downloads:
            raise DriveError(f"Drive download of file {file_id} failed with status 500: boom.")
        dest.write_bytes(self._content[file_id])


# A type checker flags this line if the fake drifts from the DriveClient Protocol.
_conforms: DriveClient = FakeDriveClient()
