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
