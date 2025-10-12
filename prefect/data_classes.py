from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
        return (self.school, self.season, self.class_, self.region, self.city, self.zip, self.latitude, self.longitude, self.mascot, self.maxpreps_id, self.maxpreps_url, self.maxpreps_logo, self.primary_color, self.secondary_color)
    

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
            return cls(school=school, season=season, class_=class_, region=region)
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
    date: str
    location: str = "neutral"
    opponent: str = ""
    points_for: int = 0
    points_against: int = 0
    result: str = ""
    region_game: bool = False
    season: int = 0
    round: str = ""
    kickoff_time: str = ""  # ISO 8601 format, e.g., "2023-09-01T19:00:00Z"

    def as_db_tuple(self):
        return (self.school, self.date, self.location, self.opponent, self.points_for, self.points_against, self.result, self.region_game, self.season, self.round)


    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a Game object from a database row tuple or sequence.
        Accepts rows with 3 or 13 columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)
        if len(row) == 11:
            school, date, location, opponent, points_for, points_against, result, region_game, season, round, kickoff_time = row[:11]
            return cls(
                school=school,
                date=date,
                location=location,
                opponent=opponent,
                points_for=points_for,
                points_against=points_against,
                result=result,
                region_game=region_game,
                season=season,
                round=round,
                kickoff_time=kickoff_time,
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")
