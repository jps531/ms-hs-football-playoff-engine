// Reusable view components. Each returns an HTML string, so they render
// identically in the browser and under `node --test`.

import {
  escapeHtml as esc, formatPct, oddsBucket, initials, inkFor, teamUiColors, marginText, isCertain,
} from "./format.js";

// ----------------------------------------------------------------- icons
// Icons appear only where they carry meaning (brief §2.1).

const ICONS = {
  check: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>',
  cross: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>',
  coin: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3.2"/></svg>',
  chevron: '<svg class="row-toggle__chev" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5l4.5 4.5L6 12.5"/></svg>',
};

// ------------------------------------------------------------- odds cell

/** Odds cell: ramp background, honest-rounded percentage. */
export function oddsCell(p) {
  return `<span class="odds odds--${oddsBucket(p)}">${esc(formatPct(p))}</span>`;
}

// ------------------------------------------------------- provenance line

/**
 * What the reader is looking at. Each segment owns its leading separator so
 * an omitted segment never leaves an orphaned dot.
 *   { label: "Week 9", date: "2025-10-24" }  -> "Through Week 9 · Oct 24"
 *   { live: true, label: "Week 9" }          -> "● LIVE · Week 9"
 */
export function provenance({ label, date, live = false } = {}, formatDate = (d) => d) {
  const segments = [];
  if (live) {
    segments.push('<span class="provenance__live"><span class="provenance__pulse" aria-hidden="true"></span>LIVE</span>');
    if (label) segments.push(esc(label));
  } else if (label) {
    segments.push(`Through ${esc(label)}`);
    if (date) segments.push(esc(formatDate(date)));
  } else if (date) {
    segments.push(`Updated ${esc(formatDate(date))}`);
  }
  if (!segments.length) return "";
  const body = segments.map((s, i) => (i === 0 ? s : `<span aria-hidden="true"> · </span>${s}`)).join("");
  return `<p class="provenance">${body}</p>`;
}

// --------------------------------------------------------- status badge

/** The single highest status for a standings row, or null. */
export function teamStatus(entry) {
  if (!entry) return null;
  if (entry.eliminated) return { kind: "eliminated", label: "Eliminated" };
  const o = entry.odds ?? {};
  for (const seed of [1, 2, 3, 4]) {
    if (isCertain(o[`p${seed}`])) return { kind: "clinched", label: `Clinched #${seed}` };
  }
  if (entry.coin_flip_needed) return { kind: "coinflip", label: "Coin flip" };
  if (entry.clinched) return { kind: "clinched", label: "Clinched" };
  return null;
}

export function statusBadge(entry) {
  const status = teamStatus(entry);
  if (!status) return "";
  const icon = { clinched: ICONS.check, eliminated: ICONS.cross, coinflip: ICONS.coin }[status.kind];
  return `<span class="badge badge--${status.kind}">${icon}${esc(status.label)}</span>`;
}

// ---------------------------------------------------------- team identity

/**
 * Helmet, else logo, else initials on the team color. Always decorative
 * (alt="") because it's never shown without the team name beside it.
 */
export function teamMark(name, team, { size = 24 } = {}) {
  const lg = size >= 48 ? " mark--lg" : "";
  if (team?.helmet_url) {
    return `<img class="mark mark--helmet${lg}" src="${esc(team.helmet_url)}" alt="" width="${size}" height="${size}" loading="lazy">`;
  }
  if (team?.logo_primary) {
    return `<img class="mark mark--logo${lg}" src="${esc(team.logo_primary)}" alt="" width="${size}" height="${size}" loading="lazy">`;
  }
  const colors = teamUiColors(team);
  const style = colors
    ? ` style="--team-light:${colors.light};--team-dark:${colors.dark};--team-ink-light:${inkFor(colors.light)};--team-ink-dark:${inkFor(colors.dark)}"`
    : "";
  return `<span class="mark mark--initials${lg}"${style} aria-hidden="true">${esc(initials(name))}</span>`;
}

/** Inline style carrying a team's clamped UI color for both themes. */
export function teamColorStyle(team) {
  const colors = teamUiColors(team);
  return colors ? ` style="--team-ui-light:${colors.light};--team-ui-dark:${colors.dark}"` : "";
}

/** Helmet + name: the only way a team is ever identified. */
export function teamLabel(name, teams) {
  return `<span class="team">${teamMark(name, teams?.[name])}<span class="team-name">${esc(name)}</span></span>`;
}

// ---------------------------------------------------- condition chips

/** One condition as a chip: helmet, subject team, and what has to happen. */
export function conditionChip(cond, teams) {
  if (cond.type === "game_result") {
    const subject = cond.school;
    const verb = cond.required_result === "loss" ? "loses to" : "beats";
    return `<span class="chip">${teamMark(subject, teams?.[subject])}<span><span class="chip__subject">${esc(subject)}</span> ${verb} ${esc(cond.opponent)}${esc(marginText(cond.min_margin, cond.max_margin))}</span></span>`;
  }
  if (cond.type === "coin_flip") {
    return `<span class="chip chip--text">${ICONS.coin}<span>${esc(cond.description)}</span></span>`;
  }
  return `<span class="chip chip--text"><span>${esc(cond.description ?? "")}</span></span>`;
}

/**
 * OR-of-AND condition groups. AND links chips with a short vertical
 * connector; alternatives are split by a full-width rule with an inverted OR
 * pill. The grammar is explicit text, never position alone, so it survives
 * wrapping on narrow screens.
 */
export function conditionGroups(groups, teams) {
  const rendered = groups.filter((g) => g.length).map((group) => {
    const chips = group.map((c) => conditionChip(c, teams));
    return `<div class="cond-group">${chips.join('<div class="and"><span>AND</span></div>')}</div>`;
  });
  return `<div class="conditions">${rendered.join('<div class="or"><span>OR</span></div>')}</div>`;
}

// -------------------------------------------------------- scenario card

export function scenarioCard({ title, p = null, groups, provenanceHtml = "", team = null, teams }) {
  const odds = p == null ? "" : oddsCell(p);
  return `<article class="scenario"${teamColorStyle(team)}>
    <div class="scenario__head"><h4 class="scenario__title">${esc(title)}</h4>${odds}</div>
    ${provenanceHtml}
    <div class="scenario__body">${conditionGroups(groups, teams)}</div>
  </article>`;
}

// -------------------------------------------------------- class scrubber

/**
 * Segmented control over the ordered class scale. A radiogroup with a roving
 * tabindex: one tab stop, arrow keys move between (and select) classes.
 */
export function classScrubber(classes, selected) {
  const active = classes.includes(selected) ? selected : classes[0];
  const items = classes.map((c) => {
    const on = c === selected;
    return `<button type="button" class="scrubber__item" role="radio" aria-checked="${on}" tabindex="${c === active ? 0 : -1}" data-class="${c}">${c}A</button>`;
  });
  return `<div class="scrubber" role="radiogroup" aria-label="Classification">${items.join("")}</div>`;
}

export const chevronIcon = ICONS.chevron;
