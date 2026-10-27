// The feedback form's data: subjects, validation, request bodies, and what
// to tell someone when a submission fails. No DOM, so it runs under
// `node --test`. Reports go to the API's moderation queue:
//   POST /api/v1/submissions/scores    a corrected score for a specific game
//   POST /api/v1/submissions/feedback  anything else (category: score, odds, other)

export const CATEGORIES = [
  { value: "score", label: "A score", subject: "Score report" },
  { value: "odds", label: "Odds or scenarios", subject: "Odds or scenarios" },
  { value: "other", label: "Something else", subject: "Feedback" },
];

export const MESSAGE_MAX = 2000;
export const NOTE_MAX = 1000;
// A form is never sent sooner than this after it opens: a send before then
// waits out the rest (showing "Sending…"), so a quick real correction still
// arrives while an instant scripted one is slowed.
export const MIN_FILL_MS = 2500;

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** "Odds or scenarios · Region 6-3A · Raleigh", at most 200 characters (the API's limit). */
export function feedbackSubject(category, context) {
  const base = (CATEGORIES.find((c) => c.value === category) ?? CATEGORIES[2]).subject;
  return (context ? `${base} · ${context}` : base).slice(0, 200);
}

/** A problem with a general report's fields, as a sentence for the form, or null. */
export function feedbackProblem({ message, email }) {
  const text = (message ?? "").trim();
  if (!text) return "Please tell us what’s wrong.";
  if (text.length > MESSAGE_MAX) return `Please keep it to ${MESSAGE_MAX.toLocaleString("en-US")} characters or fewer.`;
  if (email && !EMAIL.test(email.trim())) return "That email address doesn’t look right. It’s optional, so you can leave it blank.";
  return null;
}

/** Request body for /submissions/feedback. */
export function feedbackBody({ category, context, message, email, page, website }) {
  const body = {
    subject: feedbackSubject(category, context),
    message: message.trim(),
    category,
    page,
  };
  if (email?.trim()) body.email = email.trim();
  if (website) body.website = website;
  return body;
}

const score = (v) => (/^\d{1,3}$/.test(String(v ?? "").trim()) ? Number(v) : null);

/** A problem with a score correction, as a sentence for the form, or null. */
export function scoreProblem(game, { awayScore, homeScore }) {
  const away = score(awayScore);
  const home = score(homeScore);
  if (away == null || home == null) return "Enter both teams’ final scores.";
  if (away > 200 || home > 200) return "Scores over 200 aren’t accepted. Please check the score.";
  if (away === game.awayScore && home === game.homeScore) return "That’s the score we have. Change it to the correct final score.";
  return null;
}

/**
 * Request body for /submissions/scores. The API takes one school's side of
 * the game (points_for is that school's), so the visiting team's is sent.
 */
export function scoreBody(game, { awayScore, homeScore, note, page, website }) {
  const body = {
    school: game.away,
    date: game.date,
    points_for: Number(awayScore),
    points_against: Number(homeScore),
    page,
  };
  if (note?.trim()) body.note = note.trim().slice(0, NOTE_MAX);
  if (website) body.website = website;
  return body;
}

/** What to say when a submission fails, from the HTTP status (0 for no response) and the API's detail. */
export function submissionError(status, detail) {
  if (status === 403) return typeof detail === "string" ? detail : "The spam check didn’t pass. Please try again.";
  if (status === 429) return "You’ve sent a lot of reports in a short time. Please try again later.";
  if (status === 503) return typeof detail === "string" ? detail : "We’re getting more reports than usual. Please try again in a little while.";
  if (status === 404) return "We couldn’t find that game to correct. Please send it as general feedback instead.";
  if (status === 422) return "Something in the form wasn’t accepted. Please check it and try again.";
  if (status === 0) return "Couldn’t send. Check your connection and try again.";
  return "Something went wrong on our end. Please try again in a moment.";
}
