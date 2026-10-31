// Bracket view data shaping: game states, side labels, occupants and
// matchups in the chosen odds mode, and a picked team's possible opponents.
// No DOM, so it runs under `node --test`.
//
// Inputs are the two API responses:
//   /bracket            -> bracket_layout (results, scores, venues)
//   /bracket/matchups   -> games[] (sides, occupants, matchups, hosting)
// Hosting always comes from the API; nothing here applies MHSAA rules.

import { isCertain, isImpossible } from "./format.js";

const SEED_NAMES = { 1: "#1 Seed", 2: "#2 Seed", 3: "#3 Seed", 4: "#4 Seed" };

/** "Region 3 #1 Seed", "Region 4 #2 Seed". */
export function positionName({ region, seed }) {
  return `Region ${region} ${SEED_NAMES[seed] ?? `#${seed} Seed`}`;
}

/**
 * Where one side of a game comes from, as short as it can be said:
 *   one or two positions   "Region 3 #1 Seed", "Region 1 #1 Seed or Region 2 #4 Seed"
 *   more, by region        "Region 1 (#1 Seed, #3 Seed), Region 2 (#2 Seed, #4 Seed)"
 *   whole regions          "Region 1 or 2 (Any Seed)", "Regions 1–4 (Any Seed)"
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
    if (regions.length === 1) return `Region ${regions[0]} (Any Seed)`;
    if (regions.length === 2) return `Region ${regions[0]} or ${regions[1]} (Any Seed)`;
    return contiguous
      ? `Regions ${regions[0]}–${regions[regions.length - 1]} (Any Seed)`
      : `Regions ${regions.slice(0, -1).join(", ")} or ${regions[regions.length - 1]} (Any Seed)`;
  }
  return regions.map((r) => {
    if (full(r)) return `Region ${r} (Any Seed)`;
    const seeds = byRegion.get(r).sort((a, b) => a - b).map((k) => SEED_NAMES[k] ?? `#${k} Seed`);
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

/**
 * Each team's chance to win the state championship, from the championship
 * game's occupants (the API's p_champion, the same figure as a team's
 * bracket_odds.champion): [{ team, p }], likeliest first. [] for any other
 * game, or when the API doesn't send it.
 */
export function championOdds(game, mode) {
  if (game?.id !== "final") return [];
  return [...game.side_a.occupants, ...game.side_b.occupants]
    .filter((o) => o.p_champion != null)
    .map((o) => ({ team: o.team, p: pick(o, "p_champion", mode) ?? 0 }))
    .filter((o) => o.p > 0)
    .sort((a, b) => b.p - a.p || a.team.localeCompare(b.team));
}

/**
 * The projected champion: the team likeliest to win the championship game in
 * Projected odds, as { team, p }. Null when it's been played (*result*),
 * without Projected odds, or when two teams tie for likeliest.
 * static_pages.projected_champion() is the same.
 */
export function projectedChampion(game, result) {
  if (game?.id !== "final" || result) return null;
  const list = [...game.side_a.occupants, ...game.side_b.occupants]
    .filter((o) => o.p_champion_weighted > 0)
    .sort((a, b) => b.p_champion_weighted - a.p_champion_weighted);
  if (!list.length || list[1]?.p_champion_weighted === list[0].p_champion_weighted) return null;
  return { team: list[0].team, p: list[0].p_champion_weighted };
}

/**
 * Which team each open side of a tree column shows, so no team shows in two
 * slots of one round: Map of `${gameId}:${a|b}` to team. Taking every
 * (team, side) chance in the column, likeliest first, a team goes to the
 * side where it's likeliest and that side is filled; a side whose teams are
 * all likelier elsewhere falls back to its likeliest. Ties go to the better
 * seed (first round) or the earlier slot. A team already locked into or
 * playing in the column counts as placed. The game sheet still lists everyone.
 *
 * @param {{ games: { game: object }[] }} col  a column from treeColumns()
 * @param {string} mode  "projected" or "tossup"
 * @param {Record<string, object>} results  played games, by id
 */
export function roundPicks(col, mode, results = {}) {
  const placed = new Set();
  const open = [];
  col.games.forEach(({ game }, i) => {
    const result = results[game.id];
    ["a", "b"].forEach((key, j) => {
      const side = key === "a" ? game.side_a : game.side_b;
      const locked = lockedTeam(side) ?? (result ? (key === "a" ? result.winner : result.loser) : null);
      if (locked || result) {
        if (locked) placed.add(locked);
        return;
      }
      const rank = side.feeders.length === 1 ? side.feeders[0].seed : 2 * i + j;
      occupants(side, mode).forEach((o) => open.push({ side: `${game.id}:${key}`, team: o.team, p: o.p, rank }));
    });
  });
  open.sort((x, y) => y.p - x.p || x.rank - y.rank || x.team.localeCompare(y.team));
  const picks = new Map();
  for (const o of open) {
    if (!picks.has(o.side) && !placed.has(o.team)) {
      picks.set(o.side, o.team);
      placed.add(o.team);
    }
  }
  return picks;
}

/** The team certain to fill a side, or null. */
export function lockedTeam(side) {
  const locked = side.occupants.find((o) => o.is_locked);
  return locked ? locked.team : null;
}

/**
 * The side of a first-round game whose seed doesn't exist ("a" or "b"), or
 * null. The API marks it `bye`: its region has too few teams for that seed
 * (a three-team region has no #4 seed), so the other side's team advances
 * without playing.
 */
export function byeSide(game) {
  return game.side_a.bye ? "a" : game.side_b.bye ? "b" : null;
}

/**
 * How `team` can reach side `sideKey` of `game`: one entry for each
 * first-round position on that side it can still take (by the odds `mode`),
 * earliest seed first, each with whether that seed is already its own and the
 * playoff games it still has to win to get here, in order:
 *   [{ feeder, seedLocked, wins: [{ round, opponent, byPosition, depth }] }]
 * (`depth`: how many first-round positions feed that game, so wins sort into
 * the order they're played).
 * A bye needs no win and a game it already won drops out; a position whose
 * game was won by someone else is gone. An opponent is named once locked in
 * ("Neshoba Central"), or by position in the first round ("Region 2 #2 Seed",
 * `byPosition`), else left null. The games on the way are the ones the
 * position plays in whose feeders all come into this side.
 */
export function pathTo(games, results, game, sideKey, team, mode) {
  const side = sideKey === "a" ? game.side_a : game.side_b;
  const at = (f) => `${f.region}:${f.seed}`;
  const within = new Set(side.feeders.map(at));
  const all = (g) => [...g.side_a.feeders, ...g.side_b.feeders];
  const holds = (s, f) => s.feeders.some((x) => at(x) === at(f));
  const out = [];
  for (const feeder of side.feeders) {
    const first = games.find((g) => [g.side_a, g.side_b].some((s) => s.feeders.length === 1 && holds(s, feeder)));
    if (!first) continue;
    const start = holds(first.side_a, feeder) ? first.side_a : first.side_b;
    const seedLocked = lockedTeam(start) === team;
    if (!seedLocked && !occupants(start, mode).some((o) => o.team === team)) continue;
    const chain = games
      .filter((g) => g !== game && all(g).some((x) => at(x) === at(feeder)) && all(g).every((x) => within.has(at(x))))
      .sort((x, y) => all(x).length - all(y).length);
    const wins = [];
    let gone = false;
    for (const g of chain) {
      if (byeSide(g)) continue; // through without playing
      const result = results[g.id];
      if (result) {
        if (result.winner === team) continue;
        gone = true;
        break;
      }
      const other = holds(g.side_a, feeder) ? g.side_b : g.side_a;
      const opponent = lockedTeam(other);
      const byPosition = !opponent && other.feeders.length === 1;
      wins.push({ round: g.round, opponent: opponent ?? (byPosition ? positionName(other.feeders[0]) : null), byPosition, depth: all(g).length });
    }
    if (!gone) out.push({ feeder, seedLocked, wins });
  }
  return out.sort((x, y) => x.feeder.seed - y.feeder.seed);
}

// ------------------------------------------------------ who hosts
// MHSAA's hosting rules, as backend/helpers/bracket_home_odds.py has them
// (r2_home_team, qf_home_team, sf_home_team): "x" or "y" hosts. A position
// is { region, seed }. Same-region opponents: the better seed always hosts.

/** Better seed hosts; equal seeds from different regions: odd years the lower region number, even years the higher. */
function bySeed(x, y, season) {
  if (x.seed !== y.seed) return x.seed < y.seed ? "x" : "y";
  if (season % 2 === 1) return x.region < y.region ? "x" : "y";
  return x.region > y.region ? "x" : "y";
}

/** Second round (r2_home_team): the better seed hosts. */
export function secondRoundHost(x, y, season) {
  return x.region === y.region ? (x.seed < y.seed ? "x" : "y") : bySeed(x, y, season);
}

/** Semifinals (sf_home_team): the better seed hosts; home games played don't count. */
export function semifinalHost(x, y, season) {
  return x.region === y.region ? (x.seed < y.seed ? "x" : "y") : bySeed(x, y, season);
}

/** Quarterfinals (qf_home_team): fewer playoff home games so far hosts (`homesX`, `homesY`), then the better seed. */
export function quarterfinalHost(x, homesX, y, homesY, season) {
  if (x.region === y.region) return x.seed < y.seed ? "x" : "y";
  if (homesX !== homesY) return homesX < homesY ? "x" : "y";
  return bySeed(x, y, season);
}

/**
 * A later-round matchup's ways, each with who hosts it: `a` on side A and
 * `b` on side B, every pairing of their ways here (pathTo), as
 * [{ a: way, b: way, host: "a" | "b" | null }] (null at the neutral
 * championship, or when it can't be told). A way's wins are in order of
 * play; in a quarterfinal of a class with a second round the host also
 * turns on whom each team beat there, so when it does the pairing splits by
 * that opponent, named on the team's Second Round win: one team's when that
 * alone decides it, else both.
 */
export function matchupWays(games, results, game, a, b, mode, season) {
  const at = (f) => `${f.region}:${f.seed}`;
  const firstSide = (f) => {
    for (const g of games) {
      for (const [key, side] of [["a", g.side_a], ["b", g.side_b]]) {
        if (side.feeders.length === 1 && at(side.feeders[0]) === at(f)) return { game: g, key, side };
      }
    }
    return null;
  };
  // A first-round side is the slot's home position on side A (bracket_matchups' feeders).
  const homeInFirst = (f) => firstSide(f)?.key === "a";
  const positionOf = (team) => {
    for (const g of games) {
      for (const side of [g.side_a, g.side_b]) if (side.feeders.length === 1 && lockedTeam(side) === team) return side.feeders[0];
    }
    return null;
  };
  // Who a position's Second Round opponent can be: the other first-round game feeding that game.
  const secondRoundFoes = (f) => {
    const r2 = games.find((g) => g.round === "Second Round" && [g.side_a, g.side_b].some((sd) => sd.feeders.some((x) => at(x) === at(f))));
    if (!r2) return null;
    const mine = r2.side_a.feeders.some((x) => at(x) === at(f)) ? "a" : "b";
    const result = results[r2.id];
    if (result) {
      const beat = positionOf(result.loser);
      return beat ? [{ foe: beat, played: true }] : null;
    }
    const other = mine === "a" ? r2.side_b : r2.side_a;
    const before = firstSide(other.feeders[0])?.game;
    if (!before) return null;
    const done = results[before.id];
    if (done) {
      const won = positionOf(done.winner);
      return won ? [{ foe: won, team: done.winner }] : null;
    }
    const bye = byeSide(before);
    const sides = bye ? [bye === "a" ? before.side_b : before.side_a] : [before.side_a, before.side_b];
    return sides.map((sd) => ({ foe: sd.feeders[0], team: lockedTeam(sd) }));
  };
  const waysA = pathTo(games, results, game, "a", a, mode);
  const waysB = pathTo(games, results, game, "b", b, mode);
  const withQf = game.round === "Quarterfinals" && games.some((g) => g.half === game.half && g.round === "Second Round");
  const name = (z) => (z.team ? { opponent: z.team, byPosition: false } : { opponent: positionName(z.foe), byPosition: true });
  const out = [];
  for (const wa of waysA) {
    for (const wb of waysB) {
      const x = wa.feeder;
      const y = wb.feeder;
      if (game.id === "final") {
        out.push({ a: wa, b: wb, host: null });
      } else if (game.round === "Second Round") {
        out.push({ a: wa, b: wb, host: secondRoundHost(x, y, season) === "x" ? "a" : "b" });
      } else if (game.round === "Semifinals") {
        out.push({ a: wa, b: wb, host: semifinalHost(x, y, season) === "x" ? "a" : "b" });
      } else if (!withQf) {
        out.push({ a: wa, b: wb, host: quarterfinalHost(x, homeInFirst(x) ? 1 : 0, y, homeInFirst(y) ? 1 : 0, season) === "x" ? "a" : "b" });
      } else {
        const fa = secondRoundFoes(x);
        const fb = secondRoundFoes(y);
        if (!fa || !fb) {
          out.push({ a: wa, b: wb, host: null });
          continue;
        }
        const homes = (f, z) => (homeInFirst(f) ? 1 : 0) + (secondRoundHost(f, z.foe, season) === "x" ? 1 : 0);
        const combos = fa.flatMap((za) => fb.map((zb) => ({ za, zb, host: quarterfinalHost(x, homes(x, za), y, homes(y, zb), season) === "x" ? "a" : "b" })));
        if (combos.every((c) => c.host === combos[0].host)) {
          out.push({ a: wa, b: wb, host: combos[0].host });
          continue;
        }
        // An opponent decides it: name it on that Second Round win, and only the one(s) that matter.
        const named = (w, z) => (z.played ? w : { ...w, wins: w.wins.map((v) => (v.round === "Second Round" ? { ...v, ...name(z) } : v)) });
        const onlyBy = (key) => combos.every((c) => combos.every((d) => c[key] !== d[key] || c.host === d.host));
        if (onlyBy("za")) {
          for (const za of fa) out.push({ a: named(wa, za), b: wb, host: combos.find((c) => c.za === za).host });
        } else if (onlyBy("zb")) {
          for (const zb of fb) out.push({ a: wa, b: named(wb, zb), host: combos.find((c) => c.zb === zb).host });
        } else {
          for (const c of combos) out.push({ a: named(wa, c.za), b: named(wb, c.zb), host: c.host });
        }
      }
    }
  }
  return out;
}

/**
 * How settled a game is:
 *   "played"     — it has a result (scores, winner)
 *   "bye"        — one side's seed doesn't exist (byeSide)
 *   "determined" — both teams locked, not yet played
 *   "partial"    — one side locked, the other open
 *   "projected"  — neither side locked
 */
export function gameState(game, result) {
  if (result) return "played";
  if (byeSide(game)) return "bye";
  const a = lockedTeam(game.side_a);
  const b = lockedTeam(game.side_b);
  if (a && b) return "determined";
  if (a || b) return "partial";
  return "projected";
}

/**
 * Who hosts a pairing, as data for a label: { host: "a" | "b" | "split" |
 * "neutral", p } where p is side A's chance of hosting. A side is the host
 * only when that's certain; anything short of it, however close, is a split
 * with its chance (">99% chance Tupelo hosts").
 */
export function hosting(pHostA) {
  if (pHostA == null) return { host: "neutral", p: null };
  if (isCertain(pHostA)) return { host: "a", p: 1 };
  if (isImpossible(pHostA)) return { host: "b", p: 0 };
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
