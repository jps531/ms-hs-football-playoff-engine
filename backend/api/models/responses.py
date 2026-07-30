"""Pydantic response models for the playoff engine REST API."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

# Alias used where a field is literally named `date` and also needs a default
# value (e.g. `date: date | None = None`): in a class body, an annotated
# assignment binds the value to the target name *before* evaluating the
# annotation, so a same-named bare `date` annotation resolves to the
# just-assigned `None` instead of the `datetime.date` class. Fields that omit
# the default (`date: date | None`, no `= None`) aren't affected and don't
# need this alias.
_Date = date

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


class SeasonDateEntry(BaseModel):
    """One notable date for a season's timeline scrubber.

    ``kind`` is ``"games"`` (at least one game was played) or
    ``"season_start"`` (one day before the season's first game, always
    ``week: 0``). ``week`` is a derived, 1-indexed, Monday-Sunday-bucketed
    week number that counts continuously through the whole season —
    regular season *and* playoffs — so it's always populated for
    ``"games"`` dates; it is **not** a signal for "is this a playoff date"
    (use ``round is not None`` for that). ``round`` is set only for
    unambiguous playoff game dates. ``num_games`` is set only for
    ``"games"`` dates (deduplicated contest count, statewide unless the
    optional ``class`` param scopes the request).

    1A-4A and 5A-7A run offset playoff schedules, so a single date can be a
    playoff date for one group of classes and still regular season (or a
    different round) for another. When that happens (and no ``class`` param
    was given to resolve it), ``round`` is ``null`` for that date rather
    than guessing — ``week`` is still populated — but ``description`` still
    gives a human label, e.g. ``"Week 11 (5A-7A) / First Round (1A-4A)"``.
    On an unambiguous date, ``description`` is just the single label
    (``"Week 13"``, ``"First Round"``) — except the championship, where an
    unscoped ``description`` reads ``"Championship Games"`` (plural; a
    statewide date usually covers several classes' separate games) while
    scoped to one ``class`` it stays ``"Championship Game"`` (singular).
    ``round`` is ``"championship_game"`` either way. Scoped to one
    ``class``, every date is unambiguous.
    """

    date: date
    kind: str  # "games" | "season_start"
    week: int | None = None
    round: str | None = None
    num_games: int | None = None
    description: str | None = None


class SeasonDatesResponse(BaseModel):
    """The set of notable dates for a season, for a timeline scrubber."""

    season: int
    dates: list[SeasonDateEntry]


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
    """P(hosts round | reaches round) for each playoff round (unweighted and margin-weighted)."""

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


class PathGameRefModel(BaseModel):
    """A game reference (school/date/opponent) used inside a ``margin_sum`` condition."""

    school: str
    date: date | None
    opponent: str


class PathConditionModel(BaseModel):
    """One atomic condition within a scenario path's AND-group.

    ``type`` discriminates the condition kind (mirrors
    ``scenario_serializers.serialize_condition``'s tagged shape): ``"game_result"``
    is the common single-game case with ``school``/``date``/``opponent``/
    ``required_result`` populated; ``"margin_sum"`` carries a linear margin
    constraint across multiple games via ``games``/``op``/``threshold`` instead of
    a single school/opponent; ``"coin_flip"`` and ``"pd_rank"`` cover
    tiebreaker-only conditions with no associated remaining game (``description``
    carries the fallback text since there's nothing to map to a schedule row).
    ``"bracket_advances"``/``"seed_required"`` mirror ``HomeGameCondition``
    (used for bracket-slot ``host_conditions``): ``school`` carries the team
    name (``HomeGameCondition.team_name``), ``region``/``seed`` identify the
    bracket position the condition is about, ``round_name`` is set only for
    ``"bracket_advances"``, and ``description`` carries a rendered sentence
    (e.g. "Taylorsville advances to Quarterfinals").
    """

    type: str = "game_result"  # "game_result" | "margin_sum" | "coin_flip" | "pd_rank" | "bracket_advances" | "seed_required"
    school: str | None = None
    date: _Date | None = None
    opponent: str | None = None
    required_result: str | None = None  # "win" | "loss"
    margin_class: str | None = None
    games: list[PathGameRefModel] | None = None  # populated for "margin_sum"
    op: str | None = None  # populated for "margin_sum"
    threshold: int | None = None  # populated for "margin_sum"
    description: str | None = None  # human-readable fallback for coin_flip / pd_rank / bracket_advances / seed_required
    region: int | None = None  # populated for "bracket_advances" / "seed_required"
    seed: int | None = None  # populated for "bracket_advances" / "seed_required"
    round_name: str | None = None  # populated for "bracket_advances" only


class PathOutcomeModel(BaseModel):
    """The seeding/playoff outcome a scenario path leads to."""

    type: str  # "seed" | "playoffs" | "eliminated"
    value: int | None = None  # seed number when type == "seed"


class ScenarioPathModel(BaseModel):
    """One minimized path (OR-of-AND conditions) to a specific outcome for a team.

    ``p`` is the outcome's existing unweighted seeding probability (``p1``-``p4``
    for a seed outcome, ``p_playoffs`` for playoffs, ``1 - p_playoffs`` for
    eliminated) — not a per-branch probability. ``conditions`` OR-groups are
    already ordered broadest/most-likely-first by the underlying boolean
    minimizer (``_sort_atom_list``).
    """

    outcome: PathOutcomeModel
    p: float
    conditions: list[list[PathConditionModel]]
    human_text: str


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
    paths: list[ScenarioPathModel] | None = None


class TeamStatusModel(BaseModel):
    """One team's current status within a region, for the summary status strip."""

    school: str
    status: str  # "clinched" | "alive" | "eliminated"
    clinched_seed: int | None = None
    record: RecordModel


class RegionLeaderModel(BaseModel):
    """The current #1 team in a region, by actual current standing."""

    school: str
    region_wins: int
    region_losses: int


class RegionSummaryCard(BaseModel):
    """One region's compact summary card for the statewide grand view."""

    region: int
    leader: RegionLeaderModel
    num_teams: int
    num_clinched: int
    num_eliminated: int
    teams_alive: int
    volatility: float
    statuses: list[TeamStatusModel]


class ClassSummary(BaseModel):
    """One classification's regions within the statewide standings summary."""

    class_: int
    regions: list[RegionSummaryCard]


class StandingsSummaryResponse(BaseModel):
    """Statewide standings summary: one card per region across every class."""

    season: int
    as_of_date: date
    classes: list[ClassSummary]


class InsightModel(BaseModel):
    """One deduped key insight in the statewide insights feed."""

    as_of_date: date
    class_: int
    region: int
    teams: list[str]
    human_text: str
    kind: str | None = None


class InsightsResponse(BaseModel):
    """Statewide, deduped, newest-first feed of key insights."""

    insights: list[InsightModel]


class ScenarioGameOutcome(BaseModel):
    """The result of one remaining game in a scenario."""

    winner: str
    loser: str


class ScenarioEntry(BaseModel):
    """One complete-scenario entry: the game results that produce a specific seeding."""

    scenario_num: int
    sub_label: str
    title: str | None = None
    game_winners: list[ScenarioGameOutcome]
    tiebreaker_groups: list[list[str]] | None = None
    coinflip_groups: list[list[str]] | None = None
    outcomes: dict[str, str]  # team → seed number ("1"–"4")
    conditions: list[dict] | None = (
        None  # structured form of `title` (GameResult/MarginCondition/PDRankCondition dicts)
    )


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


class ClassRegionStandings(BaseModel):
    """One region's full standings table within the class view (no scenarios)."""

    region: int
    teams: list[TeamStandingsEntry]


class ClassStandingsResponse(BaseModel):
    """Full standings tables for every region in one class, one request."""

    season: int
    class_: int
    as_of_date: date
    regions: list[ClassRegionStandings]


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

    p_host_given_reach: float | None
    p_host_overall: float | None
    p_host_given_reach_weighted: float | None = None
    p_host_overall_weighted: float | None = None


class TeamHostingEntry(BaseModel):
    """Per-team hosting odds across all rounds."""

    school: str
    first_round: RoundHostingOdds
    second_round: RoundHostingOdds
    quarterfinals: RoundHostingOdds
    semifinals: RoundHostingOdds
    scenarios: dict[str, Any] | None = None


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
    Elo ratings exist for the season.  ``hosting`` contains ``p_host_given_reach``
    and ``p_host_overall`` hosting odds per round (``null`` fields for 5A–7A second_round).
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


class SlotOutlookTeam(BaseModel):
    """One candidate team's outlook for a single bracket slot/round.

    ``p_reach`` is the probability the team plays in this slot's game;
    ``p_host_overall`` is always ``p_reach * p_host_given_reach``, computed
    server-side for consistency. ``*_weighted`` fields use Elo-based win
    probabilities; ``null`` when no Elo ratings exist for the season.
    ``host_conditions`` is ``null`` unless the request passed
    ``include_conditions=true``; when present it's the OR-of-AND-groups of
    conditions under which this team would host, given it reaches the round
    (an empty list means "computed, but this team never hosts"). Each group
    is a list of ``PathConditionModel``. ``reach_conditions`` is always
    ``null`` for now — structured condition derivation for it is a separate,
    undesigned follow-up (see docs/API_FRONTEND_GAPS.md §3).
    """

    school: str
    p_reach: float
    p_host_given_reach: float | None
    p_host_overall: float
    p_reach_weighted: float | None = None
    p_host_given_reach_weighted: float | None = None
    p_host_overall_weighted: float | None = None
    reach_conditions: list[list[PathConditionModel]] | None = None
    host_conditions: list[list[PathConditionModel]] | None = None


class SlotOutlookResponse(BaseModel):
    """Every team still alive for one bracket slot/round, ranked by chance of reaching it."""

    season: int
    class_: int
    round: str
    slot: int
    as_of_date: date
    teams: list[SlotOutlookTeam]


class BracketParticipant(BaseModel):
    """A team occupying one side of a bracket game slot."""

    region: int
    seed: int
    school: str | None = None


class BracketGameResult(BaseModel):
    """Outcome of a completed bracket game."""

    winner: BracketParticipant
    loser: BracketParticipant | None = None
    winner_score: int | None = None
    loser_score: int | None = None
    simulated: bool = False


class BracketGame(BaseModel):
    """One game node in the bracket tree.

    R1 leaf nodes have ``slot`` set and ``participant_a``/``participant_b``
    pre-populated with region and seed (school is null until seedings clinch).
    All later-round nodes have ``feeds_from`` set: a pair of 0-based indices
    into the *previous* round's game list indicating which two winners meet here.
    ``slot`` is ``None`` for non-R1 nodes.

    ``participant_a`` and ``participant_b`` are positional: on R1 nodes
    ``participant_a`` is the format-designated home side; on R2+ nodes it is the
    ``feeds_from[0]`` winner — neither implies hosting.
    ``home_team`` is the authoritative ``{ region, seed, school }`` object for who
    hosts the game. Always set on R1 nodes (region/seed known from the format;
    school null until seedings clinch). Set on R2+ nodes when one participant's
    p_host_given_reach hosting odds are 1.0; null when hosting is not yet determined.
    ``result`` is set once the game has a confirmed or simulated outcome.
    """

    slot: int | None = None
    feeds_from: list[int] | None = None
    round: str | None = None
    participant_a: BracketParticipant | None = None
    participant_b: BracketParticipant | None = None
    home_team: BracketParticipant | None = None
    result: BracketGameResult | None = None
    venue: VenueModel | None = None


class ChampionshipGame(BaseModel):
    """The championship game, fed by the two Semifinal winners."""

    feeds_from_halves: list[str] = ["N", "S"]
    north_participant: BracketParticipant | None = None
    south_participant: BracketParticipant | None = None
    result: BracketGameResult | None = None
    venue: VenueModel | None = None


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
    pregame_prob: float | None = None
    live_prob: float | None = None
    prob_as_of: datetime | None = None


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


class UpsetModel(BaseModel):
    """A finished game the model rated as an upset for the winner."""

    school: str
    opponent: str
    date: date
    points_for: int
    points_against: int
    pregame_prob: float
    class_: int
    region: int
    region_game: bool


class UpsetsResponse(BaseModel):
    """Finished games sorted by the winner's pregame win probability, ascending."""

    upsets: list[UpsetModel]


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


class MoverModel(BaseModel):
    """A team's Elo change between two rating snapshots."""

    school: str
    class_: int
    region: int
    elo_before: float
    elo_after: float
    delta: float


class MoversResponse(BaseModel):
    """Biggest Elo risers/fallers between two rating snapshots."""

    risers: list[MoverModel]
    fallers: list[MoverModel]


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
    classes: list[int]
    games_updated: int
    games: list[ChampionshipGameRow]
    dry_run: bool


class ChampionshipVenueAssignment(BaseModel):
    """One season/class's currently assigned championship venue."""

    season: int
    class_: int
    location_id: int
    location_name: str


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
