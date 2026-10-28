"""The engine's settings that more than one part of the code, or the site's wording, depends on.

Each is defined once here. The pages say some of them in words (the About page's "5 or fewer" and
"50,000 times", the bracket's "under 0.5%"); ``backend/tests/unit/copy_settings_test.py`` fails if
the wording and the setting stop matching, so change both together.
"""

FULL_MARGINS_MAX_LEFT = 5
"""With this many region games left or fewer, every winning margin is worked through: the full
scenario list is shown, and a race that turns on point differential is stated exactly ("beats Magee
by 8-10"). The headline's scenario paths are margin-accurate only here."""

ENUMERATE_MAX_LEFT = 15
"""With this many region games left or fewer, every win/loss outcome is enumerated; above it the
odds come from Monte Carlo sampling and no scenarios are enumerated."""

MONTE_CARLO_SAMPLES = 50_000
"""Simulated seasons per odds mode when there are more than ``ENUMERATE_MAX_LEFT`` games left."""

LISTING_FLOOR = 0.005
"""A bracket pairing under this chance in both odds modes isn't listed; the API folds it into
``other`` (the pages say "under 0.5%")."""

PLAYOFF_SEEDS = 4
"""Teams per region that make the playoffs (MHSAA: the top four)."""

CLASSES = (1, 2, 3, 4, 5, 6, 7)
"""MHSAA classifications, 1A-7A."""
