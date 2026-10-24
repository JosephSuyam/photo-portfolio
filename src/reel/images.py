"""Thumbnail and display-size generation (WebP with JPEG fallback).

Originals are only read. Each derived file is named after a hash of its bytes, so
outputs are deterministic and can be cached forever. No EXIF is written, which drops
location data along with everything else.
"""

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

THUMBNAIL_WIDTH = 600
DISPLAY_LONG_EDGE = 2000

_HASH_PREFIX_LENGTH = 16
_JPEG_BACKGROUND = (255, 255, 255)
_QUALITY = 85
_ICC_COMPATIBLE_MODES = ("RGB", "RGBA")


class ImageError(Exception):
    """Raised when a source file cannot be read as an image."""


@dataclass(frozen=True)
class ImageVariant:
    """One derived size, saved as both WebP and JPEG."""

    webp_name: str
    jpeg_name: str
    width: int
    height: int


@dataclass(frozen=True)
class ProcessedPhoto:
    """All derived files for one source photo."""

    thumbnail: ImageVariant
    display: ImageVariant


def process_photo(source: Path, out_dir: Path) -> ProcessedPhoto:
    """Write thumbnail and display variants of `source` into `out_dir`.

    Raises ImageError if `source` is not a readable image. `source` is never modified.
    """
    image, icc_profile = _load_upright(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    return ProcessedPhoto(
        thumbnail=_write_variant(image, thumbnail_size(image.size), icc_profile, out_dir),
        display=_write_variant(image, display_size(image.size), icc_profile, out_dir),
    )


def thumbnail_size(size: tuple[int, int]) -> tuple[int, int]:
    """Size scaled to THUMBNAIL_WIDTH wide, never upscaling or exceeding the display size."""
    return _scaled(size, min(1.0, THUMBNAIL_WIDTH / size[0], DISPLAY_LONG_EDGE / max(size)))


def display_size(size: tuple[int, int]) -> tuple[int, int]:
    """Size scaled to DISPLAY_LONG_EDGE on the long edge, never upscaling."""
    return _scaled(size, min(1.0, DISPLAY_LONG_EDGE / max(size)))


def content_name(data: bytes, extension: str) -> str:
    """File name derived from the content hash of `data`."""
    return f"{hashlib.sha256(data).hexdigest()[:_HASH_PREFIX_LENGTH]}.{extension}"


def _scaled(size: tuple[int, int], factor: float) -> tuple[int, int]:
    width, height = size
    return max(1, round(width * factor)), max(1, round(height * factor))


def _load_upright(source: Path) -> tuple[Image.Image, bytes | None]:
    """Decoded, upright, RGB(A) image with no source metadata, plus its usable ICC profile."""
    try:
        with Image.open(source) as opened:
            upright = ImageOps.exif_transpose(opened)
            upright.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise ImageError(f"Cannot read image {source.name}: {error}") from error
    # A CMYK or grayscale profile no longer describes the pixels once converted to RGB.
    icc_profile = upright.info.get("icc_profile") if upright.mode in _ICC_COMPATIBLE_MODES else None
    normalized = _normalized_mode(upright)
    # Pillow re-emits some source metadata (e.g. JPEG comments), which can hold locations.
    normalized.info = {}
    return normalized, icc_profile


def _normalized_mode(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    target = "RGBA" if has_alpha else "RGB"
    return image if image.mode == target else image.convert(target)


def _write_variant(
    image: Image.Image, size: tuple[int, int], icc_profile: bytes | None, out_dir: Path
) -> ImageVariant:
    resized = image if size == image.size else image.resize(size, Image.Resampling.LANCZOS)
    webp_bytes = _encode(resized, "WEBP", icc_profile)
    jpeg_bytes = _encode(_flattened(resized), "JPEG", icc_profile)
    webp_name = content_name(webp_bytes, "webp")
    jpeg_name = content_name(jpeg_bytes, "jpg")
    (out_dir / webp_name).write_bytes(webp_bytes)
    (out_dir / jpeg_name).write_bytes(jpeg_bytes)
    return ImageVariant(webp_name=webp_name, jpeg_name=jpeg_name, width=size[0], height=size[1])


def _flattened(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    background = Image.new("RGB", image.size, _JPEG_BACKGROUND)
    background.paste(image, mask=image.getchannel("A"))
    return background


def _encode(image: Image.Image, image_format: str, icc_profile: bytes | None) -> bytes:
    # Writing an empty EXIF block on purpose: originals may carry GPS location.
    options: dict[str, object] = {"exif": b"", "quality": _QUALITY}
    if icc_profile:
        options["icc_profile"] = icc_profile
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()
