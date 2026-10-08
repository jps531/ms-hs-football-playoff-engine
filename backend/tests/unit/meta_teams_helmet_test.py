"""Unit tests for the resolved helmet image on GET /teams and GET /teams/{team}."""

from backend.api.routers import meta


def _team_row(helmet_image: str | None) -> tuple:
    """An 18-column team row (see meta._row_to_team_model) with the given helmet image path."""
    return (
        "Oxford", "Oxford", 2026, 7, 2,  # school, display_name, season, class, region
        "Oxford", "Chargers", "Blue", "Gold",  # city, mascot, primary_color, secondary_color
        "", "", "",  # logo_primary/secondary/tertiary
        None, None, None, None,  # latitude, longitude, zip, secondary_color_hex
        None,  # color_variants
        helmet_image,
    )  # fmt: skip


def test_helmet_path_becomes_full_url(monkeypatch):
    """A stored Cloudinary path is assembled into a full URL, like logos are."""
    monkeypatch.setenv("CLOUDINARY_BASE_URL", "https://res.cloudinary.com/demo/image/upload/")
    team = meta._row_to_team_model(_team_row("helmets/right/Oxford_2020_4"))
    assert team.helmet_url == "https://res.cloudinary.com/demo/image/upload/helmets/right/Oxford_2020_4"


def test_no_resolved_helmet_is_none():
    """A team without a helmet design covering the season gets helmet_url=None."""
    assert meta._row_to_team_model(_team_row(None)).helmet_url is None


def test_resolved_helmet_join_matches_resolution_order():
    """The join resolves helmets in the documented order and prefers the right-side view."""
    join = meta._RESOLVED_HELMET_JOIN
    assert "ORDER BY hd.is_primary DESC, hd.year_first_worn DESC" in join
    assert "helmet_covers_season(" in join
    assert "COALESCE(hd.image_right, hd.image_left)" in join
