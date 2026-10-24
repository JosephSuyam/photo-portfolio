"""Tiny generated images for tests. No real photos ever live in the repo."""

from pathlib import Path

from PIL import Image

ORIENTATION_TAG = 0x0112
GPS_IFD_TAG = 0x8825


def make_image(
    path: Path,
    size: tuple[int, int] = (40, 30),
    color: tuple[int, ...] = (200, 50, 50),
    mode: str = "RGB",
    image_format: str = "JPEG",
    exif: Image.Exif | None = None,
) -> Path:
    """Write a solid-color image to `path` and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new(mode, size, color)
    if exif is None:
        image.save(path, format=image_format)
    else:
        image.save(path, format=image_format, exif=exif)
    return path


def orientation_exif(orientation: int) -> Image.Exif:
    """EXIF block carrying only an Orientation tag."""
    exif = Image.Exif()
    exif[ORIENTATION_TAG] = orientation
    return exif


def gps_exif() -> Image.Exif:
    """EXIF block carrying a GPS location."""
    exif = Image.Exif()
    gps = exif.get_ifd(GPS_IFD_TAG)
    gps[1] = "N"
    gps[2] = (52.0, 22.0, 1.0)
    gps[3] = "E"
    gps[4] = (4.0, 53.0, 2.0)
    return exif
