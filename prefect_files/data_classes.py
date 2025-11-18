from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypedDict
from datetime import date

# -------------------------
# Data Classes
# -------------------------

# --- Data class for a row in the school table ---
@dataclass
class School:
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


    def as_db_tuple(self):
        return (
            self.school, 
            self.season,
            self.class_,
            self.region,
            self.city,
            self.zip,
            self.latitude,
            self.longitude,
            self.mascot,
            self.maxpreps_id,
            self.maxpreps_url,
            self.maxpreps_logo,
            self.primary_color,
            self.secondary_color
        )
    

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a School object from a database row tuple or sequence.
        Accepts rows with 4 or 14 columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)

        if len(row) == 4:
            school, season, class_, region = row
            return cls(
                school=school,
                season=season,
                class_=class_,
                region=region
            )
        elif len(row) >= 14:
            school, season, class_, region, city, zip, latitude, longitude, mascot, maxpreps_id, maxpreps_url, maxpreps_logo, primary_color, secondary_color = row[:14]
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
        """
        Create a Game object from a DB row (tuple, list, or dict).
        Accepts rows with 16 expected columns or dicts with named fields.
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
            (school, date, season, location_id, points_for, points_against,
            round, kickoff_time, opponent, result, game_status, source,
            location, region_game, final, overtime) = row
            return cls(
                school=school,
                date=date,
                season=season,
                location=location or "neutral",
                location_id=location_id,
                points_for=points_for,
                points_against=points_against,
                round=round,
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
    id: int | None
    name: str
    city: str
    home_team: str
    latitude: float
    longitude: float

    def as_db_tuple(self):
        return (
            self.name,
            self.city,
            self.home_team,
            self.latitude,
            self.longitude,
        )

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a Location object from a database row tuple or sequence.
        Accepts rows with 5 columns.
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
    name: str
    season: int
    class_: int
    source: str | None

    def as_db_tuple(self):
        return (
            self.name,
            self.season,
            self.class_,
            self.source,
        )
    
    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a Bracket object from a database row tuple or sequence.
        Accepts rows with 4 columns.
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
    bracket_id: int
    school: str
    season: int
    seed: int
    region: int

    def as_db_tuple(self):
        return (
            self.bracket_id,
            self.school,
            self.season,
            self.seed,
            self.region,
        )
    
    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a BracketTeam object from a database row tuple or sequence.
        Accepts rows with 5 columns.
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


# --- Data class for a row in the bracket_games table ---
@dataclass
class BracketGame:
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
        """
        Create a BracketGame object from a database row tuple or sequence.
        Accepts rows with 3 or 10 columns.
        """
        row = tuple(row)
        if len(row) == 3:
            bracket_id, round, game_number = row
            return cls(
                bracket_id=bracket_id,
                round=round,
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
            (bracket_id, round, game_number, home, away,
            home_region, home_seed, away_region, away_seed,
            next_game_id) = row
            return cls(
                bracket_id=bracket_id,
                round=round,
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
    school: str
    opponent: str
    date: str
    result: str
    points_for: int
    points_against: int


# --- Data class for completed games used in tiebreakers ---
@dataclass(frozen=True)
class CompletedGame:
    a: str  # team (lexicographically first)
    b: str  # team (lexicographically second)
    res_a: int  # head-to-head result in completed set (+1 a beat b, -1 b beat a, 0 split)
    pd_a: int   # raw point differential for a vs b across completed meetings (will be capped when used)
    pa_a: int   # points allowed by team a in those meetings
    pa_b: int   # points allowed by team b in those meetings