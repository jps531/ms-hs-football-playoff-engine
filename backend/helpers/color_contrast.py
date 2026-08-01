"""WCAG contrast clamping for school team colors.

Precomputes light/dark, text/ui variants of a raw hex color that are
guaranteed to meet WCAG contrast minimums against a light card (`#FFFFFF`)
and a dark card (`#272727`).  Hue and saturation are preserved — only OKLCh
lightness is adjusted, via a binary search that finds the minimal shift
needed to clear the target ratio.  All computation is pure Python (plus
``coloraide`` for OKLCh conversion); no DB or Prefect imports here.

See docs/proposals/COLOR_CLAMP_SPEC.md for the full design.

Public API
----------
ClampConfig               — tunable model parameters (surfaces, targets, iterations)
ClampResult                — one clamped color + whether the target was unreachable
ColorVariantsResult        — primary/secondary variant blobs + any skip warnings
is_valid_hex()             — ``#RRGGBB`` shape check
relative_luminance()       — WCAG relative luminance of a hex color
contrast_ratio()           — WCAG contrast ratio between two hex colors
clamp_color()               — binary-search lightness clamp of one color against one surface
compute_variant_blob()      — light/dark × text/ui blob for one raw hex color
compute_color_variants()    — full primary + multi-secondary orchestration
"""

import re
from dataclasses import dataclass, field
from typing import TypeGuard

from coloraide import Color

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIGHT_SURFACE = "#FFFFFF"
DARK_SURFACE = "#272727"
TEXT_TARGET_RATIO = 4.5
UI_TARGET_RATIO = 3.0
ALGORITHM_VERSION = 1

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass
class ClampConfig:
    """Tunable parameters for the contrast-clamping algorithm."""

    iterations: int = 12
    text_target: float = TEXT_TARGET_RATIO
    ui_target: float = UI_TARGET_RATIO
    light_surface: str = LIGHT_SURFACE
    dark_surface: str = DARK_SURFACE


DEFAULT_CLAMP_CONFIG = ClampConfig()


# ---------------------------------------------------------------------------
# WCAG contrast (exact, no approximations)
# ---------------------------------------------------------------------------


def is_valid_hex(value: str | None) -> TypeGuard[str]:
    """Return True if *value* is a well-formed ``#RRGGBB`` hex color string."""
    return bool(value) and bool(_HEX_RE.match(value))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a ``#RRGGBB`` hex string to an (r, g, b) tuple of 0-255 ints."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _linearize(c: float) -> float:
    """Convert one 0-255 sRGB channel value to linear light per the WCAG spec."""
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """Return the WCAG relative luminance (0-1) of a ``#RRGGBB`` hex color."""
    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """Return the WCAG contrast ratio (1-21) between two ``#RRGGBB`` hex colors."""
    la, lb = relative_luminance(hex_a), relative_luminance(hex_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------------------
# OKLCh lightness manipulation
# ---------------------------------------------------------------------------


def _oklch_lightness(hex_color: str) -> float:
    """Return the OKLCh lightness channel (0-1) of a ``#RRGGBB`` hex color."""
    return Color(hex_color).convert("oklch")["lightness"]


def _with_oklch_lightness(hex_color: str, lightness: float) -> str:
    """Return *hex_color* with its OKLCh lightness set to *lightness*, hue/chroma unchanged.

    Fit back into the sRGB gamut (clipping only the lightness-shifted result,
    never hue or chroma) and serialize as uppercase ``#RRGGBB``.
    """
    oklch = Color(hex_color).convert("oklch")
    oklch["lightness"] = lightness
    return oklch.convert("srgb").to_string(hex=True, fit=True).upper()


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


@dataclass
class ClampResult:
    """One clamped color, plus whether the target ratio was unreachable."""

    hex: str
    clamp_failed: bool


def clamp_color(
    hex_color: str,
    surface: str,
    target_ratio: float,
    config: ClampConfig = DEFAULT_CLAMP_CONFIG,
) -> ClampResult:
    """Return the minimal lightness-only adjustment of *hex_color* that clears
    *target_ratio* against *surface*, preserving hue and saturation.

    Returns *hex_color* unchanged if it already clears the target. Otherwise
    binary-searches OKLCh lightness toward white (if *surface* is dark) or
    black (if *surface* is light) for ``config.iterations`` steps, so the
    result is the closest compliant relative of the original. If even the
    extreme (`#FFFFFF`/`#000000`) cannot clear the target, that extreme is
    returned with ``clamp_failed=True``.
    """
    if contrast_ratio(hex_color, surface) >= target_ratio:
        return ClampResult(hex=hex_color, clamp_failed=False)

    lighten = relative_luminance(surface) < 0.5
    extreme = "#FFFFFF" if lighten else "#000000"

    lo = _oklch_lightness(hex_color)
    hi = 1.0 if lighten else 0.0
    for _ in range(config.iterations):
        mid = (lo + hi) / 2
        candidate = _with_oklch_lightness(hex_color, mid)
        if contrast_ratio(candidate, surface) >= target_ratio:
            hi = mid  # compliant — try to stay closer to the original
        else:
            lo = mid

    result = _with_oklch_lightness(hex_color, hi)
    if contrast_ratio(result, surface) < target_ratio:
        return ClampResult(hex=extreme, clamp_failed=True)
    return ClampResult(hex=result, clamp_failed=False)


def compute_variant_blob(raw_hex: str | None, config: ClampConfig = DEFAULT_CLAMP_CONFIG) -> dict | None:
    """Return the light/dark × text/ui variant blob for one raw hex color.

    Returns None for malformed or missing input — callers decide whether/how
    to log the skip; this module does no I/O.
    """
    if not is_valid_hex(raw_hex):
        return None

    light_text = clamp_color(raw_hex, config.light_surface, config.text_target, config)
    light_ui = clamp_color(raw_hex, config.light_surface, config.ui_target, config)
    dark_text = clamp_color(raw_hex, config.dark_surface, config.text_target, config)
    dark_ui = clamp_color(raw_hex, config.dark_surface, config.ui_target, config)

    return {
        "raw": raw_hex,
        "light": {
            "text": light_text.hex,
            "ui": light_ui.hex,
            "clamp_failed": light_text.clamp_failed or light_ui.clamp_failed,
        },
        "dark": {
            "text": dark_text.hex,
            "ui": dark_ui.hex,
            "clamp_failed": dark_text.clamp_failed or dark_ui.clamp_failed,
        },
    }


@dataclass
class ColorVariantsResult:
    """Primary + multi-secondary variant blobs, plus any malformed-input warnings."""

    primary: dict | None
    secondary: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_color_variants(
    primary_hex: str | None,
    secondary_hexes: list[str],
    config: ClampConfig = DEFAULT_CLAMP_CONFIG,
) -> ColorVariantsResult:
    """Compute variant blobs for one primary color and a list of secondary colors.

    ``primary`` is a single blob (or None if missing/malformed). ``secondary``
    is a list with one blob per valid entry in *secondary_hexes* — malformed
    entries are individually skipped (with a warning) rather than aborting
    the whole call, since a school can have up to five secondary colors.
    """
    warnings: list[str] = []

    primary_blob = compute_variant_blob(primary_hex, config)
    if primary_hex and primary_blob is None:
        warnings.append(f"primary hex {primary_hex!r} is malformed — skipped")

    secondary_blobs: list[dict] = []
    for hex_color in secondary_hexes:
        blob = compute_variant_blob(hex_color, config)
        if blob is None:
            warnings.append(f"secondary hex {hex_color!r} is malformed — skipped")
        else:
            secondary_blobs.append(blob)

    return ColorVariantsResult(primary=primary_blob, secondary=secondary_blobs, warnings=warnings)
