"""Pydantic response models for the playoff engine REST API."""

from datetime import date

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class RecordModel(BaseModel):
    """Overall and region W/L record."""

    wins: int
    losses: int
    ties: int
    region_wins: int
    region_losses: int
    region_ties: int


class SeedingOddsModel(BaseModel):
    """Equal-probability seed odds for a single team."""

    p1: float
    p2: float
    p3: float
    p4: float
    p_playoffs: float


class RemainingGameModel(BaseModel):
    """An unplayed region game."""

    team_a: str
    team_b: str
    location_a: str | None = None


# ---------------------------------------------------------------------------
# Meta / navigation
# ---------------------------------------------------------------------------


class SeasonModel(BaseModel):
    """A single available season."""

    season: int


class RegionSummary(BaseModel):
    """One region within a class, with team count."""

    region: int
    team_count: int


class ClassStructure(BaseModel):
    """One classification with its regions."""

    class_: int
    regions: list[RegionSummary]


class SeasonStructureResponse(BaseModel):
    """All classifications and regions for a season."""

    season: int
    classes: list[ClassStructure]


class TeamModel(BaseModel):
    """Single team with identity metadata."""

    school: str
    display_name: str
    display_logo: str
    season: int
    class_: int
    region: int
    city: str
    mascot: str
    primary_color: str
    secondary_color: str
    maxpreps_logo: str


class YearsWornRange(BaseModel):
    """A contiguous span of seasons a helmet design was worn."""

    start: int
    end: int


class HelmetDesignModel(BaseModel):
    """A single helmet design variant for a school."""

    id: int | None = None
    school: str
    year_first_worn: int
    year_last_worn: int | None = None
    years_worn: list[YearsWornRange] | None = None
    image_left: str | None = None
    image_right: str | None = None
    photo: str | None = None
    color: str | None = None
    finish: str | None = None
    facemask_color: str | None = None
    logo: str | None = None
    stripe: str | None = None
    tags: list[str] = []
    notes: str | None = None


# ---------------------------------------------------------------------------
# Standings / scenarios
# ---------------------------------------------------------------------------


class TeamStandingsEntry(BaseModel):
    """Per-team odds row in a region standings response."""

    school: str
    record: RecordModel
    odds: SeedingOddsModel
    clinched: bool
    eliminated: bool
    coin_flip_needed: bool


class ScenarioEntry(BaseModel):
    """One complete-scenario entry (human-readable)."""

    outcomes: dict[str, str]  # team → seed label


class StandingsResponse(BaseModel):
    """Region standings with seeding odds and (if available) scenarios."""

    season: int
    class_: int
    region: int
    as_of_date: date
    scenarios_available: bool
    remaining_games: list[RemainingGameModel]
    teams: list[TeamStandingsEntry]
    scenarios: list[ScenarioEntry] | None = None


# ---------------------------------------------------------------------------
# Hosting odds
# ---------------------------------------------------------------------------


class RoundHostingOdds(BaseModel):
    """Hosting probability for one playoff round."""

    conditional: float | None
    marginal: float | None


class TeamHostingEntry(BaseModel):
    """Per-team hosting odds across all rounds."""

    school: str
    first_round: RoundHostingOdds
    second_round: RoundHostingOdds
    quarterfinals: RoundHostingOdds
    semifinals: RoundHostingOdds


class HostingResponse(BaseModel):
    """Region hosting odds response."""

    season: int
    class_: int
    region: int
    as_of_date: date
    teams: list[TeamHostingEntry]


# ---------------------------------------------------------------------------
# Bracket advancement
# ---------------------------------------------------------------------------


class TeamBracketEntry(BaseModel):
    """Per-slot bracket advancement odds.

    ``school`` is populated only when the team has clinched that seed position
    (``p{seed} >= 0.999``).  Before seedings are locked, ``school`` is None
    and the slot is identified by ``region`` + ``seed``.
    """

    region: int
    seed: int
    school: str | None
    second_round: float
    quarterfinals: float
    semifinals: float
    finals: float
    champion: float


class BracketResponse(BaseModel):
    """Full bracket advancement odds for a class (both halves)."""

    season: int
    class_: int
    teams: list[TeamBracketEntry]


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


class GameModel(BaseModel):
    """A single game (played or upcoming)."""

    game_id: int | None = None
    season: int
    date: date | None
    team_a: str
    team_b: str
    score_a: int | None = None
    score_b: int | None = None
    location_a: str | None = None
    is_region_game: bool
    status: str | None = None


class PreGameWinProbResponse(BaseModel):
    """Pre-game win probability with Elo context."""

    team_a: str
    team_b: str
    elo_a: float
    elo_b: float
    location_a: str | None
    hfa_adjustment: float
    p_team_a: float


class LiveWinProbResponse(BaseModel):
    """In-game win probability (regulation)."""

    p_team_a: float


class OTWinProbResponse(BaseModel):
    """OT mid-possession win probability."""

    p_team_a: float


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


class TeamRatingModel(BaseModel):
    """Current Elo and RPI for a single team."""

    school: str
    season: int
    elo: float
    rpi: float | None


class EloSnapshot(BaseModel):
    """Single date point in an Elo trend series."""

    date: date
    elo: float
    rpi: float | None


class EloTrendResponse(BaseModel):
    """Elo time-series for one team."""

    school: str
    season: int
    snapshots: list[EloSnapshot]
