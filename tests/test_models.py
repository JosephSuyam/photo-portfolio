from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from reel.models import Manifest, original_path
from tests.fixtures.albums import make_album, make_photo

if TYPE_CHECKING:
    from reel.models import TextFile


def test_manifest_json_round_trip_preserves_albums() -> None:
    manifest = Manifest(albums=[make_album("b", [make_photo("p1")]), make_album("a", [])])
    assert Manifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_original_path_valid_id_under_originals(tmp_path: Path) -> None:
    assert original_path(tmp_path, "1AbC_d-9") == tmp_path / "originals" / "1AbC_d-9"


@pytest.mark.parametrize(
    "file_id",
    ["", "../x", "a/b", "a\\b", "..", "a.jpg", "a b", "<script>", "/etc/passwd", "C:x"],
)
def test_original_path_unsafe_id_raises_value_error(tmp_path: Path, file_id: str) -> None:
    with pytest.raises(ValueError):
        original_path(tmp_path, file_id)


def _about_file() -> "TextFile":
    from reel.models import TextFile

    return TextFile(
        file_id="t-about",
        name="about.txt",
        mime_type="text/plain",
        md5_checksum="md5-about",
        modified_time=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_text_file_md5_checksum_defaults_to_none() -> None:
    from reel.models import TextFile

    text_file = TextFile(
        file_id="t1", name="about.txt", mime_type="text/plain", modified_time=datetime.now(UTC)
    )
    assert text_file.md5_checksum is None


@pytest.mark.parametrize("field", ["about", "contact"])
def test_manifest_text_pages_default_to_none(field: str) -> None:
    assert getattr(Manifest(albums=[]), field) is None


@pytest.mark.parametrize("field", ["about", "contact"])
def test_manifest_old_json_without_text_pages_validates_with_none(field: str) -> None:
    manifest = Manifest.model_validate_json('{"albums": []}')
    assert getattr(manifest, field) is None


def test_manifest_json_round_trip_preserves_text_pages() -> None:
    contact = _about_file().model_copy(update={"file_id": "t-contact", "name": "Contact.txt"})
    manifest = Manifest(albums=[], about=_about_file(), contact=contact)
    assert Manifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_text_file_missing_modified_time_rejected() -> None:
    from pydantic import ValidationError

    from reel.models import TextFile

    with pytest.raises(ValidationError):
        TextFile.model_validate({"file_id": "t1", "name": "about.txt", "mime_type": "text/plain"})
