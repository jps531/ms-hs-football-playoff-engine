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
 * at the top are both 1, and the next team is 3. Teams arrive already in
 * tiebreaker order; "level" means the same region winning percentage.
 */
export function standingPositions(entries) {
  const positions = [];
  entries.forEach((e, i) => {
    const prev = entries[i - 1];
    const tied = prev && winPct(prev.record) === winPct(e.record);
    positions.push(tied ? positions[i - 1] : i + 1);
  });
  return positions;
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

const pairKey = (a, b) => [a, b].sort().join("\u0000");

/**
 * Split a region's games into finished results and remaining dates.
 * `games` are /games rows (one per contest); only region games count, and
 * results are limited to those played on or before `asOf` so a past week
 * shows that week's picture. Results come newest first; `dates` maps a
 * remaining matchup (either team order) to its scheduled date.
 */
export function regionGames(games, asOf) {
  const results = [];
  const dates = new Map();
  for (const g of games ?? []) {
    if (!g.is_region_game) continue;
    const played = g.final && g.score_a != null && g.score_b != null;
    if (played && (!asOf || g.date <= asOf)) {
      const aWon = g.score_a >= g.score_b;
      results.push({
        date: g.date,
        winner: aWon ? g.team_a : g.team_b,
        loser: aWon ? g.team_b : g.team_a,
        winnerScore: Math.max(g.score_a, g.score_b),
        loserScore: Math.min(g.score_a, g.score_b),
        tie: g.score_a === g.score_b,
      });
    } else if (g.date) {
      dates.set(pairKey(g.team_a, g.team_b), g.date);
    }
  }
  results.sort((x, y) => (x.date < y.date ? 1 : x.date > y.date ? -1 : 0));
  return { results, dateFor: (a, b) => dates.get(pairKey(a, b)) ?? null };
}
