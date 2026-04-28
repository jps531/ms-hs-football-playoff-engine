"""Pydantic request body models for the playoff engine REST API."""

from pydantic import BaseModel, Field


class GameResultRequest(BaseModel):
    """A single hypothetical game result for what-if simulation."""

    winner: str
    loser: str
    winner_score: int | None = None
    loser_score: int | None = None


class SimulateRegionRequest(BaseModel):
    """Request body for region what-if simulation endpoints."""

    results: list[GameResultRequest] = Field(min_length=1)


class BracketGameResultRequest(BaseModel):
    """A single hypothetical bracket game result."""

    home_region: int
    home_seed: int
    away_region: int
    away_seed: int
    home_wins: bool


class SimulateBracketRequest(BaseModel):
    """Request body for bracket what-if simulation endpoints."""

    results: list[BracketGameResultRequest] = Field(min_length=1)


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
