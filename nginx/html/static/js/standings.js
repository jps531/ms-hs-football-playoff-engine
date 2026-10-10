import { isCertain } from "./format.js";

// Standings-table data shaping: tie-aware positions, a team's round-by-round
// playoff path, and matching region games to scores and dates. No DOM, so it
// runs under `node --test`.

/** Region winning percentage, ties counting half; null with no games played. */
function winPct(r) {
  const games = r.region_wins + r.region_losses + r.region_ties;
  return games ? (r.region_wins + 0.5 * r.region_ties) / games : null;
}

/**
 * Standings positions with ties shared, competition style: two teams level
 * at the top are both 1, and the next team is 3. Teams arrive in display
 * order; "level" means the same region winning percentage, so 2-0 and 1-0
 * share a position (the 2-0 team listed first). A team without games counts
 * as .500, as it does for the order.
 */
export function standingPositions(entries) {
  const positions = [];
  entries.forEach((e, i) => {
    const prev = entries[i - 1];
    const tied = prev && (winPct(prev.record) ?? 0.5) === (winPct(e.record) ?? 0.5);
    positions.push(tied ? positions[i - 1] : i + 1);
  });
  return positions;
}

/**
 * Teams in display order:
 *   1. region winning percentage (a team without games counts as .500);
 *   2. games over .500, so 2-0 sits above 1-0 and 0-2 below 0-1;
 *   3. odds of finishing 1st, then of making the playoffs, then of
 *      finishing 2nd, 3rd, and 4th — projected odds, or toss-up odds when
 *      a snapshot has none;
 *   4. the API's order (MHSAA tiebreakers on completed games).
 * Early in a season the tiebreakers often can't separate level teams, so the
 * odds give the more meaningful order; once region play is over, the odds
 * already reflect the tiebreakers.
 */
export function displayOrder(entries) {
  const weighted = entries.some((e) => (e.odds?.p_playoffs_weighted ?? 0) > 0);
  const keys = ["p1", "p_playoffs", "p2", "p3", "p4"].map((k) => (weighted ? `${k}_weighted` : k));
  const net = (r) => r.region_wins - r.region_losses;
  const compare = (a, b) => {
    const pct = (winPct(b.record) ?? 0.5) - (winPct(a.record) ?? 0.5);
    if (pct) return pct;
    const games = net(b.record) - net(a.record);
    if (games) return games;
    for (const k of keys) {
      const d = (b.odds?.[k] ?? 0) - (a.odds?.[k] ?? 0);
      if (d) return d;
    }
    return 0; // Array.prototype.sort is stable: keep the API's order
  };
  return [...entries].sort(compare);
}

/**
 * Whether region play is over, judged from records alone (for views without
 * a remaining-games list): every team has played each of the others once.
 */
export function regionComplete(entries) {
  const n = entries.length;
  return n > 1 && entries.every((e) => {
    const r = e.record;
    return r.region_wins + r.region_losses + r.region_ties >= n - 1;
  });
}

/**
 * A team's road through the playoff bracket, one row per round:
 * { round, reach, neutral, hostIfReach, hostOverall }. Hosting applies
 * through the semifinals; the championship is at a neutral site. 5A-7A skip the second
 * round. Returns [] when the snapshot has no bracket odds.
 */
export function playoffPath(entry, mode, clazz) {
  const b = entry.bracket_odds;
  const h = entry.home_game_odds;
  if (!b) return [];
  const w = mode === "projected" ? "_weighted" : "";
  const o = entry.odds ?? {};
  const pick = (obj, key) => (obj ? obj[`${key}${w}`] ?? null : null);
  const rounds = [
    { round: "First round", reach: mode === "projected" ? o.p_playoffs_weighted : o.p_playoffs, host: pick(h, "first_round") },
    { round: "Second round", reach: pick(b, "second_round"), host: pick(h, "second_round"), skip: clazz >= 5 },
    { round: "Quarterfinals", reach: pick(b, "quarterfinals"), host: pick(h, "quarterfinals") },
    { round: "Semifinals", reach: pick(b, "semifinals"), host: pick(h, "semifinals") },
    { round: "Championship game", reach: pick(b, "finals"), host: null, neutral: true },
    { round: "Wins it all", reach: pick(b, "champion"), host: null },
  ];
  return rounds
    .filter((r) => !r.skip)
    .map(({ round, reach, host, neutral = false }) => ({
      round,
      reach,
      neutral,
      hostIfReach: host,
      hostOverall: host != null && reach != null ? host * reach : null,
    }));
}

const ROUND_TITLES = {
  "First round": "First Round",
  "Second round": "Second Round",
  Quarterfinals: "Quarterfinals",
  Semifinals: "Semifinals",
  "Championship game": "Championship Game",
};

/**
 * Where a playoff team stands once the bracket is underway, read from its
 * round-by-round odds (reached rounds are certain, a round after a loss is
 * zero): { kind: "champion" | "lost" | "advanced", label }, or null when
 * the team isn't in the playoffs or hasn't played a playoff game yet.
 */
export function playoffStatus(entry, clazz) {
  if (!isCertain(entry?.odds?.p_playoffs)) return null;
  const path = playoffPath(entry, "tossup", clazz);
  if (!path.length) return null;
  if (isCertain(path[path.length - 1].reach)) return { kind: "champion", label: "State Champion" };
  const rounds = path.slice(0, -1); // through the championship game
  let i = -1;
  rounds.forEach((r, k) => { if (isCertain(r.reach)) i = k; });
  if (i < 0) return null;
  const next = path[i + 1];
  if (next.reach != null && next.reach <= 1e-9) {
    return { kind: "lost", label: `Lost in ${ROUND_TITLES[rounds[i].round]}` };
  }
  if (i === 0) return null; // in the bracket, first round still to play
  return { kind: "advanced", label: `Advanced to ${ROUND_TITLES[rounds[i].round]}` };
}

const pairKey = (a, b) => [a, b].sort().join("\u0000");

/**
 * Who's the visitor: { away, home, joiner }. `location_a` is team_a's side
 * ("home" / "away" / "neutral" / null). The visitor is listed first with
 * "at"; at a neutral or unknown site the teams keep their order with "vs".
 */
export function orient(teamA, teamB, locationA) {
  if (locationA === "home") return { away: teamB, home: teamA, joiner: "at" };
  if (locationA === "away") return { away: teamA, home: teamB, joiner: "at" };
  return { away: teamA, home: teamB, joiner: "vs" };
}

/**
 * Split a region's games into finished results and remaining dates.
 * `games` are /games rows (one per contest); only region games count, and
 * results are limited to those played on or before `asOf` so a past week
 * shows that week's picture. Results come oldest first, each with the
 * visitor first ({ away, home, awayScore, homeScore, joiner }) as well as
 * { winner, loser, tie }. `upcoming(a, b)` gives a remaining matchup (either
 * team order) as it's scheduled: { date, away, home, joiner }, or null when
 * the schedule doesn't list it.
 */
export function regionGames(games, asOf) {
  const results = [];
  const dates = new Map();
  for (const g of games ?? []) {
    if (!g.is_region_game) continue;
    const played = g.final && g.score_a != null && g.score_b != null;
    if (played && (!asOf || g.date <= asOf)) {
      const side = orient(g.team_a, g.team_b, g.location_a);
      const score = { [g.team_a]: g.score_a, [g.team_b]: g.score_b };
      const tie = g.score_a === g.score_b;
      results.push({
        date: g.date,
        ...side,
        awayScore: score[side.away],
        homeScore: score[side.home],
        winner: tie ? null : g.score_a > g.score_b ? g.team_a : g.team_b,
        loser: tie ? null : g.score_a > g.score_b ? g.team_b : g.team_a,
        tie,
      });
    } else {
      dates.set(pairKey(g.team_a, g.team_b), { date: g.date ?? null, ...orient(g.team_a, g.team_b, g.location_a) });
    }
  }
  results.sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : 0));
  return { results, upcoming: (a, b) => dates.get(pairKey(a, b)) ?? null };
}

/**
 * Group items by their `date`, oldest day first, undated items last:
 * [{ date, items }]. Order within a day is kept.
 */
export function byDay(items) {
  const days = new Map();
  for (const item of items) {
    const key = item.date ?? null;
    if (!days.has(key)) days.set(key, []);
    days.get(key).push(item);
  }
  return [...days.entries()]
    .sort(([a], [b]) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : a < b ? -1 : 1))
    .map(([date, list]) => ({ date, items: list }));
}

/**
 * One team's region schedule, from its own side: completed games as
 * { date, opponent, joiner, scoreFor, scoreAgainst, result } (W / L / T),
 * and remaining games as { date, opponent, joiner }. The joiner is "at" for
 * road games and "vs" otherwise. Both lists run oldest first.
 */
export function teamSchedule(team, results, remaining) {
  const sideOf = (g) => {
    if (g.home === team) return { opponent: g.away, joiner: "vs" };
    return { opponent: g.home, joiner: g.joiner === "at" ? "at" : "vs" };
  };
  const completed = results
    .filter((g) => g.away === team || g.home === team)
    .map((g) => {
      const mine = g.home === team ? g.homeScore : g.awayScore;
      const theirs = g.home === team ? g.awayScore : g.homeScore;
      return {
        date: g.date,
        ...sideOf(g),
        scoreFor: mine,
        scoreAgainst: theirs,
        result: g.tie ? "T" : g.winner === team ? "W" : "L",
      };
    });
  const byDate = (x, y) => (x.date ?? "9999") < (y.date ?? "9999") ? -1 : (x.date ?? "9999") > (y.date ?? "9999") ? 1 : 0;
  const upcoming = remaining
    .filter((g) => g.away === team || g.home === team)
    .map((g) => ({ date: g.date, ...sideOf(g) }))
    .sort(byDate); // the standings list them by team name; undated games last
  return { completed: completed.sort(byDate), upcoming };
}

/**
 * The snapshot date to request for a chosen week, or null for "latest".
 * `weeks` are played weeks oldest first ({ week, end }), `week` the chosen
 * week number (null = the newest). Snapshots dated after a week's games but
 * before the next week's are what "through week N" shows, so a week maps to
 * its Sunday.
 *
 * In the current season the newest week means "now", so it asks for the
 * latest snapshot. A past season is pinned to its last week instead: any
 * snapshot written for it later (a stray manual run, say) is not the
 * season's final word and must not stand in for it.
 */
export function snapshotDate(weeks, week, pastSeason) {
  if (!weeks.length) return null;
  const latest = weeks[weeks.length - 1];
  const chosen = (week && weeks.find((w) => w.week === week)) || latest;
  if (pastSeason) return chosen.end;
  return chosen === latest ? null : chosen.end;
}
