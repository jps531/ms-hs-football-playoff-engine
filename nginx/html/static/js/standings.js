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
 * Teams in display order: the API's order (MHSAA tiebreakers on completed
 * games, clinched seeds pinned), except that teams level on region record
 * are ordered by their projected odds of finishing 1st, then 2nd, 3rd, 4th,
 * and making the playoffs. Early in a season the tiebreakers often can't
 * separate level teams, so the odds give the more meaningful order. Falls
 * back to toss-up odds when a snapshot has no projected odds.
 */
export function displayOrder(entries) {
  const weighted = entries.some((e) => (e.odds?.p_playoffs_weighted ?? 0) > 0);
  const keys = ["p1", "p2", "p3", "p4", "p_playoffs"].map((k) => (weighted ? `${k}_weighted` : k));
  const byOdds = (a, b) => {
    for (const k of keys) {
      const d = (b.odds?.[k] ?? 0) - (a.odds?.[k] ?? 0);
      if (d) return d;
    }
    return 0; // Array.prototype.sort is stable: keep the API's order
  };
  const out = [];
  let run = [];
  for (const e of entries) {
    if (run.length && winPct(run[0].record) !== winPct(e.record)) {
      out.push(...run.sort(byOdds));
      run = [];
    }
    run.push(e);
  }
  return out.concat(run.sort(byOdds));
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
