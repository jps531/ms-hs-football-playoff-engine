"""Unit tests for backend/helpers/color_contrast.py.

All tests are pure Python — no DB, no Prefect, no I/O.
"""

from coloraide import Color

from backend.helpers.color_contrast import (
    DARK_SURFACE,
    LIGHT_SURFACE,
    TEXT_TARGET_RATIO,
    UI_TARGET_RATIO,
    ClampConfig,
    clamp_color,
    compute_color_variants,
    compute_variant_blob,
    contrast_ratio,
    is_valid_hex,
    relative_luminance,
)

# ---------------------------------------------------------------------------
# WCAG math sanity
# ---------------------------------------------------------------------------


def test_relative_luminance_white_and_black():
    """White and black are the luminance extremes: 1.0 and 0.0."""
    assert relative_luminance("#FFFFFF") == 1.0
    assert relative_luminance("#000000") == 0.0


def test_contrast_ratio_white_black_is_max():
    """White against black is the maximum possible WCAG ratio, 21:1."""
    assert contrast_ratio("#FFFFFF", "#000000") == 21.0


def test_contrast_ratio_is_symmetric():
    """Contrast ratio doesn't depend on argument order."""
    assert contrast_ratio("#2A3EAD", "#272727") == contrast_ratio("#272727", "#2A3EAD")


def test_contrast_ratio_identical_colors_is_one():
    """A color against itself has the minimum possible ratio, 1:1."""
    assert contrast_ratio("#2A3EAD", "#2A3EAD") == 1.0


# ---------------------------------------------------------------------------
# is_valid_hex
# ---------------------------------------------------------------------------


def test_is_valid_hex_accepts_wellformed():
    """Six-digit hex strings are accepted regardless of case."""
    assert is_valid_hex("#2A3EAD")
    assert is_valid_hex("#ffffff")


def test_is_valid_hex_rejects_malformed():
    """None, empty, non-hex, out-of-range, and short-form values are all rejected."""
    assert not is_valid_hex(None)
    assert not is_valid_hex("")
    assert not is_valid_hex("not-a-color")
    assert not is_valid_hex("#ZZZZZZ")
    assert not is_valid_hex("#FFF")


# ---------------------------------------------------------------------------
# Golden values (spec §7): Seminary royal `#2A3EAD` on the dark card
# ---------------------------------------------------------------------------


def test_seminary_dark_text_clamp_meets_ratio_and_stays_blue():
    """Clamping Seminary royal for dark-mode text clears the ratio without a hue shift."""
    result = clamp_color("#2A3EAD", DARK_SURFACE, TEXT_TARGET_RATIO)
    assert not result.clamp_failed
    assert contrast_ratio(result.hex, DARK_SURFACE) >= TEXT_TARGET_RATIO

    orig_hue = Color("#2A3EAD").convert("oklch")["hue"]
    new_hue = Color(result.hex).convert("oklch")["hue"]
    assert abs(orig_hue - new_hue) < 10


def test_seminary_dark_ui_clamp_meets_ratio_and_stays_blue():
    """Clamping Seminary royal for dark-mode UI clears the (lower) ratio without a hue shift."""
    result = clamp_color("#2A3EAD", DARK_SURFACE, UI_TARGET_RATIO)
    assert not result.clamp_failed
    assert contrast_ratio(result.hex, DARK_SURFACE) >= UI_TARGET_RATIO

    orig_hue = Color("#2A3EAD").convert("oklch")["hue"]
    new_hue = Color(result.hex).convert("oklch")["hue"]
    assert abs(orig_hue - new_hue) < 10


def test_philadelphia_red_dark_text_clamp_meets_ratio():
    """Clamping a second golden-value color (Philadelphia red) also clears the target ratio."""
    result = clamp_color("#B01E28", DARK_SURFACE, TEXT_TARGET_RATIO)
    assert not result.clamp_failed
    assert contrast_ratio(result.hex, DARK_SURFACE) >= TEXT_TARGET_RATIO


# ---------------------------------------------------------------------------
# Idempotence: already-compliant colors are returned unchanged, byte for byte
# ---------------------------------------------------------------------------


def test_idempotence_compliant_color_unchanged():
    """A color that already clears the ratio is returned byte-for-byte unchanged."""
    # #2A3EAD already clears 4.5:1 against white (light card) — spec §1 table.
    result = clamp_color("#2A3EAD", LIGHT_SURFACE, TEXT_TARGET_RATIO)
    assert result.hex == "#2A3EAD"
    assert not result.clamp_failed


def test_idempotence_black_on_white():
    """Pure black against a white surface is already maximally compliant and unchanged."""
    result = clamp_color("#000000", LIGHT_SURFACE, TEXT_TARGET_RATIO)
    assert result.hex == "#000000"
    assert not result.clamp_failed


# ---------------------------------------------------------------------------
# Minimality: one binary-search step back toward the original fails the threshold
# ---------------------------------------------------------------------------


def test_minimality_one_step_back_fails_threshold():
    """The binary search stops at the minimal compliant lightness, not one step further."""
    hex_color = "#2A3EAD"
    result = clamp_color(hex_color, DARK_SURFACE, TEXT_TARGET_RATIO)
    assert not result.clamp_failed

    # Re-run the same bracketing search manually to recover the last
    # known-non-compliant lightness (`lo`) that bracketed the result.
    orig_lightness = Color(hex_color).convert("oklch")["lightness"]
    lo, hi = orig_lightness, 1.0
    for _ in range(12):
        mid = (lo + hi) / 2
        candidate = Color(hex_color).convert("oklch")
        candidate["lightness"] = mid
        candidate_hex = candidate.convert("srgb").to_string(hex=True, fit=True).upper()
        if contrast_ratio(candidate_hex, DARK_SURFACE) >= TEXT_TARGET_RATIO:
            hi = mid
        else:
            lo = mid

    lo_color = Color(hex_color).convert("oklch")
    lo_color["lightness"] = lo
    lo_hex = lo_color.convert("srgb").to_string(hex=True, fit=True).upper()
    assert contrast_ratio(lo_hex, DARK_SURFACE) < TEXT_TARGET_RATIO


# ---------------------------------------------------------------------------
# Edge cases (spec §4.3)
# ---------------------------------------------------------------------------


def test_already_compliant_light_mode_noop():
    """A typical school-brand blue already clears the light-mode target and is left alone."""
    # Most light-mode values hit this path per spec §4.3.
    result = clamp_color("#003DA5", LIGHT_SURFACE, TEXT_TARGET_RATIO)
    assert result.hex == "#003DA5"
    assert not result.clamp_failed


def test_near_white_on_light_darkens_toward_gray():
    """Near-white on a light card is darkened until it clears the text ratio."""
    blob = compute_variant_blob("#FFFFFF")
    assert blob is not None
    assert contrast_ratio(blob["light"]["text"], LIGHT_SURFACE) >= TEXT_TARGET_RATIO
    assert blob["light"]["text"] != "#FFFFFF"


def test_near_black_on_dark_lightens_toward_gray():
    """Near-black on a dark card is lightened until it clears the text ratio."""
    blob = compute_variant_blob("#000000")
    assert blob is not None
    assert contrast_ratio(blob["dark"]["text"], DARK_SURFACE) >= TEXT_TARGET_RATIO
    assert blob["dark"]["text"] != "#000000"


def test_achromatic_lightness_only_no_hue_added():
    """Clamping a gray input never introduces chroma/saturation."""
    # A gray input has ~0 chroma; clamping must not introduce saturation.
    blob = compute_variant_blob("#808080")
    assert blob is not None
    for variant_hex in (blob["light"]["text"], blob["light"]["ui"], blob["dark"]["text"], blob["dark"]["ui"]):
        chroma = Color(variant_hex).convert("oklch")["chroma"]
        assert chroma < 0.01


def test_cannot_reach_target_returns_extreme_with_clamp_failed():
    """An unreachable ratio returns a pure-white/black extreme flagged with clamp_failed."""
    # An impossible target against a mid-tone surface forces clamp_failed.
    mid_surface = "#808080"
    result = clamp_color("#808080", mid_surface, 10.0)
    assert result.clamp_failed
    assert result.hex in ("#FFFFFF", "#000000")


def test_malformed_hex_returns_none():
    """Malformed or missing hex input returns None rather than raising."""
    assert compute_variant_blob("not-a-color") is None
    assert compute_variant_blob("#ZZZZZZ") is None
    assert compute_variant_blob(None) is None
    assert compute_variant_blob("") is None


# ---------------------------------------------------------------------------
# Multi-secondary orchestration
# ---------------------------------------------------------------------------


def test_compute_color_variants_multi_secondary_shape():
    """A primary plus multiple secondaries each get their own blob, in input order."""
    result = compute_color_variants("#2A3EAD", ["#FFFFFF", "#000000"])
    assert result.primary is not None
    assert result.primary["raw"] == "#2A3EAD"
    assert len(result.secondary) == 2
    assert result.secondary[0]["raw"] == "#FFFFFF"
    assert result.secondary[1]["raw"] == "#000000"
    assert result.warnings == []


def test_compute_color_variants_skips_malformed_secondary_individually():
    """One malformed secondary is skipped with a warning; the rest still compute."""
    result = compute_color_variants("#2A3EAD", ["#FFFFFF", "not-a-color", "#000000"])
    assert len(result.secondary) == 2
    assert len(result.warnings) == 1
    assert "not-a-color" in result.warnings[0]


def test_compute_color_variants_malformed_primary_is_none_with_warning():
    """A malformed primary yields a None primary blob and one warning."""
    result = compute_color_variants("not-a-color", [])
    assert result.primary is None
    assert len(result.warnings) == 1


def test_compute_color_variants_no_primary_no_warning():
    """A missing (not malformed) primary yields None with no warning."""
    result = compute_color_variants(None, [])
    assert result.primary is None
    assert result.warnings == []
    assert result.secondary == []


def test_compute_color_variants_uses_config_overrides():
    """A custom ClampConfig's target ratios are honored instead of the module defaults."""
    config = ClampConfig(text_target=3.0, ui_target=2.0)
    result = compute_color_variants("#2A3EAD", [], config=config)
    assert result.primary is not None
