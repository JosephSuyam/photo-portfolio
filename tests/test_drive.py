from typing import Any

import httplib2
import pytest
from googleapiclient.errors import HttpError

from reel.drive import (
    FOLDER_MIME_TYPE,
    SHORTCUT_MIME_TYPE,
    DriveError,
    DriveFile,
    GoogleDriveClient,
)

API_ITEM = {
    "id": "f1",
    "name": "Book I",
    "mimeType": FOLDER_MIME_TYPE,
    "modifiedTime": "2024-05-01T12:00:00.000Z",
}


class _Request:
    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result

    def execute(self, num_retries: int = 0) -> dict[str, Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _FakeService:
    """Stands in for the Drive v3 service.

    Serves `files().list()` pages keyed by token and a single `files().get()` result.
    """

    def __init__(
        self,
        pages: dict[str | None, dict[str, Any] | Exception] | None = None,
        file: dict[str, Any] | Exception | None = None,
    ) -> None:
        self._pages = pages or {}
        self._file = file
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def files(self) -> "_FakeService":
        return self

    def list(self, **kwargs: Any) -> _Request:
        self.list_calls.append(kwargs)
        return _Request(self._pages[kwargs["pageToken"]])

    def get(self, **kwargs: Any) -> _Request:
        self.get_calls.append(kwargs)
        assert self._file is not None
        return _Request(self._file)


def _item(file_id: str) -> dict[str, Any]:
    return {**API_ITEM, "id": file_id}


def _http_error(status: int, message: str = "nope") -> HttpError:
    body = f'{{"error": {{"message": "{message}"}}}}'.encode()
    return HttpError(httplib2.Response({"status": status}), body)


def test_drive_file_api_payload_parsed_by_alias() -> None:
    assert DriveFile.model_validate(API_ITEM).mime_type == FOLDER_MIME_TYPE


def test_drive_file_folder_without_md5_defaults_to_none() -> None:
    assert DriveFile.model_validate(API_ITEM).md5_checksum is None


def test_drive_file_folder_mime_is_folder() -> None:
    assert DriveFile.model_validate(API_ITEM).is_folder


def test_drive_file_image_mime_is_not_folder() -> None:
    item = {**API_ITEM, "mimeType": "image/jpeg", "md5Checksum": "abc"}
    assert not DriveFile.model_validate(item).is_folder


def test_drive_file_shortcut_mime_is_shortcut() -> None:
    assert DriveFile.model_validate({**API_ITEM, "mimeType": SHORTCUT_MIME_TYPE}).is_shortcut


def test_list_children_multiple_pages_returns_all_items() -> None:
    service = _FakeService(
        {
            None: {"files": [_item("a")], "nextPageToken": "t2"},
            "t2": {"files": [_item("b")], "nextPageToken": "t3"},
            "t3": {"files": [_item("c")]},
        }
    )
    children = GoogleDriveClient(service).list_children("root")
    assert [child.id for child in children] == ["a", "b", "c"]


def test_list_children_empty_folder_returns_empty_list() -> None:
    service = _FakeService({None: {}})
    assert GoogleDriveClient(service).list_children("root") == []


def test_list_children_requests_shared_drive_support() -> None:
    service = _FakeService({None: {"files": []}})
    GoogleDriveClient(service).list_children("root")
    assert service.list_calls[0]["supportsAllDrives"] is True


def test_list_children_quote_in_folder_id_escaped_in_query() -> None:
    service = _FakeService({None: {"files": []}})
    GoogleDriveClient(service).list_children("a'b")
    assert service.list_calls[0]["q"].startswith("'a\\'b' in parents")


def test_list_children_http_404_raises_drive_error_with_sharing_hint() -> None:
    service = _FakeService({None: _http_error(404)})
    with pytest.raises(DriveError, match="shared with the service account"):
        GoogleDriveClient(service).list_children("root")


def test_list_children_http_500_raises_drive_error_without_hint() -> None:
    service = _FakeService({None: _http_error(500)})
    with pytest.raises(DriveError) as excinfo:
        GoogleDriveClient(service).list_children("root")
    assert "shared" not in str(excinfo.value)


def test_get_folder_visible_folder_returns_entry() -> None:
    service = _FakeService(file=_item("root"))
    assert GoogleDriveClient(service).get_folder("root").id == "root"


def test_get_folder_requests_shared_drive_support() -> None:
    service = _FakeService(file=_item("root"))
    GoogleDriveClient(service).get_folder("root")
    assert service.get_calls[0]["supportsAllDrives"] is True


@pytest.mark.parametrize("status", [403, 404])
def test_get_folder_unshared_raises_drive_error_with_sharing_hint(status: int) -> None:
    # Listing an unshared folder returns nothing, so this lookup is what surfaces the problem.
    service = _FakeService(file=_http_error(status))
    with pytest.raises(DriveError, match="shared with the service account"):
        GoogleDriveClient(service).get_folder("root")


def test_get_folder_id_of_a_file_raises_drive_error() -> None:
    service = _FakeService(file={**API_ITEM, "mimeType": "image/jpeg"})
    with pytest.raises(DriveError, match="not a folder"):
        GoogleDriveClient(service).get_folder("root")


def test_get_folder_trashed_folder_raises_drive_error() -> None:
    service = _FakeService(file={**_item("root"), "trashed": True})
    with pytest.raises(DriveError, match="in the trash"):
        GoogleDriveClient(service).get_folder("root")


def test_get_folder_requests_trashed_field() -> None:
    service = _FakeService(file=_item("root"))
    GoogleDriveClient(service).get_folder("root")
    assert "trashed" in service.get_calls[0]["fields"]


def test_drive_error_reason_ending_in_period_not_doubled() -> None:
    service = _FakeService(file=_http_error(404, "File not found: root."))
    with pytest.raises(DriveError) as excinfo:
        GoogleDriveClient(service).get_folder("root")
    assert ".." not in str(excinfo.value)
