"""The morning update's order, and the Friday-night AHSFHS score probe's sampling and counts."""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import backend.prefect.ahsfhs_score_probe_pipeline as probe
import backend.prefect.daily_update_pipeline as daily
from backend.helpers.data_classes import Game, School

CENTRAL = ZoneInfo("America/Chicago")
FRIDAY = date(2026, 10, 23)


def test_region_scenarios_run_after_the_scores_are_pulled(monkeypatch):
    """The morning update recalculates only once the pull has finished, and not at all if it fails."""
    calls = []
    monkeypatch.setattr(daily, "ahsfhs_schedule_data_flow", lambda season: calls.append(("pull", season)))
    monkeypatch.setattr(daily, "region_scenarios_data_flow", lambda season: calls.append(("recalc", season)))
    daily.daily_update_flow.fn(2026)
    assert calls == [("pull", 2026), ("recalc", 2026)]

    def failed_pull(season):
        """A pull that fails partway."""
        raise RuntimeError("AHSFHS down")

    calls.clear()
    monkeypatch.setattr(daily, "ahsfhs_schedule_data_flow", failed_pull)
    with pytest.raises(RuntimeError):
        daily.daily_update_flow.fn(2026)
    assert calls == []


def test_only_the_daily_update_is_scheduled_each_morning():
    """Its two halves keep deployments for manual runs but no schedule of their own."""
    flows = (Path(__file__).resolve().parents[2] / "prefect" / "flows.py").read_text()
    assert flows.count('CronSchedule(cron=f"0 {DAILY_UPDATE_HOUR} * * *"') == 1
    assert "DAILY_UPDATE_HOUR = 9\n" in flows
    assert 'await ahsfhs_schedule_data_flow.to_deployment("ahsfhs-schedule-data-pipeline")' in flows
    assert 'await region_scenarios_data_flow.to_deployment("region-scenarios-data-pipeline")' in flows


def test_the_probe_runs_6_to_10_on_friday_and_saturday_mornings():
    """Every 15 minutes from 6:00 to 10:00 AM Central on Fridays and Saturdays, and no other time."""
    flows = (Path(__file__).resolve().parents[2] / "prefect" / "flows.py").read_text()
    probe_block = flows[flows.index('"ahsfhs-score-probe"') : flows.index("await backfill_historical_snapshots")]
    crons = re.findall(r'CronSchedule\(cron="([^"]+)"', probe_block)
    assert crons == ["*/15 6-9 * * 5,6", "0 10 * * 5,6"]


@pytest.mark.parametrize(
    ("local", "night"),
    [
        (datetime(2026, 10, 23, 21, 0), FRIDAY),  # Friday 9 PM: tonight
        (datetime(2026, 10, 23, 23, 45), FRIDAY),
        (datetime(2026, 10, 24, 0, 15), FRIDAY),  # after midnight: still Friday's games
        (datetime(2026, 10, 24, 12, 0), FRIDAY),  # Saturday noon
        (datetime(2026, 10, 24, 6, 0), FRIDAY),  # Saturday 6 AM, the first morning probe
        (datetime(2026, 10, 24, 10, 0), FRIDAY),  # Saturday 10 AM, the last
        (datetime(2026, 10, 30, 6, 0), date(2026, 10, 29)),  # Friday morning: Thursday's games
    ],
)
def test_probe_looks_for_the_night_just_played(local, night):
    """Runs after midnight look for the previous night's scores."""
    assert probe.probe_game_date(local.replace(tzinfo=CENTRAL)) == night


def test_probe_date_is_central_whatever_the_server_zone():
    """5 AM UTC Saturday is midnight Friday night in Mississippi."""
    assert probe.probe_game_date(datetime(2026, 10, 24, 5, 0, tzinfo=ZoneInfo("UTC"))) == FRIDAY


def _school(name, clazz, region):
    """A school in a class and region."""
    return School(school=name, season=2026, class_=clazz, region=region)


def test_probe_samples_one_school_per_region_that_plays():
    """The first school alphabetically among each region's teams playing tonight; idle regions are skipped."""
    schools = [
        _school("Raleigh", 3, 7),
        _school("Magee", 3, 7),
        _school("Seminary", 3, 7),
        _school("Tupelo", 6, 1),
        _school("Idle", 2, 4),
    ]
    picked = probe.pick_probe_schools(schools, playing={"Raleigh", "Seminary", "Tupelo"})
    assert [s.school for s in picked] == ["Raleigh", "Tupelo"]


def _game(school, day, final):
    """A game on *day*, final or not yet."""
    return Game(
        school=school,
        date=day,
        season=2026,
        location_id=None,
        points_for=21 if final else None,
        points_against=14 if final else None,
        round=None,
        kickoff_time=None,
        opponent="Other",
        result="W" if final else None,
        game_status=None,
        source=None,
        final=final,
    )


def test_probe_counts_tonight_final_scores_by_class():
    """Only games on the night count; an unreadable page is counted apart from the games."""
    checked = [
        (_school("Raleigh", 3, 7), [_game("Raleigh", date(2026, 10, 16), True), _game("Raleigh", FRIDAY, True)]),
        (_school("Kosciusko", 3, 4), [_game("Kosciusko", FRIDAY, False)]),
        (_school("Tupelo", 6, 1), None),
    ]
    assert probe.summarize_probe(checked, FRIDAY) == [
        {"class": "3A", "teams_checked": 2, "games": 2, "final": 1, "unreadable": 0},
        {"class": "6A", "teams_checked": 1, "games": 0, "final": 0, "unreadable": 1},
    ]


def test_probe_records_its_counts(monkeypatch):
    """The flow saves one table row per class under a fixed artifact key."""
    monkeypatch.setattr(probe, "get_run_logger", lambda: logging.getLogger("test"))
    monkeypatch.setattr(probe, "get_existing_schools", lambda season: [_school("Raleigh", 3, 7)])
    monkeypatch.setattr(probe, "schools_playing_on", lambda season, day: {"Raleigh"})
    monkeypatch.setattr(
        probe, "check_pages", lambda schools, season, day: [(schools[0], [_game("Raleigh", day, True)])]
    )
    saved = {}
    monkeypatch.setattr(probe, "create_table_artifact", lambda **kw: saved.update(kw))
    rows = probe.ahsfhs_score_probe_flow.fn(FRIDAY)
    assert rows == [{"class": "3A", "teams_checked": 1, "games": 1, "final": 1, "unreadable": 0}]
    assert saved["key"] == "ahsfhs-score-probe"
    assert saved["table"][0]["game_date"] == "2026-10-23" and saved["table"][0]["final"] == 1
    assert "1 of 1 sampled games on 2026-10-23 final" in saved["description"]
