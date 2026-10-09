import { test } from "node:test";
import assert from "node:assert/strict";
import {
  outcomeCards, insightCards, oddsFor, hasProjectedOdds, outcomeProbability,
} from "../html/static/js/scenarios.js";

const cond = (w, l) => [{ type: "game_result", school: w, opponent: l }];
const seed = (value, p, groups) => ({ outcome: { type: "seed", value }, p, conditions: groups });
const playoffs = (p, groups) => ({ outcome: { type: "playoffs" }, p, conditions: groups });
const UNCONDITIONAL = [[]];
/** Odds where the toss-up and projected columns differ, so tests can tell them apart. */
const odds = (p1, p2, p3, p4, w = null) => {
  const raw = { p1, p2, p3, p4, p_playoffs: p1 + p2 + p3 + p4 };
  const ww = w ?? [p1, p2, p3, p4];
  return { ...raw, p1_weighted: ww[0], p2_weighted: ww[1], p3_weighted: ww[2], p4_weighted: ww[3], p_playoffs_weighted: ww.reduce((a, b) => a + b, 0) };
};

test("2-7A shape: title locked, bubble teams and seeding become cards", () => {
  const teams = [
    { school: "Oxford", clinched: true, odds: odds(1, 0, 0, 0), paths: [seed(1, 1, UNCONDITIONAL), playoffs(1, UNCONDITIONAL)] },
    { school: "Starkville", clinched: true, odds: odds(0, 0, 0.5, 0.5), paths: [seed(3, 0.5, [cond("Clinton", "MC")]), seed(4, 0.5, [cond("MC", "Clinton")]), playoffs(1, UNCONDITIONAL)] },
    { school: "MC", odds: odds(0, 0, 0.5, 0.146), paths: [seed(3, 0.5, [cond("MC", "Clinton")]), seed(4, 0.146, [cond("Clinton", "MC")]), playoffs(0.646, [cond("MC", "Clinton")])] },
    { school: "Clinton", odds: odds(0, 0, 0, 0.354), paths: [seed(4, 0.354, [cond("Clinton", "MC")]), playoffs(0.354, [cond("Clinton", "MC")])] },
    { school: "Murrah", eliminated: true, odds: odds(0, 0, 0, 0), paths: [{ outcome: { type: "eliminated" }, p: 1, conditions: UNCONDITIONAL }] },
  ];
  const g = outcomeCards(teams);
  assert.deepEqual(g.title, []); // unconditional #1 is a badge, not a card
  assert.deepEqual(g.playoffs.map((c) => c.title), [
    "MC makes the playoffs",
    "Clinton makes the playoffs as the No. 4 seed",
  ]);
  assert.deepEqual(g.seeding.map((c) => c.title), [
    "Starkville finishes third",
    "Starkville finishes fourth",
    "MC finishes third",
    "MC finishes fourth",
  ]);
});

test("conditional #1 is a title card, and a lone #1 path isn't repeated as a playoff card", () => {
  const teams = [{ school: "Mize", odds: odds(0.25, 0, 0, 0), paths: [seed(1, 0.25, [cond("Mize", "Bay")]), playoffs(0.25, [cond("Mize", "Bay")])] }];
  const g = outcomeCards(teams);
  assert.deepEqual(g.title.map((c) => c.title), ["Mize wins the region"]);
  assert.deepEqual(g.playoffs, []);
});

test("a bubble team gets the simpler of 'makes the playoffs' and 'is eliminated'", () => {
  const many = [cond("A", "B"), cond("C", "D"), cond("E", "F")];
  const teams = [{ school: "NWR", odds: odds(0, 0.4, 0, 0.35), paths: [
    seed(2, 0.4, [cond("NWR", "Pearl")]), seed(4, 0.35, [cond("Pearl", "NWR")]),
    playoffs(0.75, many), { outcome: { type: "eliminated" }, p: 0.25, conditions: [cond("Brandon", "NWR")] },
  ] }];
  assert.deepEqual(outcomeCards(teams).playoffs.map((c) => [c.title, c.p]), [["NWR is eliminated", 0.25]]);
});

test("cards sort by probability within a group", () => {
  const teams = [
    { school: "A", odds: odds(0.25, 0.75, 0, 0, [0.6, 0.4, 0, 0]), paths: [seed(1, 0.25, [cond("A", "B")]), seed(2, 0.75, [cond("B", "A")]), playoffs(1, UNCONDITIONAL)], clinched: true },
    { school: "B", odds: odds(0.75, 0.25, 0, 0, [0.4, 0.6, 0, 0]), paths: [seed(1, 0.75, [cond("B", "A")]), seed(2, 0.25, [cond("A", "B")]), playoffs(1, UNCONDITIONAL)], clinched: true },
  ];
  assert.deepEqual(outcomeCards(teams).title.map((c) => c.team), ["B", "A"]);
  // Projected odds reorder the same cards.
  assert.deepEqual(outcomeCards(teams, "projected").title.map((c) => [c.team, c.p]), [["A", 0.6], ["B", 0.4]]);
});

test("odds mode picks the weighted or toss-up column", () => {
  const t = { odds: odds(0.5, 0.5, 0, 0, [0.8, 0.2, 0, 0]) };
  assert.equal(oddsFor(t, "tossup").p1, 0.5);
  assert.equal(oddsFor(t, "projected").p1, 0.8);
  assert.equal(outcomeProbability(t, { type: "seed", value: 2 }, "projected"), 0.2);
  assert.equal(outcomeProbability(t, { type: "playoffs" }, "tossup"), 1);
  assert.equal(outcomeProbability({ odds: odds(0.3, 0, 0, 0) }, { type: "eliminated" }, "tossup"), 0.7);
});

test("projected odds count as available only when the weighted column was computed", () => {
  assert.equal(hasProjectedOdds([{ odds: odds(1, 0, 0, 0) }]), true);
  assert.equal(hasProjectedOdds([{ odds: { p1: 1, p_playoffs: 1, p1_weighted: 0, p_playoffs_weighted: 0 } }]), false);
  assert.equal(hasProjectedOdds([]), false);
});

test("insights become one-way cards with margins preserved", () => {
  const cards = insightCards([
    { insight_type: "eliminated_if", team: "Murrah", conditions: [{ winner: "Starkville", loser: "Terry", min_margin: 1, max_margin: null }] },
    { insight_type: "already_clinched", team: "Oxford", conditions: [] },
    { insight_type: "clinch_seed", team: "Taylorsville", seed: 1, conditions: [{ winner: "Taylorsville", loser: "Stringer", min_margin: 8, max_margin: null }] },
  ]);
  assert.deepEqual(cards.map((c) => c.title), ["Taylorsville clinches the region", "Murrah is eliminated"]);
  assert.equal(cards[0].groups[0][0].min_margin, 8);
  assert.equal(cards[0].p, null);
});

test("insights proving the same outcome merge into one card, joined by OR", () => {
  const elim = (loser) => ({
    insight_type: "eliminated_if", team: "Richton",
    conditions: [{ winner: "Lumberton", loser: "Richton", min_margin: 1, max_margin: null }, { winner: "Stringer", loser, min_margin: 1, max_margin: null }],
  });
  const cards = insightCards([elim("Lumberton"), elim("Resurrection"), { ...elim("X"), team: "Bay" }]);
  assert.deepEqual(cards.map((c) => [c.title, c.groups.length]), [["Richton is eliminated", 2], ["Bay is eliminated", 1]]);
  assert.equal(cards[0].groups[1][1].opponent, "Resurrection");
});
