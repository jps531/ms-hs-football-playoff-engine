import { test } from "node:test";
import assert from "node:assert/strict";
import { outcomeCards, insightCards } from "../html/static/js/scenarios.js";

const cond = (w, l) => [{ type: "game_result", school: w, opponent: l }];
const seed = (value, p, groups) => ({ outcome: { type: "seed", value }, p, conditions: groups });
const playoffs = (p, groups) => ({ outcome: { type: "playoffs" }, p, conditions: groups });
const UNCONDITIONAL = [[]];

test("2-7A shape: title locked, bubble teams and seeding become cards", () => {
  const teams = [
    { school: "Oxford", clinched: true, paths: [seed(1, 1, UNCONDITIONAL), playoffs(1, UNCONDITIONAL)] },
    { school: "Starkville", clinched: true, paths: [seed(3, 0.5, [cond("Clinton", "MC")]), seed(4, 0.5, [cond("MC", "Clinton")]), playoffs(1, UNCONDITIONAL)] },
    { school: "MC", paths: [seed(3, 0.5, [cond("MC", "Clinton")]), seed(4, 0.146, [cond("Clinton", "MC")]), playoffs(0.646, [cond("MC", "Clinton")])] },
    { school: "Clinton", paths: [seed(4, 0.354, [cond("Clinton", "MC")]), playoffs(0.354, [cond("Clinton", "MC")])] },
    { school: "Murrah", eliminated: true, paths: [{ outcome: { type: "eliminated" }, p: 1, conditions: UNCONDITIONAL }] },
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
  const teams = [{ school: "Mize", paths: [seed(1, 0.25, [cond("Mize", "Bay")]), playoffs(0.25, [cond("Mize", "Bay")])] }];
  const g = outcomeCards(teams);
  assert.deepEqual(g.title.map((c) => c.title), ["Mize wins the region"]);
  assert.deepEqual(g.playoffs, []);
});

test("a bubble team gets the simpler of 'makes the playoffs' and 'is eliminated'", () => {
  const many = [cond("A", "B"), cond("C", "D"), cond("E", "F")];
  const teams = [{ school: "NWR", paths: [
    seed(2, 0.4, [cond("NWR", "Pearl")]), seed(4, 0.35, [cond("Pearl", "NWR")]),
    playoffs(0.75, many), { outcome: { type: "eliminated" }, p: 0.25, conditions: [cond("Brandon", "NWR")] },
  ] }];
  assert.deepEqual(outcomeCards(teams).playoffs.map((c) => [c.title, c.p]), [["NWR is eliminated", 0.25]]);
});

test("cards sort by probability within a group", () => {
  const teams = [
    { school: "A", paths: [seed(1, 0.25, [cond("A", "B")]), seed(2, 0.75, [cond("B", "A")]), playoffs(1, UNCONDITIONAL)], clinched: true },
    { school: "B", paths: [seed(1, 0.75, [cond("B", "A")]), seed(2, 0.25, [cond("A", "B")]), playoffs(1, UNCONDITIONAL)], clinched: true },
  ];
  assert.deepEqual(outcomeCards(teams).title.map((c) => c.team), ["B", "A"]);
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
