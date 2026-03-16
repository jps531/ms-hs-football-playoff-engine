"""Dataclasses shared across the playoff engine.

Includes raw and processed game representations, standings odds, and
DB-mapped objects for schools, locations, brackets, and bracket games.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

# -------------------------
# Win probability interface
# -------------------------

#: Injectable win probability function type.
#: Called as ``win_prob_fn(team_a, team_b, date_str)`` where ``team_a`` is the
#: lexicographically-first team (per RemainingGame convention).  Returns the
#: probability that ``team_a`` beats ``team_b`` on the given date.
WinProbFn = Callable[[str, str, str | None], float]


def equal_win_prob(_team_a: str, _team_b: str, _date_str: str | None = None) -> float:
    """Return 0.5 for every matchup (equal-probability default).

    Args:
        _team_a: Lexicographically-first team name (unused).
        _team_b: Lexicographically-second team name (unused).
        _date_str: Optional game date (unused in this implementation).

    Returns:
        Always ``0.5``.
    """
    return 0.5


# -------------------------
# Scenario results container
# -------------------------


@dataclass
class ScenarioResults:
    """Return value of ``determine_scenarios()``.

    Bundles both unweighted (equal-probability) and win-probability-weighted
    seed counts so callers can compute odds under either assumption without
    re-running enumeration.
    """

    first_counts: Counter
    second_counts: Counter
    third_counts: Counter
    fourth_counts: Counter
    denom: float
    minimized_scenarios: defaultdict
    coinflip_teams: set[str]
    first_counts_weighted: Counter
    second_counts_weighted: Counter
    third_counts_weighted: Counter
    fourth_counts_weighted: Counter
    denom_weighted: float

# -------------------------
# Standings (region W/L/T record used by scenario engine)
# -------------------------


@dataclass(frozen=True)
class Standings:
    """Region W/L/T record for a single school, as returned by the DB stored proc."""

    school: str
    class_: int
    region: int
    season: int
    wins: int
    losses: int
    ties: int
    region_wins: int
    region_losses: int
    region_ties: int


# -------------------------
# Data Classes
# -------------------------


# --- Data class for a school (joined view of schools + school_seasons) ---
@dataclass
class School:
    """In-memory representation of a school for a given season.

    Maps to a JOIN of the ``schools`` table (static identity metadata) and
    the ``school_seasons`` table (per-season class/region assignment).
    When writing to the database, use ``as_schools_tuple()`` for the
    ``schools`` table and ``as_school_seasons_tuple()`` for ``school_seasons``.
    """

    school: str
    season: int
    class_: int
    region: int
    city: str = ""
    zip: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    mascot: str = ""
    maxpreps_id: str = ""
    maxpreps_url: str = ""
    maxpreps_logo: str = ""
    primary_color: str = ""
    secondary_color: str = ""

    def as_schools_tuple(self):
        """Positional tuple for the ``schools`` table (static fields only)."""
        return (
            self.school,
            self.city,
            self.zip,
            self.latitude,
            self.longitude,
            self.mascot,
            self.maxpreps_id,
            self.maxpreps_url,
            self.maxpreps_logo,
            self.primary_color,
            self.secondary_color,
        )

    def as_school_seasons_tuple(self):
        """Positional tuple for the ``school_seasons`` table."""
        return (self.school, self.season, self.class_, self.region)

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a School object from a database row tuple or sequence.

        Args:
            row: An iterable of column values. Accepts rows with 4 columns
                (school, season, class_, region) or 14 columns (all fields,
                as returned by a JOIN of schools + school_seasons).

        Returns:
            A School instance populated from the row.

        Raises:
            ValueError: If the row has an unexpected number of columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)

        if len(row) == 4:
            school, season, class_, region = row
            return cls(school=school, season=season, class_=class_, region=region)
        elif len(row) >= 14:
            (
                school,
                season,
                class_,
                region,
                city,
                zip,
                latitude,
                longitude,
                mascot,
                maxpreps_id,
                maxpreps_url,
                maxpreps_logo,
                primary_color,
                secondary_color,
            ) = row[:14]
            return cls(
                school=school,
                season=season,
                class_=class_,
                region=region,
                city=city or "",
                zip=zip or "",
                latitude=latitude or 0.0,
                longitude=longitude or 0.0,
                mascot=mascot or "",
                maxpreps_id=maxpreps_id or "",
                maxpreps_url=maxpreps_url or "",
                maxpreps_logo=maxpreps_logo or "",
                primary_color=primary_color or "",
                secondary_color=secondary_color or "",
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data class for a row in the game table ---
@dataclass
class Game:
    """DB-mapped dataclass for a row in the ``games`` table."""

    school: str
    date: date
    season: int
    location_id: int | None
    points_for: int | None
    points_against: int | None
    round: str | None
    kickoff_time: str | None  # ISO 8601 format, e.g., "2023-09-01T19:00:00Z"
    opponent: str | None
    result: str | None
    game_status: str | None
    source: str | None
    location: str = "neutral"
    region_game: bool = False
    final: bool = False
    overtime: int = 0

    def as_db_tuple(self):
        """Return a positional tuple suitable for INSERT/UPDATE queries."""
        return (
            self.school,
            self.date,
            self.season,
            self.location_id,
            self.points_for,
            self.points_against,
            self.round,
            self.kickoff_time,
            self.opponent,
            self.result,
            self.game_status,
            self.source,
            self.location,
            self.region_game,
            self.final,
            self.overtime,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a Game object from a DB row (tuple, list, or dict).

        Args:
            row: Either a dict with named fields (e.g., psycopg2 RealDictRow)
                or a positional tuple/list with 16 columns.

        Returns:
            A Game instance populated from the row.

        Raises:
            ValueError: If a dict row is missing the required ``date`` field,
                or a tuple row has an unexpected number of columns.
        """
        # Handle dict-like objects (e.g., psycopg2.extras.RealDictRow)
        if isinstance(row, dict):
            game_date = row.get("date")
            if not game_date:
                raise ValueError("Game row missing required 'date' field")
            return cls(
                school=row.get("school") or "",
                date=game_date,
                season=row.get("season") or 0,
                location=row.get("location") or "neutral",
                location_id=row.get("location_id"),
                points_for=row.get("points_for"),
                points_against=row.get("points_against"),
                round=row.get("round"),
                kickoff_time=row.get("kickoff_time"),
                opponent=row.get("opponent"),
                result=row.get("result"),
                game_status=row.get("game_status"),
                source=row.get("source"),
                region_game=bool(row.get("region_game")),
                final=bool(row.get("final")),
                overtime=row.get("overtime") or 0,
            )

        # Otherwise assume a positional tuple/list
        row = tuple(row)
        if len(row) == 16:
            (
                school,
                date,
                season,
                location_id,
                points_for,
                points_against,
                round_,
                kickoff_time,
                opponent,
                result,
                game_status,
                source,
                location,
                region_game,
                final,
                overtime,
            ) = row
            return cls(
                school=school,
                date=date,
                season=season,
                location=location or "neutral",
                location_id=location_id,
                points_for=points_for,
                points_against=points_against,
                round=round_,
                kickoff_time=kickoff_time,
                opponent=opponent,
                result=result,
                game_status=game_status,
                source=source,
                region_game=bool(region_game),
                final=bool(final),
                overtime=overtime,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data class for a row in the location table ---
@dataclass
class Location:
    """DB-mapped dataclass for a row in the ``locations`` table."""

    id: int | None
    name: str
    city: str
    home_team: str
    latitude: float
    longitude: float

    def as_db_tuple(self):
        """Return a positional tuple suitable for INSERT/UPDATE queries."""
        return (
            self.name,
            self.city,
            self.home_team,
            self.latitude,
            self.longitude,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a Location object from a database row tuple or sequence.

        Args:
            row: An iterable of 5 column values
                (name, city, home_team, latitude, longitude).

        Returns:
            A Location instance with ``id=None`` (id is assigned by the DB).

        Raises:
            ValueError: If the row does not have exactly 5 columns.
        """
        row = tuple(row)
        if len(row) == 5:
            name, city, home_team, latitude, longitude = row
            return cls(
                id=None,
                name=name,
                city=city,
                home_team=home_team,
                latitude=latitude,
                longitude=longitude,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data class for a row in the bracket table ---
@dataclass
class Bracket:
    """DB-mapped dataclass for a row in the ``brackets`` table."""

    name: str
    season: int
    class_: int
    source: str | None

    def as_db_tuple(self):
        """Return a positional tuple suitable for INSERT/UPDATE queries."""
        return (
            self.name,
            self.season,
            self.class_,
            self.source,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a Bracket object from a database row tuple or sequence.

        Args:
            row: An iterable of 4 column values
                (name, season, class_, source).

        Returns:
            A Bracket instance populated from the row.

        Raises:
            ValueError: If the row does not have exactly 4 columns.
        """
        row = tuple(row)
        if len(row) == 4:
            name, season, class_, source = row
            return cls(
                name=name,
                season=season,
                class_=class_,
                source=source,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data Class for a row in the bracket_teams table ---
@dataclass
class BracketTeam:
    """DB-mapped dataclass for a row in the ``bracket_teams`` table."""

    bracket_id: int
    school: str
    season: int
    seed: int
    region: int

    def as_db_tuple(self):
        """Return a positional tuple suitable for INSERT/UPDATE queries."""
        return (
            self.bracket_id,
            self.school,
            self.season,
            self.seed,
            self.region,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a BracketTeam object from a database row tuple or sequence.

        Args:
            row: An iterable of 5 column values
                (bracket_id, school, season, seed, region).

        Returns:
            A BracketTeam instance populated from the row.

        Raises:
            ValueError: If the row does not have exactly 5 columns.
        """
        row = tuple(row)
        if len(row) == 5:
            bracket_id, school, season, seed, region = row
            return cls(
                bracket_id=bracket_id,
                school=school,
                season=season,
                seed=seed,
                region=region,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data class for a row in the playoff_format_slots table ---
@dataclass(frozen=True)
class FormatSlot:
    """DB-mapped dataclass for a row in the ``playoff_format_slots`` table.

    Attributes:
        slot:        1-based slot number within the class/season format.
        home_region: Region number of the designated home team.
        home_seed:   Seed of the home team (1 = best).
        away_region: Region number of the designated away team.
        away_seed:   Seed of the away team.
        north_south: ``'N'`` or ``'S'`` — which bracket half this slot belongs to.
    """

    slot: int
    home_region: int
    home_seed: int
    away_region: int
    away_seed: int
    north_south: str


# --- Data class for a row in the bracket_games table ---
@dataclass
class BracketGame:
    """DB-mapped dataclass for a row in the ``bracket_games`` table."""

    bracket_id: int
    round: str
    game_number: int
    home: str | None
    away: str | None
    home_region: int | None
    home_seed: int | None
    away_region: int | None
    away_seed: int | None
    next_game_id: int | None

    def as_db_tuple(self):
        """Return a positional tuple suitable for INSERT/UPDATE queries."""
        return (
            self.bracket_id,
            self.round,
            self.game_number,
            self.home,
            self.away,
            self.home_region,
            self.home_seed,
            self.away_region,
            self.away_seed,
            self.next_game_id,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """Create a BracketGame object from a database row tuple or sequence.

        Args:
            row: An iterable of column values.  Accepts rows with 3 columns
                (bracket_id, round, game_number) — all matchup fields default
                to None — or 10 columns (all fields).

        Returns:
            A BracketGame instance populated from the row.

        Raises:
            ValueError: If the row has an unexpected number of columns.
        """
        row = tuple(row)
        if len(row) == 3:
            bracket_id, round_, game_number = row
            return cls(
                bracket_id=bracket_id,
                round=round_,
                game_number=game_number,
                home=None,
                away=None,
                home_region=None,
                home_seed=None,
                away_region=None,
                away_seed=None,
                next_game_id=None,
            )
        elif len(row) == 10:
            (
                bracket_id,
                round_,
                game_number,
                home,
                away,
                home_region,
                home_seed,
                away_region,
                away_seed,
                next_game_id,
            ) = row
            return cls(
                bracket_id=bracket_id,
                round=round_,
                game_number=game_number,
                home=home,
                away=away,
                home_region=home_region,
                home_seed=home_seed,
                away_region=away_region,
                away_seed=away_seed,
                next_game_id=next_game_id,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")


# --- Data class for raw results of completed games used in tiebreakers ---
class RawCompletedGame(TypedDict):
    """Raw game result dict as returned directly from a DB query row.

    Used as the input format for ``get_completed_games()`` before normalization
    into CompletedGame instances.
    """

    school: str
    opponent: str
    date: str
    result: str
    points_for: int
    points_against: int


# --- Data class for completed games used in tiebreakers ---
@dataclass(frozen=True)
class CompletedGame:
    """Normalized completed-game record used by the tiebreaker engine.

    Fields are always stored from the perspective of the lexicographically
    first team (``a``).  These field names have caused bugs when confused, so
    the per-field meanings are documented carefully below.
    """

    a: str  # team (lexicographically first)
    b: str  # team (lexicographically second)
    res_a: int  # head-to-head result in completed set (+1 a beat b, -1 b beat a, 0 split)
    pd_a: int  # raw point differential for a vs b across completed meetings (will be capped when used)
    pa_a: int  # points allowed by team a in those meetings (i.e., points scored BY b against a)
    pa_b: int  # points allowed by team b in those meetings (i.e., points scored BY a against b)


# --- Data class for remaining games used in tiebreakers ---
@dataclass(frozen=True)
class RemainingGame:
    """An unplayed region game, stored with teams in lexicographic order."""

    a: str  # team (lexicographically first)
    b: str  # team (lexicographically second)


# --- Data class for bracket advancement odds ---
@dataclass(frozen=True)
class BracketOdds:
    """Per-team probability of advancing to each successive playoff round.

    Computed under equal win probability (50/50) from ``compute_bracket_odds()``.
    ``quarterfinals`` is 0.0 for classes with only 4 playoff rounds (5A–7A).
    """

    school: str
    second_round: float   # P(playing in round 2)
    quarterfinals: float    # P(playing in round 3); 0.0 for 4-round brackets
    semifinals: float     # P(playing in the N/S championship round)
    finals: float         # P(playing in the state championship)
    champion: float       # P(winning the state championship)


# --- Data class for standings odds results ---
@dataclass(frozen=True)
class StandingsOdds:
    """Per-team seeding probability results produced by ``determine_odds()``.

    Probability fields represent the fraction of enumerated outcomes in which
    the team achieves each seeding position.
    """

    school: str
    p1: float  # probability of finishing 1st in the region
    p2: float  # probability of finishing 2nd in the region
    p3: float  # probability of finishing 3rd in the region
    p4: float  # probability of finishing 4th in the region
    p_playoffs: float  # raw sum p1+p2+p3+p4 (may equal p_playoffs if no rounding)
    final_playoffs: float  # 1.0 if clinched, 0.0 if eliminated, else p_playoffs
    clinched: bool  # True when p_playoffs >= 0.999
    eliminated: bool  # True when p_playoffs <= 0.001
