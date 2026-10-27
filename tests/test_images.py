import re
from pathlib import Path

import pytest
from PIL import Image

from portfolio.images import (
    DISPLAY_LONG_EDGE,
    THUMBNAIL_WIDTH,
    ImageError,
    ImageVariant,
    process_photo,
)
from tests.fixtures.images import gps_exif, make_image, orientation_exif

HEX_WEBP = re.compile(r"^[0-9a-f]+\.webp$")
HEX_JPEG = re.compile(r"^[0-9a-f]+\.jpg$")


def _open(out_dir: Path, name: str) -> Image.Image:
    image = Image.open(out_dir / name)
    image.load()
    return image


def _ratio(width: int, height: int) -> float:
    return width / height


def test_constants_match_pipeline_rules() -> None:
    assert (THUMBNAIL_WIDTH, DISPLAY_LONG_EDGE) == (600, 2000)


def test_process_photo_writes_four_files(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(1200, 800))
    out = tmp_path / "out"
    out.mkdir()
    process_photo(source, out)
    assert len(list(out.iterdir())) == 4


def test_process_photo_reported_names_exist(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    out = tmp_path / "out"
    out.mkdir()
    result = process_photo(source, out)
    names = {
        result.thumbnail.webp_name,
        result.thumbnail.jpeg_name,
        result.display.webp_name,
        result.display.jpeg_name,
    }
    assert names == {path.name for path in out.iterdir()}


def test_process_photo_webp_names_are_content_hashes(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    result = process_photo(source, tmp_path)
    assert all(HEX_WEBP.match(v.webp_name) for v in (result.thumbnail, result.display))


def test_process_photo_jpeg_names_are_content_hashes(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    result = process_photo(source, tmp_path)
    assert all(HEX_JPEG.match(v.jpeg_name) for v in (result.thumbnail, result.display))


def test_process_photo_webp_variant_is_webp_format(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    result = process_photo(source, tmp_path)
    assert _open(tmp_path, result.display.webp_name).format == "WEBP"


def test_process_photo_jpeg_variant_is_jpeg_format(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    result = process_photo(source, tmp_path)
    assert _open(tmp_path, result.display.jpeg_name).format == "JPEG"


def test_process_photo_same_input_same_names(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg")
    first_dir, second_dir = tmp_path / "a", tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    assert process_photo(source, first_dir) == process_photo(source, second_dir)


def test_process_photo_different_content_different_names(tmp_path: Path) -> None:
    red = make_image(tmp_path / "red.jpg", color=(255, 0, 0))
    blue = make_image(tmp_path / "blue.jpg", color=(0, 0, 255))
    out = tmp_path / "out"
    out.mkdir()
    assert process_photo(red, out).display.jpeg_name != process_photo(blue, out).display.jpeg_name


def test_process_photo_large_landscape_thumbnail_width_is_600(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(1200, 800))
    result = process_photo(source, tmp_path)
    assert result.thumbnail.width == THUMBNAIL_WIDTH


def test_process_photo_thumbnail_preserves_aspect_ratio(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(1200, 800))
    result = process_photo(source, tmp_path)
    assert result.thumbnail.height == pytest.approx(400, abs=1)


def test_process_photo_exactly_thumbnail_width_unchanged(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(600, 450))
    result = process_photo(source, tmp_path)
    assert (result.thumbnail.width, result.thumbnail.height) == (600, 450)


def test_process_photo_large_landscape_display_long_edge_is_2000(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(3000, 1500))
    result = process_photo(source, tmp_path)
    assert (result.display.width, result.display.height) == (2000, 1000)


def test_process_photo_large_portrait_display_long_edge_is_height(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(1000, 2500))
    result = process_photo(source, tmp_path)
    assert (result.display.width, result.display.height) == (800, 2000)


def test_process_photo_display_preserves_aspect_ratio(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(2400, 1000))
    result = process_photo(source, tmp_path)
    ratio = _ratio(result.display.width, result.display.height)
    assert ratio == pytest.approx(2.4, rel=0.01)


def test_process_photo_small_source_thumbnail_not_upscaled(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(300, 200))
    result = process_photo(source, tmp_path)
    assert (result.thumbnail.width, result.thumbnail.height) == (300, 200)


def test_process_photo_small_source_display_not_upscaled(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(300, 200))
    result = process_photo(source, tmp_path)
    assert (result.display.width, result.display.height) == (300, 200)


@pytest.mark.parametrize("variant", ["thumbnail", "display"])
@pytest.mark.parametrize("kind", ["webp_name", "jpeg_name"])
def test_process_photo_reported_size_matches_saved_file(
    tmp_path: Path, variant: str, kind: str
) -> None:
    source = make_image(tmp_path / "src.jpg", size=(2500, 1300))
    out = tmp_path / "out"
    out.mkdir()
    image_variant: ImageVariant = getattr(process_photo(source, out), variant)
    saved = _open(out, getattr(image_variant, kind))
    assert saved.size == (image_variant.width, image_variant.height)


def test_process_photo_exif_rotation_applied(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(100, 50), exif=orientation_exif(6))
    out = tmp_path / "out"
    out.mkdir()
    result = process_photo(source, out)
    saved = _open(out, result.display.jpeg_name)
    assert saved.size == (50, 100)


def test_process_photo_exif_rotation_reported_dimensions_portrait(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(100, 50), exif=orientation_exif(6))
    result = process_photo(source, tmp_path)
    assert result.thumbnail.height > result.thumbnail.width


def test_process_photo_exif_orientation_normal_keeps_landscape(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(100, 50), exif=orientation_exif(1))
    result = process_photo(source, tmp_path)
    assert (result.display.width, result.display.height) == (100, 50)


@pytest.mark.parametrize("kind", ["webp_name", "jpeg_name"])
def test_process_photo_output_has_no_exif(tmp_path: Path, kind: str) -> None:
    source = make_image(tmp_path / "src.jpg", size=(80, 60), exif=gps_exif())
    out = tmp_path / "out"
    out.mkdir()
    result = process_photo(source, out)
    assert len(_open(out, getattr(result.display, kind)).getexif()) == 0


def test_process_photo_thumbnail_has_no_gps(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(80, 60), exif=gps_exif())
    out = tmp_path / "out"
    out.mkdir()
    result = process_photo(source, out)
    exif = _open(out, result.thumbnail.jpeg_name).getexif()
    assert len(exif.get_ifd(0x8825)) == 0


def test_process_photo_original_unchanged(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(800, 600), exif=gps_exif())
    before = source.read_bytes()
    out = tmp_path / "out"
    out.mkdir()
    process_photo(source, out)
    assert source.read_bytes() == before


def test_process_photo_rgba_png_jpeg_is_rgb(tmp_path: Path) -> None:
    source = make_image(
        tmp_path / "src.png", color=(10, 20, 30, 128), mode="RGBA", image_format="PNG"
    )
    out = tmp_path / "out"
    out.mkdir()
    result = process_photo(source, out)
    assert _open(out, result.display.jpeg_name).mode == "RGB"


def test_process_photo_webp_source_supported(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.webp", size=(64, 48), image_format="WEBP")
    result = process_photo(source, tmp_path)
    assert (result.display.width, result.display.height) == (64, 48)


def test_process_photo_corrupt_file_raises_image_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.jpg"
    source.write_bytes(b"\xff\xd8\xff garbage")
    with pytest.raises(ImageError):
        process_photo(source, tmp_path)


def test_process_photo_non_image_file_raises_image_error(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    with pytest.raises(ImageError):
        process_photo(source, tmp_path)


def test_process_photo_jpeg_comment_not_copied(tmp_path: Path) -> None:
    source = tmp_path / "src.jpg"
    Image.new("RGB", (40, 30)).save(source, format="JPEG", comment=b"caption at 52N 4E")
    out = tmp_path / "out"
    result = process_photo(source, out)
    assert b"52N" not in (out / result.display.jpeg_name).read_bytes()


def test_process_photo_oversized_image_raises_image_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_image(tmp_path / "src.jpg", size=(100, 100))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(ImageError):
        process_photo(source, tmp_path / "out")


def test_process_photo_very_tall_thumbnail_not_larger_than_display(tmp_path: Path) -> None:
    source = make_image(tmp_path / "src.jpg", size=(1000, 4000))
    result = process_photo(source, tmp_path / "out")
    assert result.thumbnail.height <= result.display.height


def test_process_photo_cmyk_profile_not_attached_to_rgb_output(tmp_path: Path) -> None:
    source = tmp_path / "src.jpg"
    Image.new("CMYK", (40, 30)).save(source, format="JPEG", icc_profile=b"fake-cmyk-profile")
    out = tmp_path / "out"
    result = process_photo(source, out)
    assert "icc_profile" not in _open(out, result.display.jpeg_name).info
