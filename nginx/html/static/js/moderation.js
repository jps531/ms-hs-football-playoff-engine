// The moderation page's pure parts: labels, the score comparison, and each
// submission's card. moderate.js does the fetching and wiring.

import { escapeHtml as esc, gameDate } from "./format.js";

export const STATUSES = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "accepted_pending_asset", label: "Needs asset" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

const TYPE_LABELS = {
  score: "Score correction",
  date: "Date correction",
  feedback: "Feedback",
  colors: "Colors",
  logo: "Logo",
  helmet: "Helmet",
  helmet_assignment: "Helmet worn",
  location: "Location",
};
const CATEGORY_LABELS = { score: "Score report", odds: "Odds or scenarios", other: "Feedback" };

export function typeName(type) {
  return TYPE_LABELS[type] ?? String(type).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function typeLabel(item) {
  if (item.type === "feedback") {
    const category = CATEGORY_LABELS[item.payload?.category] ?? "Feedback";
    return category === "Feedback" ? "Feedback" : `Feedback · ${category}`;
  }
  return typeName(item.type);
}

/** What a feedback report is about: its subject minus the category the label already shows. */
export function feedbackAbout(payload) {
  let subject = String(payload?.subject ?? "").trim();
  for (const label of Object.values(CATEGORY_LABELS)) {
    if (subject === label) return "";
    if (subject.startsWith(`${label} · `)) subject = subject.slice(label.length + 3);
  }
  return subject;
}

/** The button wording for a type: what approving actually does. */
export function decisionLabels(type) {
  if (type === "score" || type === "date") return { approve: "Apply correction", reject: "Reject" };
  if (type === "feedback") return { approve: "Mark handled", reject: "Dismiss" };
  if (type === "logo") return { approve: "Accept", reject: "Reject" };
  return { approve: "Approve", reject: "Reject" };
}

export function canApprove(item) {
  return item.status === "pending";
}

export function canReject(item) {
  return item.status === "pending" || item.status === "accepted_pending_asset";
}

/** "just now", "12 min ago", "3 hr ago", "2 days ago", then the date. */
export function relativeTime(iso, now = Date.now()) {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((now - then) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(then).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function result(pf, pa) {
  if (pf == null || pa == null) return null;
  return pf > pa ? "W" : pf < pa ? "L" : "T";
}

/**
 * The game a score correction is about, from the submitting school's side:
 * the score the site shows now and the reported one, with what changed.
 */
export function scoreChange(item) {
  const p = item.payload ?? {};
  const game = item.current_game;
  const reported = { for: p.points_for, against: p.points_against, result: result(p.points_for, p.points_against) };
  const current = game
    ? { for: game.points_for, against: game.points_against, result: game.result ?? result(game.points_for, game.points_against) }
    : null;
  // A playoff game the schedule didn't have yet: approving adds it (see scoreHtml).
  const playoff = !game && p.playoff ? p.playoff : null;
  return {
    date: p.date,
    school: item.school,
    opponent: game?.opponent ?? playoff?.opponent ?? null,
    location: game?.location ?? (playoff ? PLAYOFF_LOCATION[playoff.host] ?? null : null),
    playoff,
    current,
    reported,
    changed: {
      for: !current || current.for !== reported.for,
      against: !current || current.against !== reported.against,
    },
  };
}

/** A site path from a report, as a link only when it's on this site. */
export function pageLink(page) {
  if (typeof page !== "string" || !page.startsWith("/") || page.startsWith("//")) return page ? esc(page) : "";
  return `<a href="${esc(page)}" target="_blank" rel="noopener">${esc(page)}</a>`;
}

const LOCATION_WORD = { home: "vs", away: "at", neutral: "vs" };
// A playoff report's host ("a" the reporting school, "b" its opponent) as the school's location.
const PLAYOFF_LOCATION = { a: "home", b: "away", neutral: "neutral" };

function scoreHtml(item) {
  const s = scoreChange(item);
  const cell = (value, changed) => (changed
    ? `<td class="is-changed"><span>${value ?? "–"}</span><span class="visually-hidden"> (changed)</span></td>`
    : `<td>${value ?? "–"}</td>`);
  const opponent = s.opponent ? `${LOCATION_WORD[s.location] ?? "vs"} ${esc(s.opponent)}` : "";
  const where = { a: `at ${s.school}`, b: `at ${s.opponent}`, neutral: "at a neutral site" };
  const missing = s.playoff
    ? `Not on the schedule yet. Approving adds this ${esc(s.playoff.round)} game ${esc(where[s.playoff.host] ?? "")} on this date.`
    : `No game for ${esc(s.school)} that day`;
  const current = s.current
    ? `<tr><th scope="row">On the site</th>${cell(s.current.for)}${cell(s.current.against)}<td class="mod-score__result">${s.current.result ?? ""}</td></tr>`
    : `<tr><th scope="row">On the site</th><td colspan="3" class="muted">${missing}</td></tr>`;
  return `<p class="mod-card__about">${esc(s.school)} ${opponent} · ${esc(gameDate(s.date) || s.date || "")}</p>
    <table class="mod-score">
      <thead><tr><td></td><th scope="col">${esc(s.school)}</th><th scope="col">${esc(s.opponent ?? "Opponent")}</th><td></td></tr></thead>
      <tbody>
        ${current}
        <tr><th scope="row">Reported</th>${cell(s.reported.for, s.changed.for)}${cell(s.reported.against, s.changed.against)}<td class="mod-score__result">${s.reported.result ?? ""}</td></tr>
      </tbody>
    </table>
    ${item.payload?.note ? `<p class="mod-card__meta"><span class="muted">Source:</span> ${esc(item.payload.note)}</p>` : ""}`;
}

/** A date report: the game, the date the site has it on now, and the reported one. */
function dateHtml(item) {
  const p = item.payload ?? {};
  const game = item.current_game;
  const opponent = game?.opponent ? ` ${LOCATION_WORD[game.location] ?? "vs"} ${esc(game.opponent)}` : "";
  const day = (iso) => esc(gameDate(iso) || iso || "");
  const current = game
    ? `<tr><th scope="row">On the site</th><td>${day(game.date)}</td></tr>`
    : `<tr><th scope="row">On the site</th><td class="muted">The game is no longer on the schedule</td></tr>`;
  return `<p class="mod-card__about">${esc(item.school)}${opponent} · reported while shown on ${day(p.date)}</p>
    <table class="mod-score">
      <tbody>
        ${current}
        <tr><th scope="row">Reported</th><td class="is-changed"><span>${day(p.new_date)}</span><span class="visually-hidden"> (changed)</span></td></tr>
      </tbody>
    </table>
    <p class="mod-card__meta muted">Approving moves both schools' rows of the game to the reported date.</p>
    ${p.note ? `<p class="mod-card__meta"><span class="muted">Source:</span> ${esc(p.note)}</p>` : ""}`;
}

function feedbackHtml(item) {
  const p = item.payload ?? {};
  const about = feedbackAbout(p);
  return `${about ? `<p class="mod-card__about">${esc(about)}</p>` : ""}
    <p class="mod-message">${esc(p.message ?? "")}</p>`;
}

/** A payload value as text: a named color as "Blue #0033A0", lists joined, anything else as JSON. */
export function payloadValue(v) {
  if (Array.isArray(v)) return v.map(payloadValue).join(", ");
  if (v && typeof v === "object") {
    if ("name" in v || "hex" in v) return [v.name, v.hex].filter(Boolean).join(" ");
    return JSON.stringify(v);
  }
  return String(v ?? "");
}

function payloadHtml(item) {
  const rows = Object.entries(item.payload ?? {}).map(([k, v]) => {
    const value = payloadValue(v);
    return `<div><dt>${esc(k.replace(/_/g, " "))}</dt><dd>${esc(value)}</dd></div>`;
  });
  return `${item.school ? `<p class="mod-card__about">${esc(item.school)}</p>` : ""}
    ${rows.length ? `<dl class="mod-payload">${rows.join("")}</dl>` : ""}
    <p class="mod-card__meta muted">Previews and asset steps for this type are in the API docs.</p>`;
}

function contextHtml(item) {
  const p = item.payload ?? {};
  const lines = [];
  if (p.page) lines.push(`<span class="muted">Page:</span> ${pageLink(p.page)}`);
  if (p.email) lines.push(`<span class="muted">Reply to:</span> <a href="mailto:${esc(p.email)}">${esc(p.email)}</a>`);
  return lines.map((l) => `<p class="mod-card__meta">${l}</p>`).join("");
}

function decisionHtml(item) {
  if (!canReject(item)) return "";
  const labels = decisionLabels(item.type);
  const approve = canApprove(item)
    ? `<button type="submit" class="fb-submit" name="decision" value="approve">${labels.approve}</button>`
    : "";
  return `<form class="mod-decide" data-decide="${item.id}">
      <label class="fb-field"><span>Note <span class="muted">(optional, saved with the decision)</span></span>
        <textarea name="notes" rows="2" maxlength="2000"></textarea>
      </label>
      <div class="mod-decide__actions">
        ${approve}
        <button type="submit" class="mod-reject" name="decision" value="reject">${labels.reject}</button>
      </div>
      <p class="fb-status" role="status" aria-live="polite"></p>
    </form>`;
}

function reviewedHtml(item) {
  if (item.status === "pending") return "";
  const label = STATUSES.find((s) => s.value === item.status)?.label ?? item.status;
  const when = item.reviewed_at ? ` ${relativeTime(item.reviewed_at)}` : "";
  return `<p class="mod-card__review"><span class="mod-status mod-status--${esc(item.status)}">${esc(label)}</span>${esc(when)}
    ${item.moderator_notes ? `<span class="mod-card__notes">${esc(item.moderator_notes)}</span>` : ""}</p>`;
}

export function itemHtml(item, now = Date.now()) {
  const body = item.type === "score" ? scoreHtml(item)
    : item.type === "date" ? dateHtml(item)
      : item.type === "feedback" ? feedbackHtml(item) : payloadHtml(item);
  const submitted = new Date(item.submitted_at);
  return `<article class="mod-card" id="submission-${item.id}" data-id="${item.id}" aria-labelledby="submission-${item.id}-title">
    <header class="mod-card__head">
      <h2 class="mod-card__title" id="submission-${item.id}-title">${esc(typeLabel(item))}</h2>
      <p class="mod-card__when muted"><span>#${item.id}</span> · <time datetime="${esc(item.submitted_at)}" title="${esc(submitted.toLocaleString("en-US"))}">${relativeTime(item.submitted_at, now)}</time></p>
    </header>
    ${body}
    ${contextHtml(item)}
    ${reviewedHtml(item)}
    ${decisionHtml(item)}
  </article>`;
}

/**
 * The type filter's chips: all types, then every type with something pending
 * (scores and feedback always), plus whichever is chosen. Counts are pending ones.
 */
export function typeFilters(counts, chosen) {
  const types = new Set([...Object.keys(counts ?? {}).filter((t) => counts[t] > 0), "score", "feedback"]);
  if (chosen) types.add(chosen);
  const total = Object.values(counts ?? {}).reduce((a, b) => a + b, 0);
  return [
    { value: "", label: "All types", count: total },
    ...[...types].sort((a, b) => typeName(a).localeCompare(typeName(b)))
      .map((t) => ({ value: t, label: typeName(t), count: counts?.[t] ?? 0 })),
  ];
}
