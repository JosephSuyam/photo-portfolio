from pathlib import Path

import pytest

from reel.models import Manifest, original_path
from tests.fixtures.albums import make_album, make_photo


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
