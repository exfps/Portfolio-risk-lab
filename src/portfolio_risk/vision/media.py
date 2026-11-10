"""Checks on an uploaded image before it is sent anywhere."""

from __future__ import annotations

from portfolio_risk.errors import ExtractionError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def detect_media_type(data: bytes) -> str:
    """The image's real type from its first bytes (the filename is not trusted).

    Supports PNG, JPEG and WebP. Raises ``ExtractionError`` for an empty, oversized or
    unsupported file.
    """
    if not data:
        raise ExtractionError("The image file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        limit = MAX_IMAGE_BYTES // (1024 * 1024)
        raise ExtractionError(
            f"The image is {len(data) / 1024 / 1024:.1f} MB; the limit is {limit} MB. "
            "Crop it or save a smaller copy."
        )
    for signature, media_type in _SIGNATURES:
        if data.startswith(signature):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ExtractionError("Unsupported image format. Use a PNG, JPEG or WebP screenshot.")
