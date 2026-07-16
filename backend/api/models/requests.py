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


class ParticipantRef(BaseModel):
    """A bracket participant identified by school name OR by (region, seed) slot.

    Accepts a plain string for backward compatibility:
    ``"School Name"`` coerces to ``ParticipantRef(school="School Name")``.
    """

    school: str | None = None
    region: int | None = Field(default=None, ge=1, le=8)
    seed: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, v: object) -> object:
        """Coerce a plain school-name string into a ``{"school": ...}`` mapping."""
        if isinstance(v, str):
            return {"school": v}
        return v

    @model_validator(mode="after")
    def _validate_ref(self) -> "ParticipantRef":
        """Require exactly one of ``school`` or the (``region``, ``seed``) pair."""
        has_name = self.school is not None
        half_slot = (self.region is None) != (self.seed is None)
        has_slot = self.region is not None and self.seed is not None
        if half_slot:
            raise ValueError("'region' and 'seed' must both be provided together")
        if has_name and has_slot:
            raise ValueError("Provide either 'school' or 'region'+'seed', not both")
        if not has_name and not has_slot:
            raise ValueError("Provide either 'school' or 'region'+'seed'")
        return self


_VALID_ROUNDS = {"second_round", "quarterfinals", "semifinals"}


class BracketGameResultRequest(BaseModel):
    """A hypothetical bracket game result — participants identified by name or (region, seed).

    Provide either ``loser`` (specific opponent) or ``round`` (unspecified opponent),
    but not both.  When ``round`` is given, all teams that could have faced the winner
    in that round are marked eliminated so they do not appear in later rounds.
    """

    winner: ParticipantRef
    loser: ParticipantRef | None = None
    round: str | None = None
    winner_score: int | None = None
    loser_score: int | None = None

    @model_validator(mode="after")
    def _validate_loser_or_round(self) -> "BracketGameResultRequest":
        """Require exactly one of ``loser`` or ``round``, and validate ``round``'s value."""
        has_loser = self.loser is not None
        has_round = self.round is not None
        if not has_loser and not has_round:
            raise ValueError("provide either 'loser' or 'round'")
        if has_loser and has_round:
            raise ValueError("provide either 'loser' or 'round', not both")
        if has_round and self.round not in _VALID_ROUNDS:
            raise ValueError(f"'round' must be one of {sorted(_VALID_ROUNDS)}")
        return self


class SimulateBracketRequest(BaseModel):
    """Request body for all three bracket/hosting simulate endpoints."""

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


class UpsertSchoolSeasonRequest(BaseModel):
    """Create or overwrite a school_seasons row with explicit class, region, and is_active.

    Use for mid-cycle changes the Regions pipeline cannot handle automatically:
    school consolidations, closures, or new schools.

    ``copy_identity_from`` — if provided, copies mascot, colors, city, zip, latitude, and
    longitude from that school into the new school's base columns immediately, so identity
    data is available before the MHSAA identity and NCES pipelines run. 404s if the source
    school does not exist.
    """

    class_: int = Field(alias="class", ge=1, le=7)
    region: int = Field(ge=1, le=8)
    is_active: bool = True
    copy_identity_from: str | None = None

    model_config = {"populate_by_name": True}


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
