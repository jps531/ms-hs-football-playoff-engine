"""Who can meet whom in each bracket game, and who would host.

For every game in a class's playoff bracket this gives the possible occupants
of each side (with reach odds), and the specific matchups (with the chance of
each pairing and of each side hosting it).

How it's computed — exactly, from the same pieces as the existing reach and
hosting odds, with no simulation:

1. **Positions.** The bracket is built from (region, seed) positions. Every
   game's winner distribution over positions comes from the standard bracket
   recursion, using the same position-level win probability as the existing
   advancement odds (``_p_beat_by_seed``: better seed as home). Two sides of
   one game come from disjoint sub-brackets, so given the position-level
   model, P(x on side A and y on side B) = P(x on A) * P(y on B).
2. **Teams.** A position's occupant is a team with some seed probability.
   Teams from different regions are independent, but two teams from the same
   region are not: "Stringer is the 1 seed and Lumberton the 4 seed" needs the
   region's *joint* seed probabilities (``seed_pairs``), never a product of
   per-team odds. Using the joint also makes a team meeting itself impossible.
3. **Hosting.** Decided per position pairing by the MHSAA rules already in
   ``bracket_home_odds`` (format home in round 1; ``r2_home_team``,
   ``qf_home_team``, ``sf_home_team``; neutral championship). The
   quarterfinal rule depends on home games already played, so it's averaged
   over each side's possible second-round opponent.

Games already played are fixed: a side's winner is the team that won.

Pure functions over plain inputs; the API layer loads data and runs this once
per odds mode.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.helpers.bracket_home_odds import (
    _p_beat_by_seed,
    qf_home_team,
    r2_home_team,
    sf_home_team,
    was_home_r1,
)
from backend.helpers.data_classes import FormatSlot, MatchupProbFn

Position = tuple[int, int]  # (region, seed)
PairKey = tuple[str, int, str, int]  # (team_a, seed_a, team_b, seed_b), team_a < team_b

_EPS = 1e-9
_LOCKED = 1 - 1e-6


@dataclass
class SideOutlook:
    """Who can fill one side of a game: team -> P(team plays here on this side)."""

    feeders: list[Position]
    occupants: dict[str, float]


@dataclass
class GameOutlook:
    """One bracket game's sides and matchups for one odds mode.

    ``matchups`` maps (team_a, team_b) — team_a from side A — to
    (p_matchup, p_host_a); p_host_a is None at a neutral site. ``matchups`` is
    None when a needed same-region joint seeding wasn't available.
    """

    game_id: str
    round_name: str
    half: str | None
    side_a: SideOutlook
    side_b: SideOutlook
    matchups: dict[tuple[str, str], tuple[float, float | None]] | None
    decided: bool = False
    notes: list[str] = field(default_factory=list)


def _round_names(rounds_in_half: int) -> list[str]:
    """Round names within a half, first round first (the last is the semifinal)."""
    tail = ["Quarterfinals", "Semifinals"]
    if rounds_in_half == 4:
        return ["First Round", "Second Round", *tail]
    if rounds_in_half == 3:
        return ["First Round", *tail]
    # Not a format MHSAA uses today; name generically rather than guess.
    return [f"Round {i + 1}" for i in range(rounds_in_half)]


@dataclass
class _Node:
    """A bracket game during the recursion."""

    game_id: str
    round_index: int  # within the half; 0 = first round; -1 = championship
    half: str | None
    slot_indices: list[int]  # first-round slot indices (within the half) feeding it
    side_a: dict[Position, float] = field(default_factory=dict)
    side_b: dict[Position, float] = field(default_factory=dict)
    winner: dict[Position, float] = field(default_factory=dict)
    children: tuple[_Node, _Node] | None = None
    decided: bool = False


class _Bracket:
    """Position-level bracket recursion for one class and one odds mode."""

    def __init__(
        self,
        slots: list[FormatSlot],
        season: int,
        occupants: dict[Position, dict[str, float]],
        win_prob_fn: MatchupProbFn,
        results: Iterable[tuple[str, str]],
    ):
        self.season = season
        self.occupants = occupants
        self.win_prob_fn = win_prob_fn
        self.beat_pairs = {(w, loser) for w, loser in results}
        self.halves: dict[str, list[FormatSlot]] = {}
        for ns in ("N", "S"):
            half = sorted((s for s in slots if s.north_south == ns), key=lambda s: s.slot)
            if half:
                self.halves[ns] = half
        self.rounds: dict[str, list[list[_Node]]] = {}
        for ns, half in self.halves.items():
            self.rounds[ns] = self._build_half(ns, half)
        semis = [self.rounds[ns][-1][0] for ns in ("N", "S") if ns in self.rounds]
        self.championship: _Node | None = None
        if len(semis) == 2:
            node = _Node("final", -1, None, [], children=(semis[0], semis[1]))
            self._play(node)
            self.championship = node

    # -- structure -------------------------------------------------------

    def _build_half(self, ns: str, half: list[FormatSlot]) -> list[list[_Node]]:
        """Build and evaluate one half's rounds, first round first."""
        first: list[_Node] = []
        for i, slot in enumerate(half):
            node = _Node(f"{ns}-0-{i}", 0, ns, [i])
            node.side_a = {(slot.home_region, slot.home_seed): 1.0}
            node.side_b = {(slot.away_region, slot.away_seed): 1.0}
            self._decide(node)
            first.append(node)
        rounds = [first]
        while len(rounds[-1]) > 1:
            prev = rounds[-1]
            k = len(rounds)
            nxt = []
            for i in range(0, len(prev), 2):
                a, b = prev[i], prev[i + 1]
                node = _Node(f"{ns}-{k}-{i // 2}", k, ns, a.slot_indices + b.slot_indices, children=(a, b))
                self._play(node)
                nxt.append(node)
            rounds.append(nxt)
        return rounds

    # -- odds ------------------------------------------------------------

    def _certain_team(self, pos: Position) -> str | None:
        """The team certain to hold *pos*, if any."""
        for team, p in self.occupants.get(pos, {}).items():
            if p >= _LOCKED:
                return team
        return None

    def _filled(self, pos: Position) -> float:
        """P(some team holds *pos*); below 1 only when a region can't fill its seeds."""
        return min(1.0, sum(self.occupants.get(pos, {}).values()))

    def _beat(self, x: Position, y: Position) -> float:
        """P(position x beats position y), better seed as home (as the reach odds do)."""
        return _p_beat_by_seed(x[0], x[1], y[0], y[1], self.win_prob_fn)

    def _played_winner(self, side_a: dict[Position, float], side_b: dict[Position, float]) -> Position | None:
        """The winning position when both sides are settled and the game has a result."""
        if len(side_a) != 1 or len(side_b) != 1:
            return None
        (x, px), (y, py) = next(iter(side_a.items())), next(iter(side_b.items()))
        if px < _LOCKED or py < _LOCKED:
            return None
        tx, ty = self._certain_team(x), self._certain_team(y)
        if tx is None or ty is None:
            return None
        if (tx, ty) in self.beat_pairs:
            return x
        if (ty, tx) in self.beat_pairs:
            return y
        return None

    def _decide(self, node: _Node) -> None:
        """Fill ``node.winner`` from its two sides."""
        played = self._played_winner(node.side_a, node.side_b)
        if played is not None:
            node.winner = {played: 1.0}
            node.decided = True
            return
        winner: dict[Position, float] = {}
        for x, px in node.side_a.items():
            for y, py in node.side_b.items():
                # A position no team can fill (a region short of four
                # playoff teams) forfeits; otherwise the game is played.
                if self._filled(y) <= _EPS:
                    p_x = 1.0
                elif self._filled(x) <= _EPS:
                    p_x = 0.0
                else:
                    p_x = self._beat(x, y)
                winner[x] = winner.get(x, 0.0) + px * py * p_x
                winner[y] = winner.get(y, 0.0) + px * py * (1.0 - p_x)
        node.winner = {pos: p for pos, p in winner.items() if p > _EPS}

    def _play(self, node: _Node) -> None:
        """Set a later-round node's sides from its children's winners, then decide it."""
        assert node.children is not None
        node.side_a = dict(node.children[0].winner)
        node.side_b = dict(node.children[1].winner)
        self._decide(node)

    # -- hosting ---------------------------------------------------------

    def _slot_of(self, half: str, pos: Position) -> tuple[int, FormatSlot] | None:
        """Index and first-round slot of *pos* in *half*."""
        for i, s in enumerate(self.halves[half]):
            if (s.home_region, s.home_seed) == pos or (s.away_region, s.away_seed) == pos:
                return i, s
        return None

    def _second_round_opponents(self, node: _Node, pos: Position) -> dict[Position, float]:
        """Who *pos* beat in the second round, given it won that game (1A-4A quarterfinals).

        ``node`` is the quarterfinal side's child: the second-round game *pos*
        won. Its opponent there is weighted by P(on the other side) * P(pos
        beats them), or is simply the team it beat once the game is played.
        """
        if pos in node.side_a:
            other = node.side_b
        elif pos in node.side_b:
            other = node.side_a
        else:
            return {}
        if node.decided:
            return dict(other)
        weights = {z: pz * self._beat(pos, z) for z, pz in other.items()}
        total = sum(weights.values())
        return {z: w / total for z, w in weights.items()} if total > _EPS else dict(other)

    def host_prob(self, node: _Node, x: Position, y: Position) -> float | None:
        """P(x hosts | x on side A meets y on side B in *node*); None at a neutral site."""
        if node.round_index == -1:
            return None
        half = node.half
        assert half is not None
        rounds_in_half = len(self.rounds[half])
        name = _round_names(rounds_in_half)[node.round_index]
        if node.round_index == 0:
            slot = self.halves[half][node.slot_indices[0]]
            return 1.0 if was_home_r1(x[0], x[1], slot) else 0.0
        if name == "Second Round":
            return 1.0 if r2_home_team(x[0], x[1], y[0], y[1], self.season) == x else 0.0
        if name == "Semifinals":
            return 1.0 if sf_home_team(x[0], x[1], y[0], y[1], self.season) == x else 0.0
        if name == "Quarterfinals":
            sx, sy = self._slot_of(half, x), self._slot_of(half, y)
            if sx is None or sy is None:
                return None
            r1x = was_home_r1(x[0], x[1], sx[1])
            r1y = was_home_r1(y[0], y[1], sy[1])
            if rounds_in_half == 3:  # 5A-7A: no second round
                return 1.0 if qf_home_team(x[0], x[1], r1x, False, y[0], y[1], r1y, False, self.season) == x else 0.0
            assert node.children is not None
            opp_x = self._second_round_opponents(node.children[0], x)
            opp_y = self._second_round_opponents(node.children[1], y)
            p = 0.0
            for z, pz in opp_x.items():
                r2x = r2_home_team(x[0], x[1], z[0], z[1], self.season) == x
                for w, pw in opp_y.items():
                    r2y = r2_home_team(y[0], y[1], w[0], w[1], self.season) == y
                    if qf_home_team(x[0], x[1], r1x, r2x, y[0], y[1], r1y, r2y, self.season) == x:
                        p += pz * pw
            return p
        return None

    def nodes(self) -> list[_Node]:
        """Every game, half by half and round by round, then the championship."""
        out = [node for ns in ("N", "S") if ns in self.rounds for rnd in self.rounds[ns] for node in rnd]
        if self.championship is not None:
            out.append(self.championship)
        return out

    def feeders(self, node: _Node, side: int) -> list[Position]:
        """First-round positions that can arrive on one side of *node*."""
        if node.round_index == 0:
            slot = self.halves[node.half][node.slot_indices[0]] if node.half else None
            if slot is None:
                return []
            return [(slot.home_region, slot.home_seed)] if side == 0 else [(slot.away_region, slot.away_seed)]
        assert node.children is not None
        child = node.children[side]
        return sorted({p for i in child.slot_indices for p in self._slot_positions(child.half, i)})

    def _slot_positions(self, half: str | None, index: int) -> list[Position]:
        """Both positions in a first-round slot."""
        assert half is not None
        s = self.halves[half][index]
        return [(s.home_region, s.home_seed), (s.away_region, s.away_seed)]


def _joint(
    x: Position,
    t: str,
    y: Position,
    u: str,
    occupants: dict[Position, dict[str, float]],
    seed_pairs: dict[int, dict[PairKey, float] | None],
) -> float | None:
    """P(t holds x and u holds y). None when a same-region joint isn't available."""
    if x[0] != y[0]:
        return occupants[x].get(t, 0.0) * occupants[y].get(u, 0.0)
    if t == u:
        return 0.0
    pairs = seed_pairs.get(x[0])
    if pairs is None:
        return None
    key = (t, x[1], u, y[1]) if t < u else (u, y[1], t, x[1])
    return pairs.get(key, 0.0)


def bracket_outlook(
    slots: list[FormatSlot],
    season: int,
    seed_odds: dict[int, dict[str, dict[int, float]]],
    seed_pairs: dict[int, dict[PairKey, float] | None],
    win_prob_fn: MatchupProbFn,
    results: Iterable[tuple[str, str]] = (),
) -> list[GameOutlook]:
    """Every bracket game's possible occupants and matchups for one odds mode.

    Args:
        slots: First-round format slots for the class and season.
        season: Season (hosting tiebreaks depend on odd/even years).
        seed_odds: region -> team -> {seed: P(team takes that seed)}.
        seed_pairs: region -> joint seed-pair probabilities, or None when not
            available (matchups needing them are then left out).
        win_prob_fn: Position-level win probability (home position first).
        results: Confirmed playoff results as (winner, loser) team names.

    Returns:
        One ``GameOutlook`` per game, half by half, round by round, then the
        championship.
    """
    occupants: dict[Position, dict[str, float]] = {}
    for region, teams in seed_odds.items():
        for team, by_seed in teams.items():
            for seed, p in by_seed.items():
                if p > _EPS:
                    occupants.setdefault((region, seed), {})[team] = p
    for s in slots:
        occupants.setdefault((s.home_region, s.home_seed), {})
        occupants.setdefault((s.away_region, s.away_seed), {})

    bracket = _Bracket(slots, season, occupants, win_prob_fn, results)
    out: list[GameOutlook] = []
    for node in bracket.nodes():
        out.append(_game_outlook(bracket, node, occupants, seed_pairs))
    return out


def _team_side(side: dict[Position, float], occupants: dict[Position, dict[str, float]]) -> dict[str, float]:
    """Team-level occupants of one side, normalized to sum to 1."""
    teams: dict[str, float] = {}
    for pos, p in side.items():
        for team, pt in occupants.get(pos, {}).items():
            teams[team] = teams.get(team, 0.0) + p * pt
    total = sum(teams.values())
    return {t: p / total for t, p in teams.items() if p > _EPS} if total > _EPS else {}


def _game_outlook(
    bracket: _Bracket,
    node: _Node,
    occupants: dict[Position, dict[str, float]],
    seed_pairs: dict[int, dict[PairKey, float] | None],
) -> GameOutlook:
    """Turn one position-level game into team-level sides and matchups."""
    if node.round_index == -1:
        round_name = "Championship Game"
    else:
        round_name = _round_names(len(bracket.rounds[node.half]))[node.round_index]
    side_a = SideOutlook(bracket.feeders(node, 0), _team_side(node.side_a, occupants))
    side_b = SideOutlook(bracket.feeders(node, 1), _team_side(node.side_b, occupants))

    weights: dict[tuple[str, str], float] = {}
    hosts: dict[tuple[str, str], float] = {}
    neutral = False
    missing = False
    for x, px in node.side_a.items():
        for y, py in node.side_b.items():
            pos_p = px * py
            if pos_p <= _EPS:
                continue
            h = bracket.host_prob(node, x, y)
            neutral = h is None
            for t in occupants.get(x, {}):
                for u in occupants.get(y, {}):
                    j = _joint(x, t, y, u, occupants, seed_pairs)
                    if j is None:
                        missing = True
                        continue
                    w = pos_p * j
                    if w <= _EPS:
                        continue
                    weights[(t, u)] = weights.get((t, u), 0.0) + w
                    if h is not None:
                        hosts[(t, u)] = hosts.get((t, u), 0.0) + w * h

    matchups: dict[tuple[str, str], tuple[float, float | None]] | None
    if missing:
        matchups = None
    else:
        total = sum(weights.values())
        matchups = (
            {pair: (w / total, None if neutral else hosts.get(pair, 0.0) / w) for pair, w in weights.items()}
            if total > _EPS
            else {}
        )
    notes = ["Matchup odds need this season's region seed pairs; rerun the region update."] if missing else []
    return GameOutlook(
        game_id=node.game_id,
        round_name=round_name,
        half=node.half,
        side_a=side_a,
        side_b=side_b,
        matchups=matchups,
        decided=node.decided,
        notes=notes,
    )


def locked_pairs(teams: dict[str, dict[int, float]]) -> dict[PairKey, float] | None:
    """A region's seed pairs when every playoff seed is locked; None otherwise.

    With all four seeds certain, the joint is certain too, so stored pairs
    aren't needed (e.g. during the playoffs).
    """
    holder: dict[int, str] = {}
    for team, by_seed in teams.items():
        for seed, p in by_seed.items():
            if p >= _LOCKED:
                holder[seed] = team
    seeds = sorted(holder)
    if len(seeds) != len({s for by in teams.values() for s, p in by.items() if p > _EPS}):
        return None
    pairs: dict[PairKey, float] = {}
    for i, sa in enumerate(seeds):
        for sb in seeds[i + 1 :]:
            a, b = holder[sa], holder[sb]
            key = (a, sa, b, sb) if a < b else (b, sb, a, sa)
            pairs[key] = 1.0
    return pairs


def _r(p: float | None) -> float | None:
    """Round a probability for the payload (0.01% resolution; keeps the response small)."""
    return None if p is None else round(p, 4)


def merge_modes(
    tossup: list[GameOutlook],
    projected: list[GameOutlook] | None,
    floor: float = 0.005,
) -> list[dict]:
    """Combine Toss-up and Projected outlooks into one payload per game.

    Occupants carry both modes' reach odds; matchups below *floor* in both
    modes are folded into ``other`` so the client never decides what to hide.
    Projected fields are None when Projected odds aren't available.

    Returns:
        One dict per game: ``id``, ``round``, ``half``, ``decided``,
        ``side_a``/``side_b`` (``feeders`` and ``occupants``), ``matchups``
        (or None when a needed joint seeding was missing), ``other``, ``notes``.
    """
    by_id = {g.game_id: g for g in projected} if projected is not None else {}
    games: list[dict] = []
    for g in tossup:
        pg = by_id.get(g.game_id)

        def side(t_side: SideOutlook, p_side: SideOutlook | None) -> dict:
            """Occupants of one side in both modes, likeliest first."""
            teams = set(t_side.occupants) | set(p_side.occupants if p_side else {})
            occ = [
                {
                    "team": team,
                    "p_reach": _r(t_side.occupants.get(team, 0.0)),
                    "p_reach_weighted": _r(p_side.occupants.get(team, 0.0)) if p_side else None,
                    "is_locked": t_side.occupants.get(team, 0.0) >= _LOCKED,
                }
                for team in teams
            ]
            occ.sort(key=lambda o: (-(o["p_reach_weighted"] or 0.0), -o["p_reach"], o["team"]))
            return {"feeders": [{"region": r, "seed": s} for r, s in t_side.feeders], "occupants": occ}

        p_side_a = pg.side_a if pg else None
        p_side_b = pg.side_b if pg else None
        matchups = None
        other = None
        notes = list(g.notes)
        if g.matchups is not None and (pg is None or pg.matchups is not None):
            p_matchups = pg.matchups if pg else {}
            pairs = set(g.matchups) | set(p_matchups)
            rows = []
            folded = 0  # possible pairings too unlikely to list
            for pair in pairs:
                p_t, h_t = g.matchups.get(pair, (0.0, None))
                p_w, h_w = p_matchups.get(pair, (0.0, None)) if pg else (None, None)
                if max(p_t, p_w or 0.0) < floor:
                    folded += max(p_t, p_w or 0.0) > 0
                    continue
                rows.append(
                    {
                        "team_a": pair[0],
                        "team_b": pair[1],
                        "p_matchup": _r(p_t),
                        "p_matchup_weighted": _r(p_w),
                        "p_host_a": _r(h_t),
                        "p_host_a_weighted": _r(h_w),
                    }
                )
            rows.sort(key=lambda m: (-(m["p_matchup_weighted"] or 0.0), -m["p_matchup"], m["team_a"], m["team_b"]))
            matchups = rows
            kept_t = sum(m["p_matchup"] for m in rows)
            kept_w = sum(m["p_matchup_weighted"] or 0.0 for m in rows) if pg else None
            other = {
                "p_matchup": _r(max(0.0, 1.0 - kept_t)) if g.matchups else 0.0,
                "p_matchup_weighted": (_r(max(0.0, 1.0 - kept_w)) if p_matchups else 0.0) if pg else None,
                "count": folded,
            }
        elif pg is not None:
            notes = notes or list(pg.notes)
        games.append(
            {
                "id": g.game_id,
                "round": g.round_name,
                "half": g.half,
                "decided": g.decided,
                "side_a": side(g.side_a, p_side_a),
                "side_b": side(g.side_b, p_side_b),
                "matchups": matchups,
                "other": other,
                "notes": notes,
            }
        )
    return games


def pairs_for_regions(
    seed_odds: dict[int, dict[str, dict[int, float]]],
    standings_dates: dict[int, object],
    stored: dict[int, tuple[object, list[list]]],
) -> dict[int, dict[PairKey, float] | None]:
    """Each region's seed pairs for one odds mode, or None when they can't be known.

    Stored pairs are used only when they come from the same snapshot as the
    region's standings, so the two always agree. Otherwise, if every seed is
    locked the pairs are certain and are derived; failing both, None.

    Args:
        seed_odds: region -> team -> {seed: p} for this mode.
        standings_dates: region -> as_of_date of its standings snapshot.
        stored: region -> (as_of_date, [[team_a, seed_a, team_b, seed_b, p], ...]).
    """
    out: dict[int, dict[PairKey, float] | None] = {}
    for region, teams in seed_odds.items():
        row = stored.get(region)
        if row is not None and row[0] == standings_dates.get(region):
            out[region] = {(a, int(sa), b, int(sb)): float(p) for a, sa, b, sb, p in row[1]}
        else:
            out[region] = locked_pairs(teams)
    return out


def regions_needing_fallback(
    seed_odds: dict[int, dict[str, dict[int, float]]],
    standings_dates: dict[int, object],
    stored: dict[int, tuple[object, list[list]]],
) -> list[int]:
    """Regions whose newest standings snapshot has no seed pairs from the same date.

    Every region update writes both together, but snapshots written before
    the pairs existed (or by an older pipeline) have standings only. Those
    regions can use their newest snapshot that has both instead; a region
    whose seeds are all locked needs no stored pairs and isn't listed.
    """
    out = []
    for region, teams in seed_odds.items():
        row = stored.get(region)
        if row is not None and row[0] == standings_dates.get(region):
            continue
        if locked_pairs(teams) is not None:
            continue
        out.append(region)
    return sorted(out)
