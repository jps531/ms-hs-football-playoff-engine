// Bracket view data shaping: game states, side labels, occupants and
// matchups in the chosen odds mode, and a picked team's possible opponents.
// No DOM, so it runs under `node --test`.
//
// Inputs are the two API responses:
//   /bracket            -> bracket_layout (results, scores, venues)
//   /bracket/matchups   -> games[] (sides, occupants, matchups, hosting)
// Hosting always comes from the API; nothing here applies MHSAA rules.

const SEED_NAMES = { 1: "champion", 2: "runner-up", 3: "3rd seed", 4: "4th seed" };

/** "Region 3 champion", "Region 4 runner-up". */
export function positionName({ region, seed }) {
  return `Region ${region} ${SEED_NAMES[seed] ?? `#${seed}`}`;
}

/**
 * Where one side of a game comes from: a single position's name in the
 * first round ("Region 3 champion"), and a list of the positions that can
 * win their way there later ("Region 1 champion, Region 2 4th seed, ... or
 * Region 4 3rd seed").
 */
export function sideLabel(feeders) {
  const names = feeders.map(positionName);
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
}

/** Results from the layout, keyed like the matchups' game ids. */
export function layoutResults(layout) {
  const out = {};
  const toResult = (r) => r && r.winner?.school
    ? {
      winner: r.winner.school,
      loser: r.loser?.school ?? null,
      winnerScore: r.winner_score ?? null,
      loserScore: r.loser_score ?? null,
    }
    : null;
  for (const [half, rounds] of Object.entries(layout?.halves ?? {})) {
    rounds.forEach((games, k) => games.forEach((g, i) => {
      const res = toResult(g.result);
      if (res) out[`${half}-${k}-${i}`] = res;
    }));
  }
  const final = toResult(layout?.championship?.result);
  if (final) out.final = final;
  return out;
}

const pick = (obj, key, mode) => {
  const w = obj[`${key}_weighted`];
  return mode === "projected" && w != null ? w : obj[key];
};

/** One side's occupants in the odds mode, likeliest first: [{ team, p, locked }]. */
export function occupants(side, mode) {
  return side.occupants
    .map((o) => ({ team: o.team, p: pick(o, "p_reach", mode) ?? 0, locked: o.is_locked }))
    .filter((o) => o.p > 0 || o.locked)
    .sort((a, b) => b.p - a.p || a.team.localeCompare(b.team));
}

/** The team certain to fill a side, or null. */
export function lockedTeam(side) {
  const locked = side.occupants.find((o) => o.is_locked);
  return locked ? locked.team : null;
}

/**
 * How settled a game is:
 *   "played"     — it has a result (scores, winner)
 *   "determined" — both teams locked, not yet played
 *   "partial"    — one side locked, the other open
 *   "projected"  — neither side locked
 */
export function gameState(game, result) {
  if (result) return "played";
  const a = lockedTeam(game.side_a);
  const b = lockedTeam(game.side_b);
  if (a && b) return "determined";
  if (a || b) return "partial";
  return "projected";
}

/**
 * Who hosts a pairing, as data for a label: { host: "a" | "b" | "split" |
 * "neutral", p } where p is side A's chance of hosting.
 */
export function hosting(pHostA) {
  if (pHostA == null) return { host: "neutral", p: null };
  if (pHostA >= 0.995) return { host: "a", p: 1 };
  if (pHostA <= 0.005) return { host: "b", p: 0 };
  return { host: "split", p: pHostA };
}

/** The game's matchups in the odds mode, likeliest first. */
export function matchups(game, mode) {
  return (game.matchups ?? [])
    .map((m) => ({
      a: m.team_a,
      b: m.team_b,
      p: pick(m, "p_matchup", mode) ?? 0,
      hostA: pick(m, "p_host_a", mode),
    }))
    .filter((m) => m.p > 0)
    .sort((x, y) => y.p - x.p || x.a.localeCompare(y.a) || x.b.localeCompare(y.b));
}

/** P(team plays in this game) in the odds mode, and which side it'd be on. */
export function teamInGame(game, team, mode) {
  for (const [key, side] of [["a", game.side_a], ["b", game.side_b]]) {
    const o = side.occupants.find((x) => x.team === team);
    if (o) return { side: key, p: pick(o, "p_reach", mode) ?? 0, locked: o.is_locked };
  }
  return null;
}

/**
 * A picked team's possible opponents in one game, from its own point of view:
 * [{ opponent, p, hosts }] where p is the chance of facing that opponent *if*
 * the team gets here, and hosts is "team" / "opponent" / "split" / "neutral"
 * (with pTeamHosts). Likeliest first. Empty when the team can't play here.
 */
export function opponentsFor(game, team, mode) {
  const here = teamInGame(game, team, mode);
  if (!here || here.p <= 0) return [];
  const rows = [];
  for (const m of matchups(game, mode)) {
    const mine = here.side === "a" ? m.a : m.b;
    if (mine !== team) continue;
    const opponent = here.side === "a" ? m.b : m.a;
    const pTeamHosts = m.hostA == null ? null : here.side === "a" ? m.hostA : 1 - m.hostA;
    const h = hosting(pTeamHosts);
    rows.push({
      opponent,
      p: m.p / here.p,
      hosts: h.host === "a" ? "team" : h.host === "b" ? "opponent" : h.host,
      pTeamHosts,
    });
  }
  return rows.sort((x, y) => y.p - x.p || x.opponent.localeCompare(y.opponent));
}

/** Every game id a team can still play in (its possible path), for highlighting. */
export function pathGames(games, team, mode) {
  const ids = new Set();
  for (const g of games) {
    const here = teamInGame(g, team, mode);
    if (here && (here.p > 0 || here.locked)) ids.add(g.id);
  }
  return ids;
}

/**
 * Games grouped for display: { halves: [{ half, rounds: [{ name, games }] }],
 * final } in the API's order (half by half, round by round). Nothing about
 * round counts is assumed: rounds come from the ids.
 */
export function bracketStructure(games) {
  const halves = new Map();
  let final = null;
  for (const g of games) {
    if (g.id === "final") {
      final = g;
      continue;
    }
    const [half, k] = g.id.split("-");
    if (!halves.has(half)) halves.set(half, new Map());
    const rounds = halves.get(half);
    if (!rounds.has(k)) rounds.set(k, { name: g.round, games: [] });
    rounds.get(k).games.push(g);
  }
  return {
    halves: [...halves.entries()].map(([half, rounds]) => ({
      half,
      rounds: [...rounds.entries()].sort(([x], [y]) => Number(x) - Number(y)).map(([, r]) => r),
    })),
    final,
  };
}
