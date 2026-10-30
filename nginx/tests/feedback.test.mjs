import { test } from "node:test";
import assert from "node:assert/strict";
import {
  feedbackSubject, feedbackProblem, feedbackBody, scoreProblem, scoreBody, dateProblem, dateBody, playoffScoreProblem, playoffScoreBody, submissionError, MESSAGE_MAX,
} from "../html/static/js/feedback.js";

const GAME = { date: "2026-10-09", away: "Seminary", home: "Raleigh", awayScore: 21, homeScore: 28 };

test("subjects name the category and what it's about, within the API's limit", () => {
  assert.equal(feedbackSubject("odds", "Region 6-3A · Raleigh"), "Odds or scenarios · Region 6-3A · Raleigh");
  assert.equal(feedbackSubject("other", null), "Feedback");
  assert.equal(feedbackSubject("nonsense", null), "Feedback");
  assert.equal(feedbackSubject("score", "x".repeat(300)).length, 200);
});

test("general reports need a real message and, if given, a plausible email", () => {
  assert.match(feedbackProblem({ message: "  " }), /tell us what’s wrong/);
  assert.equal(feedbackProblem({ message: "28-21" }), null); // short is fine
  assert.equal(feedbackProblem({ message: "x".repeat(MESSAGE_MAX + 1) }), "Please keep it to 2,000 characters or fewer.");
  assert.equal(feedbackProblem({ message: "x".repeat(MESSAGE_MAX) }), null); // the limit itself is allowed
  assert.match(feedbackProblem({ message: "Raleigh can't finish 4th", email: "nope" }), /email/);
  assert.equal(feedbackProblem({ message: "Raleigh can't finish 4th", email: "" }), null);
  assert.equal(feedbackProblem({ message: "Raleigh can't finish 4th", email: "fan@example.com" }), null);
});

test("feedback body carries context, trims, and leaves out a blank email", () => {
  assert.deepEqual(
    feedbackBody({ category: "odds", context: "Region 6-3A", message: "  Raleigh can't be 4th  ", email: " ", page: "/standings/3a/6" }),
    { subject: "Odds or scenarios · Region 6-3A", message: "Raleigh can't be 4th", category: "odds", page: "/standings/3a/6" },
  );
  assert.equal(feedbackBody({ category: "other", message: "hi there!!", email: "a@b.co", page: "/", website: "x" }).website, "x");
});

test("a score correction must be two whole scores, different from what we have", () => {
  assert.match(scoreProblem(GAME, { awayScore: "", homeScore: "28" }), /both/);
  assert.match(scoreProblem(GAME, { awayScore: "2.5", homeScore: "28" }), /both/);
  assert.match(scoreProblem(GAME, { awayScore: "21", homeScore: "28" }), /score we have/);
  assert.equal(scoreProblem(GAME, { awayScore: "24", homeScore: "28" }), null);
  // A game with no score yet: any valid final score is new.
  const unplayed = { ...GAME, awayScore: null, homeScore: null };
  assert.equal(scoreProblem(unplayed, { awayScore: "21", homeScore: "28" }), null);
  assert.match(scoreProblem(unplayed, { awayScore: "", homeScore: "" }), /both/);
});

test("score body is the visiting team's side of the game", () => {
  assert.deepEqual(scoreBody(GAME, { awayScore: "24", homeScore: "28", note: " Box score says 24 ", page: "/standings/3a/6" }), {
    school: "Seminary", date: "2026-10-09", points_for: 24, points_against: 28, page: "/standings/3a/6", note: "Box score says 24",
  });
});

test("failures are explained in plain words", () => {
  assert.equal(submissionError(429), "You’ve sent a lot of reports in a short time. Please try again later.");
  assert.equal(submissionError(403, "The spam check didn’t pass. Please try again."), "The spam check didn’t pass. Please try again.");
  assert.match(submissionError(403), /spam check/);
  assert.equal(submissionError(503, "Busy, try later."), "Busy, try later.");
  assert.equal(submissionError(422, "That game hasn’t been played yet"), "That game hasn’t been played yet");
  assert.match(submissionError(422, [{ msg: "x" }]), /wasn’t accepted/);
  assert.match(submissionError(404), /couldn’t find that game/);
  assert.match(submissionError(0), /connection/);
  assert.match(submissionError(500), /our end/);
});

test("a date report needs a new date in the game's season, and sends the visiting team's side", () => {
  const game = { date: "2026-10-09", away: "Seminary", home: "Raleigh", joiner: "at" };
  assert.match(dateProblem(game, { newDate: "" }), /Choose the date/);
  assert.match(dateProblem(game, { newDate: "2026-10-09" }), /date we have/);
  assert.match(dateProblem(game, { newDate: "2025-10-10" }), /same season/);
  assert.equal(dateProblem(game, { newDate: "2026-10-10" }), null);
  assert.deepEqual(dateBody(game, { newDate: "2026-10-10", note: " MHSAA moved it ", page: "/standings/3a/6" }), {
    school: "Seminary", date: "2026-10-09", new_date: "2026-10-10", page: "/standings/3a/6", note: "MHSAA moved it",
  });
});

test("a playoff score report needs a played date in the season and both scores, and sends the bracket game", () => {
  const game = { season: 2026, clazz: 3, id: "N-2-1", round: "Quarterfinals", teamA: "Union", teamB: "Raleigh", order: ["b", "a"], joiner: "at" };
  const ok = { date: "2026-11-20", pointsA: "21", pointsB: "35", today: "2026-11-21" };
  assert.equal(playoffScoreProblem(game, ok), null);
  assert.match(playoffScoreProblem(game, { ...ok, date: "" }), /Choose the date/);
  assert.match(playoffScoreProblem(game, { ...ok, date: "2026-11-22" }), /hasn’t come yet/);
  assert.match(playoffScoreProblem(game, { ...ok, date: "2025-11-20" }), /game’s season/);
  assert.match(playoffScoreProblem(game, { ...ok, pointsB: "" }), /both/);
  assert.deepEqual(playoffScoreBody(game, { ...ok, note: " MaxPreps ", page: "/brackets/3a" }), {
    season: 2026, class_: 3, game: "N-2-1", team_a: "Union", team_b: "Raleigh", date: "2026-11-20",
    points_a: 21, points_b: 35, page: "/brackets/3a", note: "MaxPreps",
  });
});
