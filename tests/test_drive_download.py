from pathlib import Path
from typing import IO, Any

import httplib2
import pytest
from googleapiclient.errors import HttpError

from reel.drive import DriveError, GoogleDriveClient


class _Service:
    def files(self) -> "_Service":
        return self

    def get_media(self, **kwargs: Any) -> object:
        return object()


def _downloader(chunks: list[bytes], fail: bool) -> type:
    """Build a stand-in for MediaIoBaseDownload that writes `chunks`, then optionally fails."""

    class _Downloader:
        def __init__(self, handle: IO[bytes], request: object) -> None:
            self._handle = handle
            self._remaining = list(chunks)

        def next_chunk(self, num_retries: int = 0) -> tuple[None, bool]:
            if self._remaining:
                self._handle.write(self._remaining.pop(0))
                return None, not self._remaining and not fail
            raise HttpError(httplib2.Response({"status": 500}), b"")

    return _Downloader


def test_download_success_writes_dest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", _downloader([b"ab"], False))
    dest = tmp_path / "photo.jpg"
    GoogleDriveClient(_Service()).download("f1", dest)
    assert dest.read_bytes() == b"ab"


def test_download_success_leaves_no_part_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", _downloader([b"ab"], False))
    GoogleDriveClient(_Service()).download("f1", tmp_path / "photo.jpg")
    assert [p.name for p in tmp_path.iterdir()] == ["photo.jpg"]


def test_download_failure_midway_leaves_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", _downloader([b"ab"], True))
    with pytest.raises(DriveError):
        GoogleDriveClient(_Service()).download("f1", tmp_path / "photo.jpg")
    assert list(tmp_path.iterdir()) == []


def test_download_failure_keeps_existing_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("googleapiclient.http.MediaIoBaseDownload", _downloader([b"new"], True))
    dest = tmp_path / "photo.jpg"
    dest.write_bytes(b"old")
    with pytest.raises(DriveError):
        GoogleDriveClient(_Service()).download("f1", dest)
    assert dest.read_bytes() == b"old"
