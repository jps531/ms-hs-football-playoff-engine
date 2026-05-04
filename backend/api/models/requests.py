"""Pydantic request body models for the playoff engine REST API."""

from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Override field type aliases — used in request bodies and DELETE path validation
# ---------------------------------------------------------------------------

SchoolOverrideField = Literal[
    "display_name",
    "mascot",
    "primary_color",
    "secondary_color",
    "primary_color_hex",
    "secondary_color_hex",
    "latitude",
    "longitude",
]

GameOverrideField = Literal[
    "location",
    "location_id",
    "points_for",
    "points_against",
    "region_game",
    "round",
    "kickoff_time",
]

LocationOverrideField = Literal["home_team", "latitude", "longitude"]


class GameResultRequest(BaseModel):
    """A single hypothetical game result for what-if simulation."""

    winner: str
    loser: str
    winner_score: int | None = None
    loser_score: int | None = None


class SimulateRegionRequest(BaseModel):
    """Request body for region what-if simulation endpoints."""

    results: list[GameResultRequest] = Field(min_length=1, max_length=20)


class BracketGameResultRequest(BaseModel):
    """A single hypothetical bracket game result."""

    home_region: int
    home_seed: int
    away_region: int
    away_seed: int
    home_wins: bool


class SimulateBracketRequest(BaseModel):
    """Request body for bracket what-if simulation endpoints."""

    results: list[BracketGameResultRequest] = Field(min_length=1, max_length=20)


class LiveWinProbRequest(BaseModel):
    """Request body for live (in-game regulation) win probability."""

    pregame_prob: float = Field(gt=0.0, lt=1.0)
    current_margin: int
    seconds_remaining: int = Field(ge=0, le=2880)


class OTWinProbRequest(BaseModel):
    """Request body for OT mid-possession win probability."""

    pregame_prob: float = Field(gt=0.0, lt=1.0)
    ot_scored_margin: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class PlayoffSlotRequest(BaseModel):
    """One first-round matchup slot in the bracket."""

    slot: int
    home_region: int
    home_seed: int
    away_region: int
    away_seed: int
    north_south: str = Field(pattern="^[NS]$")


class PlayoffClassRequest(BaseModel):
    """Bracket structure for a single MHSAA classification."""

    class_: int = Field(alias="class", ge=1, le=7)
    num_regions: int
    seeds_per_region: int = 4
    num_rounds: int
    notes: str | None = None
    slots: list[PlayoffSlotRequest] = Field(min_length=1)

    model_config = {"populate_by_name": True}


class PlayoffFormatRequest(BaseModel):
    """Request body for seeding a full season's playoff bracket format."""

    season: int
    classes: list[PlayoffClassRequest] = Field(min_length=1)


class AssignChampionshipVenueRequest(BaseModel):
    """Request body for assigning a venue to championship games."""

    season: int
    location_id: int
    class_: int | None = Field(default=None, alias="class", ge=1, le=7)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Override endpoints
# ---------------------------------------------------------------------------


class SetSchoolOverrideRequest(BaseModel):
    """Set one key in a school's overrides JSONB, shadowing the pipeline-written value."""

    field: SchoolOverrideField
    value: str


class SetGameOverrideRequest(BaseModel):
    """Set one key in a game row's overrides JSONB, shadowing the pipeline-written value."""

    field: GameOverrideField
    value: str


class SetLocationOverrideRequest(BaseModel):
    """Set one key in a location's overrides JSONB, shadowing the base column value."""

    field: LocationOverrideField
    value: str


# ---------------------------------------------------------------------------
# Game helmet assignment
# ---------------------------------------------------------------------------


class SetGameHelmetRequest(BaseModel):
    """Assign or clear the helmet design worn by a school in a specific game."""

    helmet_design_id: int | None


# ---------------------------------------------------------------------------
# School season flags
# ---------------------------------------------------------------------------


class PatchSchoolSeasonRequest(BaseModel):
    """Manually-managed school_season fields (pipeline never writes these)."""

    is_active: bool


# ---------------------------------------------------------------------------
# Location CRUD
# ---------------------------------------------------------------------------


class CreateLocationRequest(BaseModel):
    """Create a new venue in the locations table."""

    name: str
    city: str | None = None
    home_team: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PatchLocationRequest(BaseModel):
    """Partial update for an existing venue — only provided fields are written."""

    name: str | None = None
    city: str | None = None
    home_team: str | None = None
    latitude: float | None = None
    longitude: float | None = None


# ---------------------------------------------------------------------------
# Helmet design CRUD
# ---------------------------------------------------------------------------


class YearsWornRangeInput(BaseModel):
    """A contiguous span of seasons a helmet design was worn."""

    start: int
    end: int


class CreateHelmetDesignRequest(BaseModel):
    """Create a new helmet design record. Upload images separately via /images/helmets/{id}/{type}."""

    school: str
    year_first_worn: int
    year_last_worn: int | None = None
    years_worn: list[YearsWornRangeInput] | None = None
    color: str | None = None
    finish: str | None = None
    facemask_color: str | None = None
    logo: str | None = None
    stripe: str | None = None
    tags: list[str] = []
    notes: str | None = None


class PatchHelmetDesignRequest(BaseModel):
    """Partial update for a helmet design — only provided fields are written. Image columns are managed via /images/helmets/."""

    year_first_worn: int | None = None
    year_last_worn: int | None = None
    years_worn: list[YearsWornRangeInput] | None = None
    color: str | None = None
    finish: str | None = None
    facemask_color: str | None = None
    logo: str | None = None
    stripe: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# User submissions
# ---------------------------------------------------------------------------


class ColorEntry(BaseModel):
    """A single named color with its hex code."""

    name: str
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class SubmitColorsRequest(BaseModel):
    """Submit a school color correction. At least one of primary_color or secondary_colors is required."""

    school: str
    primary_color: ColorEntry | None = None
    secondary_colors: list[ColorEntry] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _require_at_least_one(self) -> "SubmitColorsRequest":
        """Require at least one of primary_color or secondary_colors."""
        if self.primary_color is None and not self.secondary_colors:
            raise ValueError("At least one of primary_color or secondary_colors must be provided")
        return self


class SubmitLocationRequest(BaseModel):
    """Submit corrected GPS coordinates for a school."""

    school: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class SubmitScoreRequest(BaseModel):
    """Submit a corrected game score."""

    school: str
    date: date_type
    points_for: int = Field(ge=0)
    points_against: int = Field(ge=0)


class SubmitFeedbackRequest(BaseModel):
    """Submit general feedback visible to moderators."""

    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


class ModerationDecisionRequest(BaseModel):
    """Optional body for a moderator approve/reject action."""

    notes: str | None = None


# ---------------------------------------------------------------------------
# Auth / Users
# ---------------------------------------------------------------------------


class PatchUserRequest(BaseModel):
    """Body for PATCH /users/me — all fields optional."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = None
    hometown: str | None = None
    favorite_team: str | None = None


class SetUserRoleRequest(BaseModel):
    """Body for PATCH /users/{id}/role — owner cannot be assigned via API."""

    role: Literal["user", "moderator"]


class SetUserActiveRequest(BaseModel):
    """Body for PATCH /users/{id}/active."""

    is_active: bool
