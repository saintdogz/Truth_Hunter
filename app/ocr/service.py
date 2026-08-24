"""Secure, in-memory OCR for user-submitted claim images."""

from io import BytesIO

import pytesseract  # type: ignore[import-untyped]
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageTextError(ValueError):
    """Raised when an image cannot safely produce a bounded claim."""


def extract_image_text(
    payload: bytes,
    content_type: str | None,
    *,
    max_bytes: int,
    max_pixels: int,
    max_characters: int,
) -> str:
    """Validate and OCR one raster image without retaining the uploaded bytes."""

    if not payload:
        raise ImageTextError("The uploaded image is empty.")
    if len(payload) > max_bytes:
        raise ImageTextError("The uploaded image is too large.")
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type not in ALLOWED_CONTENT_TYPES:
        raise ImageTextError("Upload a JPEG, PNG, or WebP image.")

    try:
        with Image.open(BytesIO(payload)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise ImageTextError("The file content is not a supported image.")
            if getattr(source, "is_animated", False):
                raise ImageTextError("Animated images are not supported.")
            width, height = source.size
            if width < 1 or height < 1 or width * height > max_pixels:
                raise ImageTextError("The image dimensions are not supported.")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.load()
    except ImageTextError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise ImageTextError("The uploaded file could not be read as a safe image.") from exc

    try:
        raw_text = pytesseract.image_to_string(image, lang="eng+hun", config="--psm 6")
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
        raise ImageTextError("Text extraction is temporarily unavailable.") from exc

    text = " ".join(raw_text.split()).strip()
    if not text:
        raise ImageTextError("No readable text was found in the image.")
    if len(text) > max_characters:
        raise ImageTextError(
            "The image contains too much text. Crop it to the claim and try again."
        )
    return text
