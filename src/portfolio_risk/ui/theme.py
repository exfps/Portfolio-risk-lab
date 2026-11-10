"""Colours and Streamlit options shared by the launcher, the charts and ``.streamlit/config.toml``.

``tests/test_ui_support.py`` checks that ``.streamlit/config.toml`` agrees with these values.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

BACKGROUND = "#0B0C0E"
SURFACE = "#14161A"
ELEVATED = "#1B1E24"  # cards sitting on the surface
BORDER = "#272B32"
TEXT = "#ECECEC"
MUTED = "#9AA1AB"
GRID = "#23262B"
AXIS = "#3A3E45"
ACCENT = "#2BB3A3"  # teal: the primary accent
ACCENT_BRIGHT = "#5ED3C4"  # teal for hover and highlights
GOLD = "#C9A96E"  # champagne: used sparingly, for small details only
NEGATIVE = "#B5523B"  # muted rust: losses and drawdowns

FONT_STACK = (
    "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, "
    "'Helvetica Neue', sans-serif"
)


def rgba(colour: str, alpha: float) -> str:
    """``#RRGGBB`` and an opacity as a CSS ``rgba()`` string (used for chart gradients)."""
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red},{green},{blue},{alpha})"


@dataclass(frozen=True)
class Palette:
    """Every colour the interface and charts use. Frozen, so it can key a cache."""

    name: str
    background: str
    surface: str
    elevated: str
    border: str
    text: str
    muted: str
    grid: str
    axis: str
    accent: str
    accent_bright: str
    gold: str
    negative: str


DEFAULT = Palette(
    "Midnight", BACKGROUND, SURFACE, ELEVATED, BORDER, TEXT, MUTED, GRID, AXIS,
    ACCENT, ACCENT_BRIGHT, GOLD, NEGATIVE,
)  # fmt: skip

PRESETS: dict[str, Palette] = {
    DEFAULT.name: DEFAULT,
    "Graphite": replace(
        DEFAULT, name="Graphite", background="#0E1013", surface="#16191E", elevated="#1E2229",
        border="#2B3038", grid="#23272E", axis="#3C424B", accent="#7C9CD6",
        accent_bright="#A5BCE6", gold="#B8B2A3",
    ),
    "Obsidian gold": replace(
        DEFAULT, name="Obsidian gold", background="#0A0A0A", surface="#131313", elevated="#1B1A18",
        border="#2A2824", grid="#222120", axis="#3B3935", accent="#C9A96E",
        accent_bright="#E2C792", gold="#C9A96E",
    ),
    "Forest": replace(
        DEFAULT, name="Forest", background="#0A0D0B", surface="#111612", elevated="#181F19",
        border="#26302A", grid="#202821", axis="#38443B", accent="#6DB38A",
        accent_bright="#9AD1B0", gold="#C2B07A",
    ),
}  # fmt: skip

FONT_SIZES: dict[str, int] = {"Compact": 15, "Comfortable": 16, "Large": 18}
MIN_ACCENT_CONTRAST = 3.0  # WCAG minimum for graphical objects and large text


def is_hex(colour: str) -> bool:
    return (
        len(colour) == 7
        and colour[0] == "#"
        and all(c in "0123456789abcdefABCDEF" for c in colour[1:])
    )


def _rgb(colour: str) -> tuple[int, int, int]:
    return (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def luminance(colour: str) -> float:
    """Relative luminance as defined by WCAG 2."""

    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(colour)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def lighten(colour: str, amount: float) -> str:
    """Mix with white; ``amount`` 0 leaves the colour unchanged, 1 gives white."""
    return _hex(tuple(v + (255 - v) * amount for v in _rgb(colour)))  # type: ignore[arg-type]


def darken(colour: str, amount: float) -> str:
    """Mix with black; ``amount`` 0 leaves the colour unchanged, 1 gives black."""
    return _hex(tuple(v * (1 - amount) for v in _rgb(colour)))  # type: ignore[arg-type]


def on_paper(accent: str) -> str:
    """The accent darkened until it is readable on a white page (printed reports)."""
    step = 0.0
    while contrast_ratio(accent, "#FFFFFF") < MIN_ACCENT_CONTRAST and step < 1.0:
        step += 0.05
        accent = darken(accent, 0.05)
    return accent


def with_accent(palette: Palette, accent: str) -> Palette:
    """The palette with another accent colour, lightened until it is readable on the background.

    Raises ``ValueError`` for anything but ``#RRGGBB``.
    """
    if not is_hex(accent):
        raise ValueError(f"accent must be #RRGGBB, not {accent!r}")
    accent = accent.upper()
    step = 0.0
    while contrast_ratio(accent, palette.background) < MIN_ACCENT_CONTRAST and step < 1.0:
        step += 0.05
        accent = lighten(accent, 0.05)
    return replace(palette, accent=accent, accent_bright=lighten(accent, 0.3))


# Streamlit option name -> value. Passed on the command line by the launcher, and mirrored in
# .streamlit/config.toml for hosts that start Streamlit themselves.
STREAMLIT_OPTIONS: dict[str, str] = {
    "theme.base": "dark",
    "theme.primaryColor": ACCENT,
    "theme.backgroundColor": BACKGROUND,
    "theme.secondaryBackgroundColor": SURFACE,
    "theme.textColor": TEXT,
    "client.toolbarMode": "minimal",
    "browser.gatherUsageStats": "false",
}
