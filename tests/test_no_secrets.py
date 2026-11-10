"""Fails if anything shaped like a real API key is committed to the repository."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".hypothesis",
}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
    ".css",
    ".csv",
    ".cfg",
    ".ini",
    ".example",
}
# OpenAI, DeepSeek and Anthropic keys all start "sk-" followed by a long unbroken token.
PATTERNS = [re.compile(r"\bsk-[A-Za-z0-9_]{24,}"), re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")]


def _files() -> list[Path]:
    found = []
    for path in ROOT.rglob("*"):
        skipped = bool(SKIP_DIRS & set(path.relative_to(ROOT).parts))
        wanted = path.suffix in TEXT_SUFFIXES or path.name in {".env", ".gitignore"}
        if path.is_file() and wanted and not skipped:
            found.append(path)
    return found


def test_no_api_keys_are_in_the_repository() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in _files()
        if any(p.search(path.read_text(encoding="utf-8", errors="ignore")) for p in PATTERNS)
    ]
    assert offenders == [], f"Possible API keys in: {offenders}"


def test_a_local_env_file_is_ignored_by_git() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignore
