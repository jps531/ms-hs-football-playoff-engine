"""The bracket as one image to share: what each spot shows, the two versions, and the image sizes."""

from PIL import Image

from backend.helpers.bracket_image import SQUARE, WIDE, is_final, picks_for, render_bracket_image, slot
from backend.helpers.static_pages import layout_results
from backend.tests.unit.static_pages_test import BRACKET, _side

SEEDS = {"Raleigh": (1, 1)}


def test_a_spot_shows_its_result_its_locked_team_or_one_team_that_could_be_there():
    """Projected: a locked team with its seed, an open spot the page's pick with its chance. Blank: only what's settled."""
    picks = picks_for(BRACKET, {})
    locked = slot(BRACKET[0], "a", {}, SEEDS, picks, blank=False)
    assert (locked["name"], locked["sub"], locked["kind"], locked["pct"]) == (
        "Raleigh",
        "Region 1 #1 Seed",
        "locked",
        None,
    )
    pick = slot(BRACKET[0], "b", {}, SEEDS, picks, blank=False)
    assert (pick["name"], pick["sub"], pick["kind"], pick["pct"]) == ("Mize", "Region 2 #4 Seed", "pick", 0.6)
    later = slot(BRACKET[4], "a", {}, SEEDS, picks, blank=False)
    assert later["kind"] == "pick" and later["sub"] == "+3 more"
    # Blank: an open first-round spot shows the seed that goes there; a later one, nothing. No chances anywhere.
    first = slot(BRACKET[0], "b", {}, SEEDS, picks, blank=True)
    assert (first["name"], first["kind"], first["pct"]) == ("Region 2 #4 Seed", "open", None)
    assert slot(BRACKET[4], "a", {}, SEEDS, picks, blank=True)["name"] == ""
    # A bye, and a played game: the winner and the loser with their scores.
    bye = {**BRACKET[2], "side_b": {**_side([(4, 4)], []), "bye": True}}
    assert slot(bye, "b", {}, SEEDS, picks, blank=False)["name"] == "BYE"
    results = {"N-0-0": {"winner": "Raleigh", "loser": "Mize", "winner_score": 35, "loser_score": 7}}
    won = slot(BRACKET[0], "a", results, SEEDS, picks, blank=True)
    lost = slot(BRACKET[0], "b", results, SEEDS, picks, blank=True)
    assert (won["name"], won["score"], won["kind"]) == ("Raleigh", 35, "won")
    assert (lost["name"], lost["score"], lost["kind"]) == ("Mize", 7, "lost")


def test_a_bracket_is_final_once_every_game_is_played():
    games = [{"id": "N-0-0"}, {"id": "final"}]
    assert not is_final(games, {"N-0-0": {}}) and is_final(games, {"N-0-0": {}, "final": {}}) and not is_final([], {})


def test_a_half_draws_square_and_the_whole_bracket_wide():
    """Both versions of each view render at their sizes; the two versions differ (one has chances)."""
    for view, size in (("N", SQUARE), ("all", WIDE)):
        odds = render_bracket_image(
            3, 2026, BRACKET, {}, SEEDS, view, False, "2026 season · Through Week 10 · Oct 30 · Projected"
        )
        blank = render_bracket_image(3, 2026, BRACKET, {}, SEEDS, view, True, "2026 season · Through Week 10 · Oct 30")
        assert odds.size == blank.size == size
        assert odds.tobytes() != blank.tobytes()
    # A class with no games for the half still draws (just the header and footer).
    assert render_bracket_image(3, 2026, BRACKET, {}, SEEDS, "S", True, "x").size == SQUARE


def test_layout_results_feed_the_image():
    """Results come from the page's own layout reader, so a played game shows its score."""
    layout = {
        "halves": {
            "N": [
                [
                    {
                        "result": {
                            "winner": {"school": "Raleigh"},
                            "loser": {"school": "Mize"},
                            "winner_score": 35,
                            "loser_score": 7,
                        }
                    }
                ]
            ]
        }
    }
    img = render_bracket_image(3, 2026, BRACKET, layout_results(layout), SEEDS, "N", True, "x")
    assert isinstance(img, Image.Image)
