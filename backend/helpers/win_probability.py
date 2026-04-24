"""Elo-based win probability model for MS high school football.

Provides a factory (``make_win_prob_fn``) that pre-computes team ratings from
completed game data and returns a ``WinProbFn`` closure suitable for injection
into ``determine_scenarios``.  All computation is pure Python; no DB or Prefect
imports here.

Public API
----------
EloConfig                — tunable model parameters
compute_elo_ratings()    — build Elo ratings + date snapshots from game history
compute_rpi()            — compute RPI for each team (display-only)
make_win_prob_fn()       — factory: returns a WinProbFn closure
make_win_prob_fn_from_ratings() — alternate factory using pre-computed ratings
make_matchup_prob_fn()        — bridge: seed-based MatchupProbFn from Elo ratings
compute_in_game_win_prob()    — regulation in-game win probability (Gaussian model)
compute_ot_win_prob()         — OT mid-possession win probability (discrete model)
win_prob_with_factors()       — returns a full WinProbFactors breakdown for display
"""

import bisect
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from backend.helpers.data_classes import (
    Game,
    InGameConfig,
    MatchupProbFn,
    School,
    StandingsOdds,
    WinProbFactors,
    WinProbFn,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CLASS_RATINGS: tuple[float, ...] = (
    1000.0,  # 1A
    1050.0,  # 2A
    1100.0,  # 3A
    1150.0,  # 4A
    1200.0,  # 5A
    1250.0,  # 6A
    1300.0,  # 7A
)


@dataclass
class EloConfig:
    """Tunable parameters for the Elo rating model.

    Defaults are calibrated for Mississippi high school football
    (10–12 games per team, 1A–7A classifications).
    """

    k_regular: float = 40.0
    """K-factor for non-region games."""

    k_region: float = 50.0
    """K-factor for region games (higher stakes — counts toward playoff seeding)."""

    hfa_points: float = 65.0
    """Home-field advantage in Elo points.  Applied in both training (expected
    calculation) and forward-looking predictions (when location_a is known)."""

    scale: float = 400.0
    """Logistic scale factor.  A difference of ``scale`` points gives 10:1 odds."""

    class_ratings: tuple[float, ...] = field(
        default_factory=lambda: _DEFAULT_CLASS_RATINGS
    )
    """Starting Elo by classification (index 0 = 1A, index 6 = 7A).
    Teams with no classification data fall back to ``class_ratings[0]``."""

    carryover_factor: float = 0.50
    """Fraction of the prior season's final Elo carried into the new season.
    ``0.0`` resets every team to the class prior each season; ``1.0`` uses the
    prior rating unchanged.  Defaults to 0.50, reflecting that roughly half a
    HS program's strength signal is roster-specific (turns over annually) and
    half is program-level (coaching, scheme, tradition)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _class_prior(school: str, schools_by_name: dict[str, School], config: EloConfig) -> float:
    """Return the starting Elo rating for a school based on its classification."""
    s = schools_by_name.get(school)
    if s is None:
        return config.class_ratings[0]
    return config.class_ratings[s.class_ - 1]


def _apply_carryover(
    class_prior: float,
    school: str,
    prior_ratings: dict[str, float] | None,
    carryover_factor: float,
) -> float:
    """Blend a classification prior with a prior-season rating.

    Returns ``class_prior`` unchanged when ``prior_ratings`` is empty/None or
    the school has no prior-season entry.
    """
    if not prior_ratings or school not in prior_ratings:
        return class_prior
    return (1.0 - carryover_factor) * class_prior + carryover_factor * prior_ratings[school]


def _elo_expected(r_a: float, r_b: float, scale: float) -> float:
    """Return P(team with rating r_a beats team with rating r_b) at neutral site."""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / scale))


def _mov_multiplier(margin: int, elo_diff_winner: float, mov_exponent: float) -> float:
    """FiveThirtyEight-style margin-of-victory multiplier.

    Discounts large winning margins when the favourite wins big; gives extra
    credit to underdog upsets.  Returns 1.0 for ties (margin == 0).
    """
    if margin == 0:
        return 1.0
    autocorrect = (elo_diff_winner / mov_exponent) + mov_exponent
    return math.log(margin + 1) * (mov_exponent / autocorrect)


# ---------------------------------------------------------------------------
# Elo computation
# ---------------------------------------------------------------------------

def compute_elo_ratings(
    games: list[Game],
    schools: list[School],
    config: EloConfig,
    prior_ratings: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, int], list[tuple[date, dict[str, float], dict[str, int]]]]:
    """Compute Elo ratings for all teams from completed game history.

    Games are processed in chronological order.  The games table has one row
    per team per game; this function deduplicates by (min_name, max_name, date)
    so each contest is applied exactly once.

    Parameters
    ----------
    games : list[Game]
        All completed games for the season.
    schools : list[School]
        All known schools for the season (used for classification priors).
    config : EloConfig
        Model parameters including ``carryover_factor``.
    prior_ratings : dict[str, float] | None
        Final Elo ratings from the previous season (e.g. fetched from
        ``team_ratings`` for ``season - 1``).  When provided, each team's
        starting rating is blended:
        ``(1 - carryover_factor) * class_prior + carryover_factor * prior_elo``.
        Teams absent from ``prior_ratings`` start at the class prior unchanged.

    Returns
    -------
    ratings : dict[str, float]
        Final Elo rating for every team seen in the data.
    games_count : dict[str, int]
        Number of completed games processed per team.
    snapshots : list[tuple[date, dict[str, float], dict[str, int]]]
        Ratings snapshot after each unique game-date, in chronological order.
        Each entry is (game_date, ratings_at_that_date, games_count_at_that_date).
        Used by ``make_win_prob_fn`` for date-conditioned queries and by the
        backfill pipeline to persist per-game-date Elo rows.
    """
    schools_by_name: dict[str, School] = {s.school: s for s in schools}

    # Seed every known school — blend with prior-season rating when available
    ratings: dict[str, float] = {
        s.school: _apply_carryover(
            config.class_ratings[s.class_ - 1], s.school, prior_ratings, config.carryover_factor
        )
        for s in schools
    }
    games_count: dict[str, int] = defaultdict(int)

    # Filter to final, scored games with a known result
    valid: list[Game] = [
        g for g in games
        if g.final
        and g.result in ("W", "L", "T")
        and g.points_for is not None
        and g.points_against is not None
        and g.opponent is not None
    ]
    valid.sort(key=lambda g: g.date)

    processed: set[tuple[str, str, str]] = set()
    snapshots: list[tuple[date, dict[str, float], dict[str, int]]] = []
    current_date: date | None = None

    for g in valid:
        school = g.school
        opponent: str = g.opponent  # type: ignore[assignment]  # filtered above

        # Deduplicate: each game appears once for school and once for opponent
        pair_key = (min(school, opponent), max(school, opponent), str(g.date))
        if pair_key in processed:
            continue
        processed.add(pair_key)

        # Record snapshot when the date advances (after all games on previous date)
        if current_date is not None and g.date != current_date:
            snapshots.append((current_date, dict(ratings), dict(games_count)))
        current_date = g.date

        # Ensure both teams have a rating (handles out-of-state / untracked opponents)
        if school not in ratings:
            ratings[school] = _apply_carryover(
                _class_prior(school, schools_by_name, config), school, prior_ratings, config.carryover_factor
            )
        if opponent not in ratings:
            ratings[opponent] = _apply_carryover(
                _class_prior(opponent, schools_by_name, config), opponent, prior_ratings, config.carryover_factor
            )

        r_school = ratings[school]
        r_opp = ratings[opponent]
        games_count[school] += 1
        games_count[opponent] += 1

        # Expected probability from school's perspective with HFA
        if g.location == "home":
            r_school_adj = r_school + config.hfa_points
        elif g.location == "away":
            r_school_adj = r_school - config.hfa_points
        else:
            r_school_adj = r_school

        e_school = _elo_expected(r_school_adj, r_opp, config.scale)

        # Actual outcome from school's perspective
        if g.result == "W":
            s_school = 1.0
        elif g.result == "L":
            s_school = 0.0
        else:
            s_school = 0.5

        # MOV multiplier — use adjusted ratings to determine "winner's Elo advantage"
        margin = abs(g.points_for - g.points_against)  # type: ignore[operator]
        if s_school >= 0.5:
            elo_diff_winner = r_school_adj - r_opp
        else:
            elo_diff_winner = r_opp - r_school_adj
        mov_mult = _mov_multiplier(margin, abs(elo_diff_winner), config.k_region)

        k = config.k_region if g.region_game else config.k_regular
        delta = k * mov_mult * (s_school - e_school)

        ratings[school] += delta
        ratings[opponent] -= delta  # zero-sum

    # Record final snapshot for the last game-date
    if current_date is not None:
        snapshots.append((current_date, dict(ratings), dict(games_count)))

    return ratings, dict(games_count), snapshots


# ---------------------------------------------------------------------------
# RPI computation (display-only)
# ---------------------------------------------------------------------------

def compute_rpi(games: list[Game]) -> dict[str, float | None]:
    """Compute RPI for each team.

    Formula: 0.25 * WP + 0.50 * OWP + 0.25 * OOWP

    Returns None for teams with fewer than 3 completed games.
    RPI is stored in WinProbFactors for display context only and does NOT
    affect win probability calculations.
    """
    # Build per-team opponent result list: (opponent_name, outcome: 1.0/0.5/0.0)
    results: dict[str, list[tuple[str, float]]] = defaultdict(list)

    valid: list[Game] = [
        g for g in games
        if g.final
        and g.result in ("W", "L", "T")
        and g.opponent is not None
    ]

    # Deduplicate — process each game from one perspective, infer the other
    processed: set[tuple[str, str, str]] = set()
    for g in valid:
        school = g.school
        opponent: str = g.opponent  # type: ignore[assignment]  # filtered above
        pair_key = (min(school, opponent), max(school, opponent), str(g.date))
        if pair_key in processed:
            continue
        processed.add(pair_key)

        if g.result == "W":
            school_outcome, opp_outcome = 1.0, 0.0
        elif g.result == "L":
            school_outcome, opp_outcome = 0.0, 1.0
        else:
            school_outcome, opp_outcome = 0.5, 0.5

        results[school].append((opponent, school_outcome))
        results[opponent].append((school, opp_outcome))

    # WP: overall win percentage
    wp: dict[str, float] = {}
    for team, res in results.items():
        total = len(res)
        wp[team] = sum(o for _, o in res) / total if total > 0 else 0.5

    # OWP: each opponent's WP excluding games against this team
    def _owp_for(team: str, opp: str) -> float:
        """Return opp's win percentage excluding games played against team."""
        filtered = [(o, out) for (o, out) in results[opp] if o != team]
        if not filtered:
            return wp.get(opp, 0.5)
        return sum(out for _, out in filtered) / len(filtered)

    owp: dict[str, float] = {}
    for team, res in results.items():
        opps = [o for o, _ in res]
        owp[team] = sum(_owp_for(team, opp) for opp in opps) / len(opps) if opps else 0.5

    # OOWP: average of each opponent's OWP
    oowp: dict[str, float] = {}
    for team, res in results.items():
        opps = [o for o, _ in res]
        opp_owps = [owp[opp] for opp in opps if opp in owp]
        oowp[team] = sum(opp_owps) / len(opp_owps) if opp_owps else 0.5

    rpi: dict[str, float | None] = {}
    for team in results:
        if len(results[team]) < 3:
            rpi[team] = None
        else:
            rpi[team] = 0.25 * wp[team] + 0.50 * owp[team] + 0.25 * oowp[team]

    return rpi


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def make_win_prob_fn(
    games: list[Game],
    schools: list[School],
    config: EloConfig | None = None,
) -> WinProbFn:
    """Build and return a WinProbFn closure from completed game data.

    Pre-computes Elo ratings and date-ordered snapshots once.  The returned
    closure is O(1) per call (dict lookup + arithmetic) and safe to call
    millions of times inside the scenario enumeration inner loop.

    Parameters
    ----------
    games:
        All completed (final=True) games for the season.  Non-final rows are
        filtered out internally, so it's safe to pass the full games list.
    schools:
        All school records for the season, used to seed classification priors.
    config:
        Elo parameters.  Defaults to ``EloConfig()`` if omitted.

    Returns
    -------
    WinProbFn
        ``fn(team_a, team_b, date_str, location_a) -> float``

        - ``team_a`` is lexicographically first (same convention as RemainingGame).
        - ``date_str``: ISO-format date string or None.  None / future date uses
          final ratings; a past date uses the most recent snapshot ≤ that date.
        - ``location_a``: ``'home'`` / ``'away'`` / ``'neutral'`` / None from
          team_a's perspective.  None is treated as neutral (no HFA adjustment).
        - Returns ``0.5`` for any team not found in the ratings dict.
    """
    cfg = config or EloConfig()
    final_ratings, _games_count, snapshots = compute_elo_ratings(games, schools, cfg)

    # Parallel list of snapshot dates for bisect
    snapshot_dates: list[date] = [snap[0] for snap in snapshots]

    def _ratings_at(target: date) -> dict[str, float]:
        """Return the ratings snapshot for the most recent game date on or before target."""
        idx = bisect.bisect_right(snapshot_dates, target) - 1
        if idx < 0:
            # Before any games were played — return classification priors
            return {
                s.school: cfg.class_ratings[s.class_ - 1] for s in schools
            }
        return snapshots[idx][1]

    def win_prob_fn(
        team_a: str,
        team_b: str,
        date_str: str | None,
        location_a: str | None,
    ) -> float:
        """Return P(team_a beats team_b) with optional date conditioning and HFA."""
        # Resolve which ratings snapshot to use
        if date_str is not None:
            try:
                target = date.fromisoformat(date_str)
                if snapshot_dates and target <= snapshot_dates[-1]:
                    ratings = _ratings_at(target)
                else:
                    ratings = final_ratings
            except ValueError:
                ratings = final_ratings
        else:
            ratings = final_ratings

        r_a = ratings.get(team_a)
        r_b = ratings.get(team_b)
        if r_a is None or r_b is None:
            return 0.5  # graceful fallback for unknown teams

        # Apply home-field advantage from team_a's perspective
        if location_a == "home":
            r_a_adj = r_a + cfg.hfa_points
        elif location_a == "away":
            r_a_adj = r_a - cfg.hfa_points
        else:
            r_a_adj = r_a  # neutral or unknown

        prob = _elo_expected(r_a_adj, r_b, cfg.scale)
        return max(0.0, min(1.0, prob))

    return win_prob_fn


# ---------------------------------------------------------------------------
# Alternate factory (pre-computed ratings)
# ---------------------------------------------------------------------------

def make_win_prob_fn_from_ratings(
    final_ratings: dict[str, float],
    snapshots: list[tuple[date, dict[str, float], dict[str, int]]],
    config: EloConfig | None = None,
) -> WinProbFn:
    """Build a WinProbFn closure from already-computed ratings and snapshots.

    Use this when ratings have been computed once at the flow level and need to
    be reused across many region tasks without re-running ``compute_elo_ratings``.
    The ``final_ratings`` and ``snapshots`` dicts are captured by the closure, so
    no re-serialization of the full game list is needed.
    """
    cfg = config or EloConfig()
    snapshot_dates: list[date] = [snap[0] for snap in snapshots]

    def _ratings_at(target: date) -> dict[str, float]:
        """Return the ratings snapshot for the most recent game date on or before target."""
        idx = bisect.bisect_right(snapshot_dates, target) - 1
        if idx < 0:
            return final_ratings  # before any games — just use priors
        return snapshots[idx][1]

    def win_prob_fn(
        team_a: str,
        team_b: str,
        date_str: str | None,
        location_a: str | None,
    ) -> float:
        """Return P(team_a beats team_b) with optional date conditioning and HFA."""
        if date_str is not None:
            try:
                target = date.fromisoformat(date_str)
                if snapshot_dates and target <= snapshot_dates[-1]:
                    ratings = _ratings_at(target)
                else:
                    ratings = final_ratings
            except ValueError:
                ratings = final_ratings
        else:
            ratings = final_ratings

        r_a = ratings.get(team_a)
        r_b = ratings.get(team_b)
        if r_a is None or r_b is None:
            return 0.5

        if location_a == "home":
            r_a_adj = r_a + cfg.hfa_points
        elif location_a == "away":
            r_a_adj = r_a - cfg.hfa_points
        else:
            r_a_adj = r_a

        prob = _elo_expected(r_a_adj, r_b, cfg.scale)
        return max(0.0, min(1.0, prob))

    return win_prob_fn


# ---------------------------------------------------------------------------
# Matchup probability bridge (team-name Elo → seed-based bracket)
# ---------------------------------------------------------------------------

def make_matchup_prob_fn(
    elo_ratings: dict[str, float],
    seeding_odds_by_region: dict[int, dict[str, StandingsOdds]],
    config: EloConfig | None = None,
) -> MatchupProbFn:
    """Build a ``MatchupProbFn`` using probability-weighted expected Elo per seed.

    For each ``(region, seed)`` position the expected Elo is:

        expected_elo[region, seed] = Σ_t  P(t achieves seed in region)  ×  elo[t]

    When seeding is fully determined (one team has ``p=1.0``) this equals that
    team's exact Elo.  When uncertain mid-season it is a proper probability-
    weighted expectation.  Seed rank is not used as a proxy — only Elo matters,
    so a high-Elo lower seed is correctly favoured over a low-Elo higher seed.

    Home-field advantage (``config.hfa_points``) is applied to the home team.
    Per MHSAA rules the lower seed number (better seed) hosts, so the home
    team is always the argument passed as ``home_region, home_seed``.

    Unknown ``(region, seed)`` pairs (no seeding odds available) return 0.5.

    Args:
        elo_ratings:            Final Elo ratings keyed by school name.
        seeding_odds_by_region: ``region → {school: StandingsOdds}`` for a
                                single class.  All regions in the class should
                                be included so cross-region playoff matchups are
                                handled correctly.
        config:                 Elo configuration used for ``hfa_points`` and
                                ``scale``.  Defaults to ``EloConfig()``.

    Returns:
        A ``MatchupProbFn``: ``fn(home_region, home_seed, away_region,
        away_seed) → float``.
    """
    cfg = config or EloConfig()
    seed_elo: dict[tuple[int, int], float] = {}
    for region, school_odds in seeding_odds_by_region.items():
        for school, so in school_odds.items():
            elo = elo_ratings.get(school, cfg.class_ratings[0])
            for seed, p in ((1, so.p1), (2, so.p2), (3, so.p3), (4, so.p4)):
                key = (region, seed)
                seed_elo[key] = seed_elo.get(key, 0.0) + p * elo

    def matchup_prob_fn(
        home_region: int, home_seed: int, away_region: int, away_seed: int
    ) -> float:
        """Return P(home wins) using probability-weighted expected Elo."""
        elo_home = seed_elo.get((home_region, home_seed))
        elo_away = seed_elo.get((away_region, away_seed))
        if elo_home is None or elo_away is None:
            return 0.5
        adjusted = elo_home + cfg.hfa_points
        return 1.0 / (1.0 + 10.0 ** ((elo_away - adjusted) / cfg.scale))

    return matchup_prob_fn


# ---------------------------------------------------------------------------
# In-game win probability
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (no scipy dependency)."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _norm_ppf(p: float) -> float:
    """Approximate inverse normal CDF (percent-point function) via bisection.

    Accurate to ~1e-6 for p in (0.001, 0.999). Used only once per call to
    ``compute_in_game_win_prob`` so bisection cost is negligible.
    """
    p = max(1e-9, min(1.0 - 1e-9, p))
    lo, hi = -10.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def compute_in_game_win_prob(
    pregame_prob: float,
    current_margin: int,
    seconds_remaining: int,
    config: InGameConfig | None = None,
) -> float:
    """Return P(team_a wins) given current score and time remaining in regulation.

    Uses a Gaussian remaining-score random walk calibrated for MSHAA 48-minute
    rules.  Do not call this for overtime possessions; use ``compute_ot_win_prob``
    instead.

    Args:
        pregame_prob: Elo win probability for team_a before the game started.
        current_margin: team_a score minus team_b score (positive = team_a leading).
        seconds_remaining: Total regulation seconds left (use ``game_seconds_remaining()``).
        config: Model parameters; defaults to ``InGameConfig()``.
    """
    cfg = config or InGameConfig()
    t = max(0, seconds_remaining)
    T = cfg.total_seconds

    if t == 0:
        if current_margin > 0:
            return 1.0
        if current_margin < 0:
            return 0.0
        return 0.5  # tied at end of regulation → overtime

    frac = t / T
    sigma_remaining = cfg.sigma * math.sqrt(frac)

    # Apply mercy-rule variance collapse when margin meets/exceeds threshold
    if abs(current_margin) >= cfg.mercy_threshold:
        sigma_remaining *= cfg.mercy_sigma_factor

    # Expected final margin: current score + remaining drift scaled by time left
    pregame_drift = _norm_ppf(pregame_prob) * cfg.sigma  # expected total margin at kickoff
    mu_final = current_margin + pregame_drift * frac

    result = _norm_cdf(mu_final / sigma_remaining)
    return max(0.0, min(1.0, result))


def _ot_score_distribution(
    p_b_wins_ot: float,
    cfg: InGameConfig,
) -> dict[int, float]:
    """Return the probability distribution over team B's OT possession score.

    Scores are one of ``{0, 3, 6, 7, 8}`` corresponding to no score, field goal,
    TD + missed PAT, TD + 1-pt PAT, and TD + 2-pt PAT respectively.

    The distribution is adjusted by ``p_b_wins_ot`` (B's stateless OT win
    probability, i.e. ``1 - pregame_prob_a``): stronger teams score TDs more
    often, weaker teams less often.
    """
    adj = cfg.ot_elo_factor * (p_b_wins_ot - 0.5)
    p_td = max(0.0, min(1.0, cfg.ot_p_td_base + adj))
    p_fg = max(0.0, min(1.0 - p_td, cfg.ot_p_fg_base + adj * 0.5))
    p_0 = max(0.0, 1.0 - p_td - p_fg)
    return {
        0: p_0,
        3: p_fg,
        6: p_td * cfg.ot_p_missed_pat,
        7: p_td * cfg.ot_p_1pt_pat,
        8: p_td * cfg.ot_p_2pt_pat,
    }


def compute_ot_win_prob(
    pregame_prob_a: float,
    ot_scored_margin: int,
    config: InGameConfig | None = None,
) -> float:
    """Return P(team_a wins the game) after team_a scored in their OT possession.

    Team_b has not yet possessed.  ``ot_scored_margin`` must be one of
    ``{0, 3, 6, 7, 8}``.  The "another OT" recursion resolves via
    ``pregame_prob_a`` (each new OT period resets to the same team-strength
    contest).

    MSHAA overtime is untimed alternating possessions (NFHS Kansas City
    Tiebreaker format).  Scoring rates are adjusted by the Elo gap.
    """
    cfg = config or InGameConfig()
    dist_b = _ot_score_distribution(1.0 - pregame_prob_a, cfg)

    p_a_wins_direct = sum(p for score, p in dist_b.items() if score < ot_scored_margin)
    p_another_ot = sum(p for score, p in dist_b.items() if score == ot_scored_margin)

    # If tied after both possessions → another OT → use stateless pregame probability
    return max(0.0, min(1.0, p_a_wins_direct + p_another_ot * pregame_prob_a))


# ---------------------------------------------------------------------------
# Breakdown for frontend display
# ---------------------------------------------------------------------------

def win_prob_with_factors(
    team_a: str,
    team_b: str,
    elo_ratings: dict[str, float],
    games_count: dict[str, int],
    rpi: dict[str, float | None],
    schools_by_name: dict[str, School],
    location_a: str | None = None,
    config: EloConfig | None = None,
) -> WinProbFactors:
    """Return a full WinProbFactors breakdown for a matchup.

    ``team_a`` must be lexicographically first (same convention as WinProbFn).
    Intended for frontend display; not in the hot path.
    """
    cfg = config or EloConfig()

    fallback_elo = cfg.class_ratings[0]
    r_a = elo_ratings.get(team_a, fallback_elo)
    r_b = elo_ratings.get(team_b, fallback_elo)

    school_a = schools_by_name.get(team_a)
    school_b = schools_by_name.get(team_b)
    class_a = school_a.class_ if school_a else 1
    class_b = school_b.class_ if school_b else 1

    raw_prob = _elo_expected(r_a, r_b, cfg.scale)

    if location_a == "home":
        r_a_adj = r_a + cfg.hfa_points
    elif location_a == "away":
        r_a_adj = r_a - cfg.hfa_points
    else:
        r_a_adj = r_a

    loc_prob = _elo_expected(r_a_adj, r_b, cfg.scale)
    loc_prob = max(0.0, min(1.0, loc_prob))

    return WinProbFactors(
        team_a=team_a,
        team_b=team_b,
        elo_a=r_a,
        elo_b=r_b,
        class_a=class_a,
        class_b=class_b,
        games_played_a=games_count.get(team_a, 0),
        games_played_b=games_count.get(team_b, 0),
        rpi_a=rpi.get(team_a),
        rpi_b=rpi.get(team_b),
        location_a=location_a,
        raw_elo_prob=max(0.0, min(1.0, raw_prob)),
        location_adjusted_prob=loc_prob,
        final_prob=loc_prob,
    )
