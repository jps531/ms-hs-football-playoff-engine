import { test } from "node:test";
import assert from "node:assert/strict";
import {
  standingPositions, playoffPath, regionGames, displayOrder, regionComplete, snapshotDate,
  orient, byDay, teamSchedule,
} from "../html/static/js/standings.js";

const rec = (w, l, t = 0) => ({ record: { region_wins: w, region_losses: l, region_ties: t } });

test("teams level on region record share a position, competition style", () => {
  assert.deepEqual(standingPositions([rec(3, 1), rec(3, 1), rec(2, 2), rec(1, 3), rec(1, 3), rec(0, 4)]), [1, 1, 3, 4, 4, 6]);
  assert.deepEqual(standingPositions([rec(4, 0), rec(3, 1), rec(2, 2)]), [1, 2, 3]);
});

test("only identical records share a position, and teams without games are level", () => {
  assert.deepEqual(standingPositions([rec(2, 1), rec(1, 1, 1), rec(1, 1)]), [1, 2, 3]);
  assert.deepEqual(standingPositions([rec(2, 0), rec(1, 0), rec(1, 0)]), [1, 2, 2]);
  assert.deepEqual(standingPositions([rec(0, 0), rec(0, 0), rec(0, 0)]), [1, 1, 1]);
});

const entry = {
  odds: { p_playoffs: 0.9, p_playoffs_weighted: 0.95 },
  bracket_odds: {
    second_round: 0.6, quarterfinals: 0.4, semifinals: 0.2, finals: 0.1, champion: 0.05,
    second_round_weighted: 0.7, quarterfinals_weighted: 0.5, semifinals_weighted: 0.3, finals_weighted: 0.2, champion_weighted: 0.1,
  },
  home_game_odds: {
    first_round: 0.5, second_round: 0.25, quarterfinals: 0.5, semifinals: 0.5,
    first_round_weighted: 0.6, second_round_weighted: 0.3, quarterfinals_weighted: 0.6, semifinals_weighted: 0.4,
  },
};

test("playoff path: reach, host if there, host overall per round", () => {
  const path = playoffPath(entry, "tossup", 3);
  assert.deepEqual(path.map((p) => p.round), ["First round", "Second round", "Quarterfinals", "Semifinals", "Championship game", "Wins it all"]);
  assert.deepEqual(path[0], { round: "First round", reach: 0.9, neutral: false, hostIfReach: 0.5, hostOverall: 0.45 });
  assert.equal(path[2].hostOverall, 0.2);
  assert.equal(path[4].neutral, true); // championship is at a neutral site
  assert.equal(path[5].neutral, false); // nothing left to host after it
  assert.equal(path[5].reach, 0.05);
});

test("playoff path follows the odds mode and skips 5A-7A's missing round", () => {
  const path = playoffPath(entry, "projected", 6);
  assert.equal(path.some((p) => p.round === "Second round"), false);
  assert.deepEqual(path[0], { round: "First round", reach: 0.95, neutral: false, hostIfReach: 0.6, hostOverall: 0.57 });
  assert.equal(path[1].reach, 0.5);
  assert.deepEqual(playoffPath({ odds: {} }, "tossup", 3), []);
});

test("region games split into results and remaining dates", () => {
  const games = [
    { date: "2025-10-17", team_a: "Oxford", team_b: "Clinton", score_a: 35, score_b: 14, final: true, is_region_game: true },
    { date: "2025-10-24", team_a: "Murrah", team_b: "Starkville", score_a: 21, score_b: 28, final: true, is_region_game: true },
    { date: "2025-10-31", team_a: "Clinton", team_b: "Madison Central", score_a: null, score_b: null, final: false, is_region_game: true },
    { date: "2025-09-05", team_a: "Oxford", team_b: "Tupelo", score_a: 7, score_b: 3, final: true, is_region_game: false },
  ];
  const { results, dateFor } = regionGames(games, "2025-10-31");
  assert.deepEqual(results.map((r) => [r.away, r.awayScore, r.home, r.homeScore, r.winner]), [
    ["Oxford", 35, "Clinton", 14, "Oxford"], // oldest first
    ["Murrah", 21, "Starkville", 28, "Starkville"],
  ]);
  assert.equal(dateFor("Madison Central", "Clinton"), "2025-10-31"); // either order
  assert.equal(dateFor("Oxford", "Tupelo"), null); // non-region games ignored
});

test("a past week's view treats later results as still to play", () => {
  const games = [{ date: "2025-10-24", team_a: "Murrah", team_b: "Starkville", score_a: 21, score_b: 28, final: true, is_region_game: true }];
  const { results, dateFor } = regionGames(games, "2025-10-20");
  assert.equal(results.length, 0);
  assert.equal(dateFor("Starkville", "Murrah"), "2025-10-24");
});

test("tied games are marked", () => {
  const { results } = regionGames([{ date: "2025-10-24", team_a: "A", team_b: "B", score_a: 14, score_b: 14, final: true, is_region_game: true }], null);
  assert.equal(results[0].tie, true);
  assert.equal(results[0].winner, null);
});

test("the visitor is listed first, with vs at a neutral or unknown site", () => {
  assert.deepEqual(orient("A", "B", "home"), { away: "B", home: "A", joiner: "at" });
  assert.deepEqual(orient("A", "B", "away"), { away: "A", home: "B", joiner: "at" });
  assert.deepEqual(orient("A", "B", "neutral"), { away: "A", home: "B", joiner: "vs" });
  assert.deepEqual(orient("A", "B", null), { away: "A", home: "B", joiner: "vs" });
});

test("results put the visitor's score with the visitor", () => {
  const { results } = regionGames([
    { date: "2025-10-24", team_a: "Home", team_b: "Road", score_a: 10, score_b: 21, location_a: "home", final: true, is_region_game: true },
  ], null);
  assert.deepEqual(
    [results[0].away, results[0].awayScore, results[0].home, results[0].homeScore, results[0].joiner],
    ["Road", 21, "Home", 10, "at"],
  );
});

test("games group by day, oldest first, undated last", () => {
  const days = byDay([{ date: "2025-10-08", n: 1 }, { date: null, n: 2 }, { date: "2025-10-01", n: 3 }, { date: "2025-10-08", n: 4 }]);
  assert.deepEqual(days.map((d) => [d.date, d.items.map((i) => i.n)]), [
    ["2025-10-01", [3]], ["2025-10-08", [1, 4]], [null, [2]],
  ]);
});

test("a team's schedule reads from its own side", () => {
  const results = [
    { date: "2025-10-01", away: "Taylorsville", home: "Stringer", joiner: "at", awayScore: 0, homeScore: 48, winner: "Stringer", tie: false },
    { date: "2025-10-08", away: "Stringer", home: "Richton", joiner: "at", awayScore: 7, homeScore: 14, winner: "Richton", tie: false },
    { date: "2025-10-08", away: "Lumberton", home: "Magee", joiner: "at", awayScore: 7, homeScore: 14, winner: "Magee", tie: false },
  ];
  const remaining = [
    { date: "2025-10-15", away: "Stringer", home: "Lumberton", joiner: "at" },
    { date: "2025-10-22", away: "Resurrection", home: "Stringer", joiner: "vs" },
  ];
  const { completed, upcoming } = teamSchedule("Stringer", results, remaining);
  assert.deepEqual(completed.map((g) => [g.joiner, g.opponent, g.scoreFor, g.scoreAgainst, g.result]), [
    ["vs", "Taylorsville", 48, 0, "W"],
    ["at", "Richton", 7, 14, "L"],
  ]);
  assert.deepEqual(upcoming.map((g) => [g.joiner, g.opponent]), [["at", "Lumberton"], ["vs", "Resurrection"]]);
});

const team = (school, w, l, p1w, p1 = p1w) => ({
  school,
  record: { region_wins: w, region_losses: l, region_ties: 0 },
  odds: { p1, p2: 0, p3: 0, p4: 0, p_playoffs: 1, p1_weighted: p1w, p2_weighted: 0, p3_weighted: 0, p4_weighted: 0, p_playoffs_weighted: 1 },
});

test("more games over .500 rank higher, and more games under rank lower", () => {
  const api = [team("A", 0, 2, 0), team("B", 1, 0, 0.9), team("C", 0, 1, 0), team("D", 2, 0, 0.1), team("E", 0, 0, 0.5)];
  assert.deepEqual(displayOrder(api).map((t) => t.school), ["D", "B", "E", "C", "A"]);
});

test("level records break on 1st odds, then playoff odds", () => {
  const withPlayoffs = (t, p) => ({ ...t, odds: { ...t.odds, p_playoffs_weighted: p } });
  const api = [withPlayoffs(team("A", 1, 1, 0.2), 0.5), withPlayoffs(team("B", 1, 1, 0.2), 0.8)];
  assert.deepEqual(displayOrder(api).map((t) => t.school), ["B", "A"]);
});

test("teams level on record are ordered by projected 1st odds; others keep the API order", () => {
  const api = [team("A", 3, 1, 0.2), team("B", 3, 1, 0.7), team("C", 2, 2, 0.1), team("D", 1, 3, 0), team("E", 1, 3, 0)];
  assert.deepEqual(displayOrder(api).map((t) => t.school), ["B", "A", "C", "D", "E"]);
});

test("ties in projected 1st odds fall through to later seeds, then the API order", () => {
  const a = team("A", 0, 0, 0.25);
  const b = { ...team("B", 0, 0, 0.25), odds: { ...team("B", 0, 0, 0.25).odds, p2_weighted: 0.5 } };
  const c = team("C", 0, 0, 0.25);
  assert.deepEqual(displayOrder([a, b, c]).map((t) => t.school), ["B", "A", "C"]);
});

test("display order falls back to toss-up odds without projected odds", () => {
  const noW = (t) => ({ ...t, odds: { ...t.odds, p1_weighted: 0, p_playoffs_weighted: 0 } });
  const api = [noW(team("A", 2, 0, 0, 0.3)), noW(team("B", 2, 0, 0, 0.6))];
  assert.deepEqual(displayOrder(api).map((t) => t.school), ["B", "A"]);
});

test("a region is complete once every team has played all the others", () => {
  assert.equal(regionComplete([team("A", 2, 0, 1), team("B", 1, 1, 0), team("C", 0, 2, 0)]), true);
  assert.equal(regionComplete([team("A", 2, 0, 1), team("B", 1, 0, 0), team("C", 0, 1, 0)]), false);
  assert.equal(regionComplete([]), false);
});

const WEEKS = [
  { week: 10, end: "2025-11-02" },
  { week: 11, end: "2025-11-09" },
  { week: 15, end: "2025-12-07" },
];

test("current season: the newest week means the latest snapshot; earlier weeks pin to their Sunday", () => {
  assert.equal(snapshotDate(WEEKS, null, false), null);
  assert.equal(snapshotDate(WEEKS, 15, false), null);
  assert.equal(snapshotDate(WEEKS, 11, false), "2025-11-09");
});

test("past season: even the final week pins to its date, so later stray snapshots can't stand in", () => {
  assert.equal(snapshotDate(WEEKS, null, true), "2025-12-07");
  assert.equal(snapshotDate(WEEKS, 15, true), "2025-12-07");
  assert.equal(snapshotDate(WEEKS, 10, true), "2025-11-02");
});

test("no played weeks or an unknown week falls back sensibly", () => {
  assert.equal(snapshotDate([], 3, true), null);
  assert.equal(snapshotDate(WEEKS, 99, false), null);
  assert.equal(snapshotDate(WEEKS, 99, true), "2025-12-07");
});
