"""Write ``backend/data/geo/mississippi_counties.geojson`` from the Census Bureau's county boundaries.

    curl -O https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip
    unzip cb_2023_us_county_500k.zip -d cb
    uv run --with pyshp python -m backend.tools.build_counties cb/cb_2023_us_county_500k.shp

The cartographic boundary file (1:500,000) is the Census Bureau's own generalization of its TIGER
lines, public domain. Only Mississippi's 82 counties are kept, as published (NAD83 longitude and
latitude, to six decimal places, about 0.1 m), with no further simplification. ``region_map`` projects
them. Run this again only for a newer vintage, and change ``SOURCE`` with it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SOURCE = "U.S. Census Bureau, 2023 cartographic boundary file, counties, 1:500,000 (cb_2023_us_county_500k)"
OUT = Path(__file__).resolve().parents[1] / "data" / "geo" / "mississippi_counties.geojson"
MISSISSIPPI = "28"


def _round(coords):
    """Coordinates to six decimal places, at any nesting depth."""
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 6), round(coords[1], 6)]
    return [_round(c) for c in coords]


def main(shp: str) -> int:  # pragma: no cover - reads the Census file
    """Write the GeoJSON for Mississippi's counties from the shapefile at *shp*."""
    import shapefile  # pyshp, only for this tool

    reader = shapefile.Reader(shp)
    fields = [f[0] for f in reader.fields[1:]]
    features = []
    for sr in reader.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        if rec["STATEFP"] != MISSISSIPPI:
            continue
        geom = sr.shape.__geo_interface__
        features.append(
            {
                "type": "Feature",
                "properties": {"name": rec["NAME"], "geoid": rec["GEOID"]},
                "geometry": {"type": geom["type"], "coordinates": _round(geom["coordinates"])},
            }
        )
    features.sort(key=lambda f: f["properties"]["geoid"])
    doc = {"type": "FeatureCollection", "source": SOURCE, "crs": "EPSG:4269", "features": features}
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(features)} counties -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1]))
