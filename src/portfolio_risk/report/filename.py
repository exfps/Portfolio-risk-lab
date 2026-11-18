"""Turn what a person typed into a safe export file name. Pure: no UI or file access."""

from __future__ import annotations

import re

MAX_LENGTH = 100
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_EXTENSIONS = (".pdf", ".xlsx")
# Windows refuses these names with any extension, so they are suffixed rather than rejected.
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}  # fmt: skip


def safe_stem(name: str, default: str) -> str:
    """A file name without extension that is valid on Windows, macOS and Linux.

    Characters the three systems forbid are removed, a typed ``.pdf`` or ``.xlsx`` is dropped
    (the exporter adds the right one), whitespace is collapsed, and the result is cut to
    ``MAX_LENGTH``. An empty result falls back to ``default``.
    """
    text = _FORBIDDEN.sub("", name).strip()
    if text.lower().endswith(_EXTENSIONS):
        text = text[: text.rfind(".")]
    text = re.sub(r"\s+", " ", text).strip(" .")[:MAX_LENGTH].strip(" .")
    if not text:
        return default
    if text.split(".")[0].upper() in _RESERVED:
        text = f"{text}_"
    return text
