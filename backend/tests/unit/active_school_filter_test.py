"""Public reads of region_standings must skip schools inactive for that season.

The pipeline never computes inactive schools, but a school marked inactive
after snapshots were written keeps its old rows; without this filter its
last stale row would keep surfacing in standings, rankings, and hosting.
"""

import inspect

from backend.api.routers import hosting, meta, standings
from backend.helpers import api_helpers
from backend.helpers.api_helpers import ACTIVE_SCHOOL_FILTER, ACTIVE_SCHOOL_JOIN_RS


def test_filter_checks_the_rows_own_season():
    """The filter matches school_seasons on both school and season, and requires is_active."""
    for fragment in (ACTIVE_SCHOOL_FILTER, ACTIVE_SCHOOL_JOIN_RS):
        assert "is_active" in fragment
        assert ".season" in fragment and ".school" in fragment


def test_standings_selects_are_filtered():
    """The summary and class standings queries both carry the filter."""
    assert ACTIVE_SCHOOL_FILTER in standings._SUMMARY_SELECT
    assert ACTIVE_SCHOOL_FILTER in standings._CLASS_SELECT


def test_rankings_join_is_filtered():
    """Rankings read region_standings through a join that requires an active school."""
    assert ACTIVE_SCHOOL_JOIN_RS in api_helpers._RANK_FROM_JOIN


def test_every_region_standings_reader_in_routers_and_helpers_is_filtered():
    """Every DISTINCT ON (school) read of region_standings in these modules applies the filter."""
    for module in (api_helpers, standings, hosting):
        src = inspect.getsource(module)
        reads = src.count("FROM region_standings\n")
        filtered = src.count("ACTIVE_SCHOOL_FILTER\n") + src.count("+ ACTIVE_SCHOOL_JOIN_RS")
        assert reads <= filtered, f"{module.__name__}: {reads} region_standings reads, {filtered} filtered"


def test_team_list_skips_inactive_schools():
    """GET /teams only lists schools active in the season."""
    assert '"ss.is_active"' in inspect.getsource(meta.list_teams)
