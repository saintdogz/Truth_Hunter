"""Tests for bounded, in-memory image text extraction."""

from io import BytesIO

import pytest
from PIL import Image

from app.ocr.service import ImageTextError, extract_image_text


def image_bytes(*, image_format: str = "PNG", size: tuple[int, int] = (40, 20)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color="white").save(buffer, format=image_format)
    return buffer.getvalue()


def test_extract_image_text_normalizes_ocr_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.ocr.service.pytesseract.image_to_string",
        lambda *_args, **_kwargs: "  The Moon\nlanding happened.  ",
    )

    text = extract_image_text(
        image_bytes(),
        "image/png",
        max_bytes=100_000,
        max_pixels=1_000_000,
        max_characters=500,
    )

    assert text == "The Moon landing happened."


@pytest.mark.parametrize("content_type", ["image/svg+xml", "application/pdf", None])
def test_extract_image_text_rejects_unsafe_content_types(content_type: str | None) -> None:
    with pytest.raises(ImageTextError, match="JPEG, PNG, or WebP"):
        extract_image_text(
            image_bytes(),
            content_type,
            max_bytes=100_000,
            max_pixels=1_000_000,
            max_characters=500,
        )


def test_extract_image_text_rejects_spoofed_and_oversized_files() -> None:
    with pytest.raises(ImageTextError, match="safe image"):
        extract_image_text(
            b"not really an image",
            "image/png",
            max_bytes=100_000,
            max_pixels=1_000_000,
            max_characters=500,
        )
    with pytest.raises(ImageTextError, match="too large"):
        extract_image_text(
            image_bytes(),
            "image/png",
            max_bytes=10,
            max_pixels=1_000_000,
            max_characters=500,
        )


def test_extract_image_text_rejects_empty_or_excessive_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.ocr.service.pytesseract.image_to_string", lambda *_args, **_kwargs: "  "
    )
    with pytest.raises(ImageTextError, match="No readable text"):
        extract_image_text(
            image_bytes(),
            "image/png",
            max_bytes=100_000,
            max_pixels=1_000_000,
            max_characters=500,
        )

    monkeypatch.setattr(
        "app.ocr.service.pytesseract.image_to_string", lambda *_args, **_kwargs: "x" * 501
    )
    with pytest.raises(ImageTextError, match="too much text"):
        extract_image_text(
            image_bytes(),
            "image/png",
            max_bytes=100_000,
            max_pixels=1_000_000,
            max_characters=500,
        )
