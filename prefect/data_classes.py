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
    homepage: str = ""
    primary_color: str = ""
    secondary_color: str = ""


    def as_db_tuple(self):
        return (self.school, self.class_, self.region, self.city, self.homepage, self.primary_color, self.secondary_color)
    

    @classmethod
    def from_db_tuple(cls, row: Iterable):
        """
        Create a School object from a database row tuple or sequence.
        Accepts rows with 3 or 7 columns.
        """
        # Convert row-like objects (sqlite Row, psycopg2 row, etc.) to tuple
        row = tuple(row)

        if len(row) == 3:
            school, class_, region = row
            return cls(school=school, class_=class_, region=region)
        elif len(row) >= 7:
            school, class_, region, city, homepage, primary_color, secondary_color = row[:7]
            return cls(
                school=school,
                class_=class_,
                region=region,
                city=city or "",
                homepage=homepage or "",
                primary_color=primary_color or "",
                secondary_color=secondary_color or "",
            )
        else:
            raise ValueError(f"Unexpected number of columns in DB row: {len(row)}")
