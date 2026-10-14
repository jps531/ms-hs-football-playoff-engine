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
 * Where one side of a game comes from, as short as it can be said:
 *   one or two positions   "Region 3 champion", "Region 1 champion or Region 2 4th seed"
 *   more, by region        "Region 1 (champion, 3rd seed), Region 2 (runner-up, 4th seed)"
 *   whole regions          "Region 1 or 2 (any seed)", "Regions 1–4 (any seed)"
 */
export function sideLabel(feeders) {
  const names = feeders.map(positionName);
  if (names.length <= 2) return names.join(" or ");
  const byRegion = new Map();
  for (const { region, seed } of feeders) {
    if (!byRegion.has(region)) byRegion.set(region, []);
    byRegion.get(region).push(seed);
  }
  const regions = [...byRegion.keys()].sort((a, b) => a - b);
  const full = (r) => [1, 2, 3, 4].every((k) => byRegion.get(r).includes(k));
  if (regions.every(full)) {
    const contiguous = regions.every((r, i) => !i || r === regions[i - 1] + 1);
    if (regions.length === 1) return `Region ${regions[0]} (any seed)`;
    if (regions.length === 2) return `Region ${regions[0]} or ${regions[1]} (any seed)`;
    return contiguous
      ? `Regions ${regions[0]}–${regions[regions.length - 1]} (any seed)`
      : `Regions ${regions.slice(0, -1).join(", ")} or ${regions[regions.length - 1]} (any seed)`;
  }
  return regions.map((r) => {
    if (full(r)) return `Region ${r} (any seed)`;
    const seeds = byRegion.get(r).sort((a, b) => a - b).map((k) => SEED_NAMES[k] ?? `#${k}`);
    return `Region ${r} (${seeds.join(", ")})`;
  }).join(", ");
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

/**
 * P(team plays in this game) in the odds mode, and which sides it could be
 * on. A team can reach either side of some games (a region's 2 seed feeds
 * one side and its 3 seed the other), and never both at once, so the
 * chances add.
 */
export function teamInGame(game, team, mode) {
  let p = 0;
  let locked = false;
  const sides = [];
  for (const [key, side] of [["a", game.side_a], ["b", game.side_b]]) {
    const o = side.occupants.find((x) => x.team === team);
    if (!o) continue;
    p += pick(o, "p_reach", mode) ?? 0;
    locked ||= o.is_locked;
    sides.push(key);
  }
  return sides.length ? { sides, p: Math.min(1, p), locked } : null;
}

/**
 * A picked team's possible opponents in one game, from its own point of view:
 * [{ opponent, p, pMatchup, hosts }] where p is the chance of facing that
 * opponent *if* the team gets here, pMatchup the chance this exact game
 * happens, and hosts is "team" / "opponent" / "split" / "neutral"
 * (with pTeamHosts). Likeliest first. Empty when the team can't play here.
 */
export function opponentsFor(game, team, mode) {
  const here = teamInGame(game, team, mode);
  if (!here || here.p <= 0) return [];
  // The same opponent can come from either orientation (team on side A or
  // on side B); combine them, weighting hosting by each one's chance.
  const by = new Map();
  for (const m of matchups(game, mode)) {
    if (m.a !== team && m.b !== team) continue;
    const opponent = m.a === team ? m.b : m.a;
    const hosts = m.hostA == null ? null : m.a === team ? m.hostA : 1 - m.hostA;
    const row = by.get(opponent) ?? { p: 0, hostMass: 0, neutral: false };
    row.p += m.p;
    if (hosts == null) row.neutral = true;
    else row.hostMass += m.p * hosts;
    by.set(opponent, row);
  }
  const rows = [];
  for (const [opponent, r] of by) {
    const pTeamHosts = r.neutral ? null : r.hostMass / r.p;
    const h = hosting(pTeamHosts);
    rows.push({
      opponent,
      p: r.p / here.p,
      pMatchup: r.p,
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
