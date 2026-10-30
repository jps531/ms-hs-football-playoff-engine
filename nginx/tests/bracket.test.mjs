import { test } from "node:test";
import assert from "node:assert/strict";
import {
  positionName, sideLabel, layoutResults, occupants, lockedTeam, gameState, hosting, matchups, byeSide,
  teamInGame, opponentsFor, pathGames, bracketStructure, treeColumns, treeLayout, roundPicks,
} from "../html/static/js/bracket.js";

const occ = (team, p, pw = p, locked = false) => ({ team, p_reach: p, p_reach_weighted: pw, is_locked: locked });
const mu = (a, b, p, pw, hostA, hostAw = hostA) => ({
  team_a: a, team_b: b, p_matchup: p, p_matchup_weighted: pw, p_host_a: hostA, p_host_a_weighted: hostAw,
});

const QF = {
  id: "N-2-0", round: "Quarterfinals", half: "N", decided: false,
  side_a: { feeders: [{ region: 1, seed: 1 }, { region: 2, seed: 4 }], occupants: [occ("Taylorsville", 0.6, 0.7), occ("Mize", 0.4, 0.3)] },
  side_b: { feeders: [{ region: 3, seed: 2 }], occupants: [occ("Bay Springs", 0.5, 0.5), occ("Richton", 0.5, 0.5)] },
  matchups: [
    mu("Taylorsville", "Bay Springs", 0.3, 0.35, 1),
    mu("Taylorsville", "Richton", 0.3, 0.35, 0.25),
    mu("Mize", "Bay Springs", 0.2, 0.15, 0),
    mu("Mize", "Richton", 0.2, 0.15, 0.5),
  ],
  other: { p_matchup: 0, p_matchup_weighted: 0 },
  notes: [],
};

test("positions and sides read the MHSAA way", () => {
  assert.equal(positionName({ region: 3, seed: 1 }), "Region 3 #1 Seed");
  assert.equal(positionName({ region: 4, seed: 2 }), "Region 4 #2 Seed");
  assert.equal(sideLabel([{ region: 3, seed: 1 }]), "Region 3 #1 Seed");
  assert.equal(sideLabel(QF.side_a.feeders), "Region 1 #1 Seed or Region 2 #4 Seed");
  const pos = (pairs) => pairs.map(([region, seed]) => ({ region, seed }));
  assert.equal(sideLabel(pos([[1, 1], [2, 4], [1, 3], [2, 2]])), "Region 1 (#1 Seed, #3 Seed), Region 2 (#2 Seed, #4 Seed)");
  const all = (rs) => pos(rs.flatMap((r) => [1, 2, 3, 4].map((k) => [r, k])));
  assert.equal(sideLabel(all([1, 2, 3, 4])), "Regions 1–4 (Any Seed)");
  assert.equal(sideLabel(all([5, 6])), "Region 5 or 6 (Any Seed)");
  assert.equal(sideLabel([...all([1]), ...pos([[2, 1], [2, 2]])]), "Region 1 (Any Seed), Region 2 (#1 Seed, #2 Seed)");
});

test("occupants follow the odds mode and sort likeliest first", () => {
  assert.deepEqual(occupants(QF.side_a, "projected").map((o) => [o.team, o.p]), [["Taylorsville", 0.7], ["Mize", 0.3]]);
  assert.deepEqual(occupants(QF.side_a, "tossup").map((o) => o.p), [0.6, 0.4]);
  // No Projected odds: fall back to Toss-up rather than showing nothing.
  const noW = { occupants: [occ("A", 0.5, null), occ("B", 0.5, null)] };
  assert.deepEqual(occupants(noW, "projected").map((o) => o.p), [0.5, 0.5]);
});

test("game states: played, determined, partial, projected", () => {
  const lockedSide = (t) => ({ feeders: [], occupants: [occ(t, 1, 1, true)] });
  assert.equal(gameState(QF, null), "projected");
  assert.equal(gameState({ ...QF, side_a: lockedSide("A") }, null), "partial");
  assert.equal(gameState({ ...QF, side_a: lockedSide("A"), side_b: lockedSide("B") }, null), "determined");
  assert.equal(gameState(QF, { winner: "A" }), "played");
  assert.equal(lockedTeam(lockedSide("A")), "A");
});

test("a seed a small region can't fill is a bye, whichever side it's on", () => {
  const bye = { feeders: [{ region: 1, seed: 4 }], occupants: [], bye: true };
  const lockedSide = { feeders: [{ region: 3, seed: 1 }], occupants: [occ("Calhoun City", 1, 1, true)] };
  assert.equal(byeSide({ side_a: lockedSide, side_b: bye }), "b");
  assert.equal(byeSide({ side_a: bye, side_b: QF.side_b }), "a");
  assert.equal(byeSide(QF), null);
  assert.equal(gameState({ side_a: lockedSide, side_b: bye }, null), "bye");
});

test("hosting labels come straight from the API's odds", () => {
  assert.deepEqual(hosting(null), { host: "neutral", p: null });
  assert.deepEqual(hosting(1), { host: "a", p: 1 });
  assert.deepEqual(hosting(0), { host: "b", p: 0 });
  assert.deepEqual(hosting(0.4), { host: "split", p: 0.4 });
});

test("a side hosts only when that's certain: anything short of it is a split with its chance", () => {
  assert.deepEqual(hosting(0.9999), { host: "split", p: 0.9999 });
  assert.deepEqual(hosting(0.001), { host: "split", p: 0.001 });
  assert.deepEqual(hosting(1 - 1e-12), { host: "a", p: 1 }); // float noise on a certainty is still certain
});

test("matchups in the odds mode, likeliest first", () => {
  assert.deepEqual(matchups(QF, "projected").map((m) => `${m.a}-${m.b}`).slice(0, 2), ["Taylorsville-Bay Springs", "Taylorsville-Richton"]);
});

test("a picked team's opponents are conditional on it getting there, with who hosts from its side", () => {
  const opp = opponentsFor(QF, "Taylorsville", "projected");
  assert.deepEqual(opp.map((o) => [o.opponent, o.p, o.hosts]), [
    ["Bay Springs", 0.5, "team"],
    ["Richton", 0.5, "split"],
  ]);
  assert.equal(opp[1].pTeamHosts, 0.25);
  // From side B, side A's hosting odds flip.
  const fromB = opponentsFor(QF, "Bay Springs", "tossup");
  assert.deepEqual(fromB.map((o) => [o.opponent, o.hosts]), [["Taylorsville", "opponent"], ["Mize", "team"]]);
  assert.equal(fromB.reduce((s, o) => s + o.p, 0), 1);
  assert.deepEqual(opponentsFor(QF, "Nobody", "tossup"), []);
  assert.deepEqual(teamInGame(QF, "Mize", "projected"), { sides: ["a"], p: 0.3, locked: false });
});

test("a team's path is every game it can still play in", () => {
  const other = { ...QF, id: "S-2-0", side_a: { feeders: [], occupants: [occ("X", 1)] }, side_b: { feeders: [], occupants: [occ("Y", 1)] } };
  assert.deepEqual([...pathGames([QF, other], "Mize", "tossup")], ["N-2-0"]);
});

test("results from the layout are keyed like the matchup games", () => {
  const p = (school) => ({ region: 1, seed: 1, school });
  const layout = {
    halves: { N: [[{ result: { winner: p("A"), loser: p("B"), winner_score: 21, loser_score: 7 } }, { result: null }], [{}]] },
    championship: { result: { winner: p("A"), loser: p("Z"), winner_score: 14, loser_score: 10 } },
  };
  assert.deepEqual(layoutResults(layout), {
    "N-0-0": { winner: "A", loser: "B", winnerScore: 21, loserScore: 7 },
    final: { winner: "A", loser: "Z", winnerScore: 14, loserScore: 10 },
  });
});

test("structure comes from the ids, whatever the round count", () => {
  const g = (id, round) => ({ id, round });
  const s = bracketStructure([g("N-0-0", "First Round"), g("N-0-1", "First Round"), g("N-1-0", "Semifinals"), g("S-0-0", "First Round"), g("final", "Championship Game")]);
  assert.deepEqual(s.halves.map((h) => [h.half, h.rounds.map((r) => [r.name, r.games.length])]), [
    ["N", [["First Round", 2], ["Semifinals", 1]]],
    ["S", [["First Round", 1]]],
  ]);
  assert.equal(s.final.id, "final");
});

test("tree columns: halves stacked per round, then the final fed by every semifinal", () => {
  const g = (id) => ({ id });
  const structure = {
    halves: [
      { half: "N", rounds: [{ name: "First Round", games: [g("N-0-0"), g("N-0-1"), g("N-0-2"), g("N-0-3")] }, { name: "Quarterfinals", games: [g("N-1-0"), g("N-1-1")] }, { name: "Semifinals", games: [g("N-2-0")] }] },
      { half: "S", rounds: [{ name: "First Round", games: [g("S-0-0"), g("S-0-1"), g("S-0-2"), g("S-0-3")] }, { name: "Quarterfinals", games: [g("S-1-0"), g("S-1-1")] }, { name: "Semifinals", games: [g("S-2-0")] }] },
    ],
    final: { id: "final", round: "Championship Game" },
  };
  const both = treeColumns(structure, ["N", "S"]);
  assert.deepEqual(both.map((c) => c.name), ["First Round", "Quarterfinals", "Semifinals", "Championship Game"]);
  assert.deepEqual(both[1].games.map((x) => [x.game.id, x.feeders]), [["N-1-0", [0, 1]], ["N-1-1", [2, 3]], ["S-1-0", [4, 5]], ["S-1-1", [6, 7]]]);
  assert.deepEqual(both[2].games.map((x) => x.feeders), [[0, 1], [2, 3]]);
  assert.deepEqual(both[3].games[0].feeders, [0, 1]);
  const south = treeColumns(structure, ["S"]);
  assert.deepEqual(south[0].games.map((x) => x.game.id), ["S-0-0", "S-0-1", "S-0-2", "S-0-3"]);
  assert.deepEqual(south[1].games.map((x) => x.feeders), [[0, 1], [2, 3]]);
  assert.deepEqual(south[3].games[0].feeders, [0]);
});

test("tree layout: focus column stacks, later columns center between feeders, and swiping blends", () => {
  const cols = [
    { games: [0, 1, 2, 3].map(() => ({ feeders: [] })) },
    { games: [{ feeders: [0, 1] }, { feeders: [2, 3] }] },
    { games: [{ feeders: [0, 1] }] },
  ];
  const at0 = treeLayout(cols, 0, 100, 80);
  assert.deepEqual(at0.centers, [[40, 140, 240, 340], [90, 290], [190]]);
  assert.equal(at0.height, 380);
  const at1 = treeLayout(cols, 1, 100, 80);
  assert.deepEqual(at1.centers.slice(1), [[40, 140], [90]]);
  assert.equal(at1.height, 180); // the first column is off to the left and doesn't count
  const mid = treeLayout(cols, 0.5, 100, 80);
  assert.deepEqual(mid.centers[1], [65, 215]); // halfway between [90, 290] and [40, 140]
  assert.deepEqual(treeLayout(cols, 9, 100, 80).centers[2], [40]); // focus is clamped
});

test("a team that can reach either side: chances add, and opponents from both orientations combine", () => {
  const side = (occ) => ({ feeders: [], occupants: occ.map(([team, p]) => ({ team, p_reach: p, p_reach_weighted: null, is_locked: false })) });
  const game = {
    id: "N-1-0",
    side_a: side([["Indy", 0.2], ["Winona", 0.5], ["Raleigh", 0.3]]),
    side_b: side([["Indy", 0.1], ["Winona", 0.4], ["Magee", 0.5]]),
    matchups: [
      { team_a: "Indy", team_b: "Winona", p_matchup: 0.08, p_matchup_weighted: null, p_host_a: 1, p_host_a_weighted: null },
      { team_a: "Indy", team_b: "Magee", p_matchup: 0.12, p_matchup_weighted: null, p_host_a: 1, p_host_a_weighted: null },
      { team_a: "Winona", team_b: "Indy", p_matchup: 0.04, p_matchup_weighted: null, p_host_a: 0, p_host_a_weighted: null },
      { team_a: "Raleigh", team_b: "Indy", p_matchup: 0.06, p_matchup_weighted: null, p_host_a: 0.5, p_host_a_weighted: null },
    ],
  };
  const here = teamInGame(game, "Indy", "tossup");
  assert.deepEqual(here.sides, ["a", "b"]);
  assert.ok(Math.abs(here.p - 0.3) < 1e-9);
  const opp = opponentsFor(game, "Indy", "tossup");
  assert.deepEqual(opp.map((o) => o.opponent), ["Magee", "Winona", "Raleigh"]);
  const w = opp.find((o) => o.opponent === "Winona");
  assert.ok(Math.abs(w.pMatchup - 0.12) < 1e-9); // 0.08 as side A + 0.04 as side B
  assert.ok(Math.abs(w.p - 0.4) < 1e-9); // 0.12 / 0.3
  assert.equal(w.hosts, "team"); // hosts in both orientations
  const r = opp.find((o) => o.opponent === "Raleigh");
  assert.equal(r.hosts, "split");
  assert.ok(Math.abs(r.pTeamHosts - 0.5) < 1e-9);
  assert.ok(Math.abs(opp.reduce((s, o) => s + o.p, 0) - 1) < 1e-9);
});

// First-round sides for one region's four seeds (6-3A, Oct 16, Projected): Magee is about as likely
// #1 as #2, so it would otherwise show in both.
const seedSide = (seed, occs) => ({ feeders: [{ region: 6, seed }], occupants: occs });
const r1 = (id, a, b) => ({ game: { id, side_a: a, side_b: b } });
const REGION_6 = {
  games: [
    r1("N-0-0", seedSide(1, [occ("Magee", 0.48), occ("Seminary", 0.47), occ("Raleigh", 0.05)]), seedSide(4, [occ("McLaurin", 0.47), occ("Jefferson Davis County", 0.469)])),
    r1("N-0-1", seedSide(2, [occ("Magee", 0.479), occ("Raleigh", 0.27), occ("Seminary", 0.25)]), seedSide(3, [occ("Raleigh", 0.62), occ("Seminary", 0.28), occ("Magee", 0.04)])),
  ],
};

test("a round shows each team in one slot: its likeliest, the next likeliest elsewhere", () => {
  const picks = roundPicks(REGION_6, "projected");
  assert.equal(picks.get("N-0-0:a"), "Magee"); // #1: Magee's likeliest slot
  assert.equal(picks.get("N-0-1:b"), "Raleigh"); // #3: 62%, not #2's 27%
  assert.equal(picks.get("N-0-1:a"), "Seminary"); // #2: Magee and Raleigh are shown elsewhere
  assert.equal(picks.get("N-0-0:b"), "McLaurin");
  assert.equal(new Set(picks.values()).size, picks.size);
});

test("a tie goes to the better seed, and locked or played teams count as placed", () => {
  const tied = { games: [r1("N-0-0", seedSide(2, [occ("A", 0.5), occ("B", 0.5)]), seedSide(1, [occ("A", 0.5), occ("C", 0.5)]))] };
  const picks = roundPicks(tied, "tossup");
  assert.equal(picks.get("N-0-0:b"), "A"); // #1 beats #2 on a tie
  assert.equal(picks.get("N-0-0:a"), "B");
  const locked = { games: [
    r1("N-0-0", { feeders: [], occupants: [occ("A", 1, 1, true)] }, seedSide(3, [occ("C", 0.2)])),
    r1("N-0-1", seedSide(2, [occ("A", 0.9), occ("B", 0.1)]), seedSide(4, [occ("D", 0.3)])),
  ] };
  assert.equal(roundPicks(locked, "tossup").get("N-0-1:a"), "B");
});

test("a side whose every team is likelier elsewhere still shows its likeliest", () => {
  const only = { games: [r1("N-0-0", seedSide(1, [occ("A", 0.9)]), seedSide(2, [occ("A", 0.1)]))] };
  const picks = roundPicks(only, "tossup");
  assert.equal(picks.get("N-0-0:a"), "A");
  assert.equal(picks.has("N-0-0:b"), false); // the tree falls back to the side's likeliest, A
});
