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

/**
 * The bracket as one tree of columns, left to right: each round with the
 * chosen halves' games stacked in order, then the championship. Every game
 * lists its feeders (indices into the previous column), so a game sits
 * between the two games that send it a team.
 *
 * @param {{halves, final}} structure  from bracketStructure()
 * @param {string[]} halves  which halves to include, e.g. ["N", "S"] or ["N"]
 * @returns {{ name: string, games: { game: object, feeders: number[] }[] }[]}
 */
export function treeColumns(structure, halves) {
  const shown = structure.halves.filter((h) => halves.includes(h.half));
  const depth = Math.max(0, ...shown.map((h) => h.rounds.length));
  const cols = [];
  for (let k = 0; k < depth; k++) {
    const games = [];
    let offset = 0; // where this half's previous-round games start in the previous column
    for (const h of shown) {
      const round = h.rounds[k];
      const prevCount = k > 0 ? h.rounds[k - 1].games.length : 0;
      round.games.forEach((game, i) => {
        games.push({ game, feeders: k === 0 ? [] : [offset + 2 * i, offset + 2 * i + 1].filter((j) => j < offset + prevCount) });
      });
      offset += prevCount;
    }
    cols.push({ name: shown[0].rounds[k].name, games });
  }
  if (structure.final && depth > 0) {
    cols.push({ name: structure.final.round, games: [{ game: structure.final, feeders: cols[depth - 1].games.map((_, j) => j) }] });
  }
  return cols;
}

/**
 * Vertical centers of every card for a given focus, in pixels.
 *
 * The focus column (and anything left of it) is a plain stacked list; each
 * column to its right centers every game between its feeders, so lines run
 * straight across. A fractional focus (mid-swipe) blends the two layouts,
 * which is what makes the bracket "condense" as you move round to round.
 *
 * @param cols   from treeColumns()
 * @param focus  0 for the first column; 1.5 is halfway to the third
 * @param pitch  card height plus the gap between cards
 * @param card   card height
 * @returns {{ centers: number[][], height: number }} height of the visible area
 */
export function treeLayout(cols, focus, pitch, card) {
  const last = Math.max(0, cols.length - 1);
  const f = Math.min(Math.max(focus, 0), last);
  const k = Math.floor(f);
  const t = f - k;
  const at = (base) => {
    const out = [];
    cols.forEach((col, r) => {
      out.push(col.games.map((g, i) => {
        const prev = out[r - 1];
        if (r <= base || !g.feeders.length || !prev) return i * pitch + card / 2;
        return g.feeders.reduce((s, j) => s + prev[j], 0) / g.feeders.length;
      }));
    });
    return out;
  };
  const a = at(k);
  const b = t > 0 ? at(Math.min(k + 1, last)) : a;
  const centers = a.map((col, r) => col.map((y, i) => y + (b[r][i] - y) * t));
  const bottom = (col) => (col.length ? Math.max(...col) + card / 2 : 0);
  const height = Math.max(0, ...centers.slice(k).map(bottom));
  return { centers, height };
}
