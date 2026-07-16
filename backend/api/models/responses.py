"""Pydantic response models for the playoff engine REST API."""

from datetime import date, datetime

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
    """Seed odds for a single team — unweighted (50/50 scenarios) and margin-weighted."""

    p1: float
    p2: float
    p3: float
    p4: float
    p_playoffs: float
    p1_weighted: float = 0.0
    p2_weighted: float = 0.0
    p3_weighted: float = 0.0
    p4_weighted: float = 0.0
    p_playoffs_weighted: float = 0.0


class VenueModel(BaseModel):
    """Physical venue for a game (populated only when location_id is set)."""

    name: str
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


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


class ImageUploadResponse(BaseModel):
    """Result of a Cloudinary image upload."""

    path: str
    url: str


class TeamModel(BaseModel):
    """Single team with identity metadata."""

    school: str
    display_name: str
    logo_primary: str
    logo_secondary: str
    logo_tertiary: str
    season: int
    class_: int
    region: int
    city: str
    mascot: str
    primary_color: str
    secondary_color: str
    secondary_color_hex: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    zip: str | None = None


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


class BracketAdvancementOdds(BaseModel):
    """Odds of advancing to each playoff round (unweighted and margin-weighted)."""

    second_round: float
    quarterfinals: float
    semifinals: float
    finals: float
    champion: float
    second_round_weighted: float
    quarterfinals_weighted: float
    semifinals_weighted: float
    finals_weighted: float
    champion_weighted: float


class HomeGameOdds(BaseModel):
    """Conditional odds of hosting each playoff round (unweighted and margin-weighted)."""

    first_round: float
    second_round: float
    quarterfinals: float
    semifinals: float
    first_round_weighted: float
    second_round_weighted: float
    quarterfinals_weighted: float
    semifinals_weighted: float


class ComputationStateModel(BaseModel):
    """Tiebreaker computation state for a region snapshot."""

    margin_sensitive: bool
    margin_compute_status: str
    computed_at: datetime | None
    margin_computed_at: datetime | None


class TeamStandingsEntry(BaseModel):
    """Per-team odds row in a region standings response."""

    school: str
    record: RecordModel
    odds: SeedingOddsModel
    bracket_odds: BracketAdvancementOdds | None = None
    home_game_odds: HomeGameOdds | None = None
    clinched: bool
    eliminated: bool
    coin_flip_needed: bool


class ScenarioGameOutcome(BaseModel):
    """The result of one remaining game in a scenario."""

    winner: str
    loser: str


class ScenarioEntry(BaseModel):
    """One complete-scenario entry: the game results that produce a specific seeding."""

    scenario_num: int
    sub_label: str
    game_winners: list[ScenarioGameOutcome]
    tiebreaker_groups: list[list[str]] | None = None
    coinflip_groups: list[list[str]] | None = None
    outcomes: dict[str, str]  # team → seed number ("1"–"4")


class KeyInsightConditionModel(BaseModel):
    """A single game-result condition within a key insight."""

    winner: str
    loser: str


class KeyInsightModel(BaseModel):
    """A pre-computed actionable insight about a team's seeding or playoff status."""

    insight_type: str
    team: str
    seed: int | None = None
    conditions: list[KeyInsightConditionModel]
    rendered: str
    r_computed: int


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
    key_insights: list[KeyInsightModel] | None = None
    computation_state: ComputationStateModel | None = None


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------


class TeamRankEntry(BaseModel):
    """One team in a rankings response, with all odds and a convenience sort_value field."""

    school: str
    class_: int
    region: int
    as_of_date: date
    record: RecordModel
    seeding_odds: SeedingOddsModel
    bracket: BracketAdvancementOdds
    home: HomeGameOdds
    sort_value: float


class RankingsResponse(BaseModel):
    """Ranked list of teams for a class, sorted by a single odds metric."""

    season: int
    class_: int
    sort_by: str
    teams: list[TeamRankEntry]


# ---------------------------------------------------------------------------
# Hosting odds
# ---------------------------------------------------------------------------


class RoundHostingOdds(BaseModel):
    """Hosting probability for one playoff round."""

    conditional: float | None
    marginal: float | None
    conditional_weighted: float | None = None
    marginal_weighted: float | None = None


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


class ClassHostingResponse(BaseModel):
    """Hosting odds across all regions for a classification."""

    season: int
    class_: int
    as_of_date: date
    regions: list[HostingResponse]


# ---------------------------------------------------------------------------
# Bracket advancement
# ---------------------------------------------------------------------------


class BracketSlotHosting(BaseModel):
    """Hosting odds for one bracket slot across all playoff rounds."""

    first_round: RoundHostingOdds
    second_round: RoundHostingOdds
    quarterfinals: RoundHostingOdds
    semifinals: RoundHostingOdds


class TeamBracketEntry(BaseModel):
    """Per-slot bracket advancement odds and hosting odds.

    ``school`` is populated only when the team has clinched that seed position
    (``p{seed} >= 0.999``).  Before seedings are locked, ``school`` is None
    and the slot is identified by ``region`` + ``seed``.

    ``*_weighted`` fields use Elo-based win probabilities; ``null`` when no
    Elo ratings exist for the season.  ``hosting`` contains conditional and
    marginal hosting odds per round (``null`` fields for 5A–7A second_round).
    """

    region: int
    seed: int
    school: str | None
    second_round: float
    quarterfinals: float
    semifinals: float
    finals: float
    champion: float
    second_round_weighted: float | None = None
    quarterfinals_weighted: float | None = None
    semifinals_weighted: float | None = None
    finals_weighted: float | None = None
    champion_weighted: float | None = None
    hosting: BracketSlotHosting | None = None


class BracketParticipant(BaseModel):
    """A team occupying one side of a bracket game slot."""

    region: int
    seed: int
    school: str | None = None


class BracketGameResult(BaseModel):
    """Outcome of a completed bracket game."""

    winner: BracketParticipant
    loser: BracketParticipant
    winner_score: int | None = None
    loser_score: int | None = None
    simulated: bool = False


class BracketGame(BaseModel):
    """One game node in the bracket tree.

    R1 leaf nodes have ``slot``, ``home``, and ``away`` set (from the playoff
    format).  All later-round nodes have ``feeds_from`` set: a pair of 0-based
    indices into the *previous* round's game list indicating which two R1-path
    winners meet here.  ``slot``/``home``/``away`` are ``None`` for non-R1 nodes.

    ``participant_a`` and ``participant_b`` are positional: ``participant_a``
    corresponds to the ``home`` format slot on R1 nodes and to the
    ``feeds_from[0]`` winner on R2+ nodes — not a hosting indicator.
    ``home_school`` is the authoritative field for who hosts the game.
    ``result`` is set once the game has a confirmed or simulated outcome.
    """

    slot: int | None = None
    home: tuple[int, int] | None = None
    away: tuple[int, int] | None = None
    feeds_from: list[int] | None = None
    round: str | None = None
    participant_a: BracketParticipant | None = None
    participant_b: BracketParticipant | None = None
    home_school: str | None = None
    result: BracketGameResult | None = None


class ChampionshipGame(BaseModel):
    """The championship game, fed by the two Semifinal winners."""

    feeds_from_halves: list[str] = ["N", "S"]
    north_participant: BracketParticipant | None = None
    south_participant: BracketParticipant | None = None
    result: BracketGameResult | None = None


class BracketLayout(BaseModel):
    """Pre-computed bracket tree for both halves plus the championship.

    ``halves`` maps each bracket half identifier (``"N"`` or ``"S"``) to a list
    of rounds.  ``rounds[0]`` contains the First Round games (``BracketGame``
    nodes with ``slot/home/away``).  Each subsequent round contains games whose
    ``feeds_from`` pair references the two preceding-round indices that produced
    the participants.  The final element of each half's round list is the
    Semifinal.

    ``championship`` carries the two SF-winner participants and the result once
    the championship game has been played.
    """

    halves: dict[str, list[list[BracketGame]]]
    championship: ChampionshipGame


class BracketResponse(BaseModel):
    """Full bracket advancement odds for a class (both halves)."""

    season: int
    class_: int
    bracket_layout: BracketLayout
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
    final: bool = False
    round: str | None = None
    kickoff_time: datetime | None = None
    overtime: int | None = None
    game_quarter: int | None = None
    game_clock: str | None = None
    source: str | None = None
    venue: VenueModel | None = None
    helmet_a: HelmetDesignModel | None = None
    helmet_b: HelmetDesignModel | None = None


class PreGameWinProbResponse(BaseModel):
    """Pre-game win probability with Elo context."""

    team_a: str
    team_b: str
    elo_a: float
    elo_b: float
    elo_date_a: date
    elo_date_b: date
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
    as_of_date: date
    games_played: int
    computed_at: datetime


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


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class LocationModel(BaseModel):
    """A venue in the locations table."""

    id: int
    name: str
    city: str | None = None
    home_team: str | None = None


class LocationDetailModel(BaseModel):
    """A venue with full coordinate data."""

    id: int
    name: str
    city: str | None = None
    home_team: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class OverrideAuditRow(BaseModel):
    """One active manual override entry."""

    source: str
    key: str
    value: str


class PlayoffFormatSeedResult(BaseModel):
    """Result of seeding a playoff bracket format."""

    season: int
    classes_inserted: int
    slots_inserted: int
    dry_run: bool


class ChampionshipGameRow(BaseModel):
    """One game row updated by assign-championship-venue."""

    school: str
    date: date
    opponent: str
    class_: int


class AssignChampionshipVenueResult(BaseModel):
    """Result of assigning a championship venue."""

    season: int
    location_id: int
    location_name: str
    games_updated: int
    games: list[ChampionshipGameRow]
    dry_run: bool


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


class SubmissionCreatedResponse(BaseModel):
    """Returned after a user successfully creates a submission."""

    id: int
    type: str
    school: str | None
    submitted_at: datetime


class SubmissionSummary(BaseModel):
    """A submission row as returned in list views."""

    id: int
    type: str
    status: str
    school: str | None
    submitted_at: datetime
    reviewed_at: datetime | None


class SubmissionDetail(SubmissionSummary):
    """A single submission with its full payload and moderator notes."""

    payload: dict
    moderator_notes: str | None


# ---------------------------------------------------------------------------
# Auth / Users
# ---------------------------------------------------------------------------


class UserProfileResponse(BaseModel):
    """Full profile returned from GET /users/me."""

    id: int
    email: str
    display_name: str
    role: str
    favorite_team: str | None
    is_active: bool
    created_at: datetime
    phone: str | None
    hometown: str | None
    followed_teams: list[str]
    games_attended_count: int


class AttendedGameModel(BaseModel):
    """A game the user has marked as attended."""

    school: str
    date: date
    opponent: str
    result: str | None


class UserAdminRow(BaseModel):
    """User row as seen in the owner-only admin list."""

    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
