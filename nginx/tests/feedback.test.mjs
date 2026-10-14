import { test } from "node:test";
import assert from "node:assert/strict";
import {
  feedbackSubject, feedbackProblem, feedbackBody, scoreProblem, scoreBody, submissionError, MESSAGE_MAX,
} from "../html/static/js/feedback.js";

const GAME = { date: "2026-10-09", away: "Seminary", home: "Raleigh", awayScore: 21, homeScore: 28 };

test("subjects name the category and what it's about, within the API's limit", () => {
  assert.equal(feedbackSubject("odds", "Region 6-3A · Raleigh"), "Odds or scenarios · Region 6-3A · Raleigh");
  assert.equal(feedbackSubject("other", null), "Feedback");
  assert.equal(feedbackSubject("nonsense", null), "Feedback");
  assert.equal(feedbackSubject("score", "x".repeat(300)).length, 200);
});

test("general reports need a real message and, if given, a plausible email", () => {
  assert.match(feedbackProblem({ message: "bad" }), /a little more/);
  assert.match(feedbackProblem({ message: "x".repeat(MESSAGE_MAX + 1) }), /under/);
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
});

test("score body is the visiting team's side of the game", () => {
  assert.deepEqual(scoreBody(GAME, { awayScore: "24", homeScore: "28", note: " Box score says 24 ", page: "/standings/3a/6" }), {
    school: "Seminary", date: "2026-10-09", points_for: 24, points_against: 28, page: "/standings/3a/6", note: "Box score says 24",
  });
});

test("failures are explained in plain words", () => {
  assert.match(submissionError(429), /wait a minute/);
  assert.equal(submissionError(403, "The spam check didn't pass. Please try again."), "The spam check didn't pass. Please try again.");
  assert.match(submissionError(403), /spam check/);
  assert.equal(submissionError(503, "Busy, try later."), "Busy, try later.");
  assert.match(submissionError(404), /couldn't find that game/);
  assert.match(submissionError(0), /connection/);
  assert.match(submissionError(500), /our end/);
});
