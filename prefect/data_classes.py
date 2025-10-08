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
        return (self.school, self.class_, self.region, self.city, self.zip, self.latitude, self.longitude, self.mascot, self.maxpreps_id, self.maxpreps_url, self.maxpreps_logo, self.primary_color, self.secondary_color)
    

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a School object from a database row tuple or sequence.
        Accepts rows with 3 or 13 columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)

        if len(row) == 3:
            school, class_, region = row
            return cls(school=school, class_=class_, region=region)
        elif len(row) >= 12:
            school, class_, region, city, zip, latitude, longitude, mascot, maxpreps_id, maxpreps_url, maxpreps_logo, primary_color, secondary_color = row[:13]
            return cls(
                school=school,
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
