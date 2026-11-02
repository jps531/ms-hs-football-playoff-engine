"""The bracket as one image to share: what each spot shows, the two versions, and the image sizes."""

from PIL import Image

from backend.helpers.bracket_image import (
    SQUARE,
    TROPHY_H,
    WIDE,
    helmet,
    is_final,
    picks_for,
    render_bracket_image,
    slot,
)
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


def test_both_themes_draw_with_helmets_in_each_teams_colors():
    """Light and dark differ; a team with colors gets its helmet (a pale one outlined so it shows on white)."""
    teams = {"Raleigh": {"color_variants": {"primary": {"raw": "#800000"}, "secondary": [{"raw": "#FFFFFF"}]}}}
    dark = render_bracket_image(3, 2026, BRACKET, {}, SEEDS, "N", True, "x", teams, "dark")
    light = render_bracket_image(3, 2026, BRACKET, {}, SEEDS, "N", True, "x", teams, "light")
    assert dark.getpixel((5, 5)) == (0x16, 0x16, 0x16) and light.getpixel((5, 5)) == (0xFF, 0xFF, 0xFF)
    icon = helmet("#800000", "#FFFFFF", 64, "#A4A3A4")
    assert icon.size == (64, 64) and icon.mode == "RGBA"
    assert icon.getpixel((18, 34))[:3] == (0x80, 0x00, 0x00)  # the shell, in the team's color
    pale = helmet("#FFFFFF", "#CC0000", 64, "#A4A3A4")
    assert any(px[:3] == (0xA4, 0xA3, 0xA4) for px in pale.getdata() if px[3] == 255)  # outlined in grey on light


def test_only_the_projected_image_has_a_subtitle():
    """It says what the odds are and how the open spots are filled; a blank or finished one needs none."""
    from backend.helpers.bracket_image import _subtitle

    assert (
        _subtitle(False, False)
        == "Projected odds · Each open spot shows one team that could be there, and their chance"
    )
    assert _subtitle(False, True) == "" and _subtitle(True, True) == ""


def test_a_finished_bracket_draws_the_trophy_over_the_championship_game():
    """The whole bracket, once the final is played, gets the trophy (gold); without its result it doesn't."""
    from backend.helpers.bracket_image import trophy

    cup = trophy(TROPHY_H)
    assert cup.height == TROPHY_H and cup.mode == "RGBA"
    assert cup.getpixel((cup.width * 5 // 8, cup.height // 4))[:3] == (0xD9, 0xA5, 0x20)  # the ball
    results = {g["id"]: {"winner": "Raleigh", "loser": "Mize", "winner_score": 1, "loser_score": 0} for g in BRACKET}
    done = render_bracket_image(3, 2025, BRACKET, results, SEEDS, "all", True, "x")
    open_ = render_bracket_image(
        3, 2025, BRACKET, {k: v for k, v in results.items() if k != "final"}, SEEDS, "all", True, "x"
    )
    gold = lambda img: sum(1 for px in img.getdata() if px == (0xD9, 0xA5, 0x20))  # noqa: E731
    assert gold(done) > 1000 and gold(open_) == 0


def test_the_whole_bracket_names_the_venue_and_in_projected_odds_the_projected_champion():
    """Under the championship game: the venue when it's on record; the projected champion only in the
    Projected image, never the blank one."""
    games = [dict(g) for g in BRACKET]
    final = next(g for g in games if g["id"] == "final")
    champ = {"p_champion": 0.25, "p_champion_weighted": 0.31}
    final["side_a"] = {
        **final["side_a"],
        "occupants": [{"team": "Raleigh", "p_reach": 0.5, "p_reach_weighted": 0.6, "is_locked": False, **champ}],
    }
    venue = {"name": "Davis Wade Stadium", "city": "Starkville, MS"}

    def draw(blank, venue, games=games):
        """The whole bracket's image as bytes."""
        return render_bracket_image(3, 2026, games, {}, SEEDS, "all", blank, "x", None, "dark", venue).tobytes()

    assert draw(False, venue) != draw(False, None)  # the venue line
    assert draw(False, None) != draw(False, None, BRACKET)  # the projected champion
    assert draw(True, None) == draw(True, None, BRACKET)  # not in the blank image
    assert draw(True, venue) != draw(True, None)


def _final_with(occupants: list[tuple[str, float]]) -> dict:
    """The championship game with these (team, Projected title chance) occupants on its first side."""
    final = dict(next(g for g in BRACKET if g["id"] == "final"))
    final["side_a"] = {
        **final["side_a"],
        "occupants": [
            {"team": t, "p_reach": 0.5, "p_reach_weighted": 0.5, "is_locked": False, "p_champion_weighted": p}
            for t, p in occupants
        ],
    }
    return final


def test_the_preview_names_the_two_likeliest_champions_and_never_picks_between_equals():
    from backend.helpers.bracket_image import title_contenders

    two = title_contenders(_final_with([("Winona", 0.26), ("Seminary", 0.42), ("Magee", 0.03)]), None)
    assert two == [{"team": "Seminary", "p": 0.42}, {"team": "Winona", "p": 0.26}]
    # A team level with the second is listed too; one level with the first doesn't push the second out.
    tied = title_contenders(_final_with([("A", 0.4), ("B", 0.2), ("C", 0.2), ("D", 0.1)]), None)
    assert [c["team"] for c in tied] == ["A", "B", "C"]
    assert [c["team"] for c in title_contenders(_final_with([("A", 0.3), ("B", 0.3), ("C", 0.1)]), None)] == ["A", "B"]
    # Once it's played, or without Projected odds, nobody.
    assert title_contenders(_final_with([("A", 0.6)]), {"winner": "A"}) == []
    assert title_contenders(_final_with([("A", None)]), None) == []
    assert title_contenders(BRACKET[0], None) == []


def test_the_link_preview_is_the_whole_bracket_at_preview_size():
    """1200x630 (share_cards' card size), in Projected odds, blank, and once the final is played (the champion)."""
    from backend.helpers.bracket_image import render_bracket_card_image
    from backend.helpers.share_cards import HEIGHT, WIDTH

    games = [_final_with([("Raleigh", 0.31)]) if g["id"] == "final" else g for g in BRACKET]
    odds = render_bracket_card_image(3, 2026, games, {}, SEEDS, False, "2026 season · Projected")
    blank = render_bracket_card_image(3, 2026, games, {}, SEEDS, True, "2026 season")
    results = {g["id"]: {"winner": "Raleigh", "loser": "Mize", "winner_score": 1, "loser_score": 0} for g in BRACKET}
    done = render_bracket_card_image(3, 2025, games, results, SEEDS, False, "2025 season · Final")
    assert odds.size == blank.size == done.size == (WIDTH, HEIGHT)
    assert odds.tobytes() != blank.tobytes()
    gold = lambda img: sum(1 for px in img.getdata() if px == (0xD9, 0xA5, 0x20))  # noqa: E731
    assert gold(done) > 0 and gold(odds) == 0  # the trophy, once there's a champion
