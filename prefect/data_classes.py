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
    mascot: str = ""
    maxpreps_id: str = ""
    maxpreps_url: str = ""
    primary_color: str = ""
    secondary_color: str = ""


    def as_db_tuple(self):
        return (self.school, self.class_, self.region, self.city, self.zip, self.mascot, self.maxpreps_id, self.maxpreps_url, self.primary_color, self.secondary_color)
    

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a School object from a database row tuple or sequence.
        Accepts rows with 3 or 10 columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)

        if len(row) == 3:
            school, class_, region = row
            return cls(school=school, class_=class_, region=region)
        elif len(row) >= 10:
            school, class_, region, city, zip, mascot, maxpreps_id, maxpreps_url, primary_color, secondary_color = row[:10]
            return cls(
                school=school,
                class_=class_,
                region=region,
                city=city or "",
                zip=zip or "",
                mascot=mascot or "",
                maxpreps_id=maxpreps_id or "",
                maxpreps_url=maxpreps_url or "",
                primary_color=primary_color or "",
                secondary_color=secondary_color or "",
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")
