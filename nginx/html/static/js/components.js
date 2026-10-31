// Reusable view components. Each returns an HTML string, so they render
// identically in the browser and under `node --test`.

import {
  escapeHtml as esc, formatPct, oddsBucket, initials, teamUiColors, teamRawColors, isPale, marginText, isCertain,
} from "./format.js";
import { playoffStatus } from "./standings.js";

// ----------------------------------------------------------------- icons
// Icons appear only where they carry meaning (brief §2.1).

const ICONS = {
  check: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>',
  cross: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>',
  bulb: '<svg class="outcome__explain-icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 11.5h4M6.5 14h3"/><path d="M6 11.5c0-1.6-2.5-2.8-2.5-5.5a4.5 4.5 0 0 1 9 0c0 2.7-2.5 3.9-2.5 5.5"/></svg>',
  coin: '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3.2"/></svg>',
  // Odds-mode glyphs: the mode is never told apart by color (brief §3.4).
  trend: '<svg class="mode__glyph" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12l4-4 3 3 5-6"/><path d="M10 5h4v4"/></svg>',
  dice: '<svg class="mode__glyph" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2.5" y="2.5" width="11" height="11" rx="2.5"/><circle cx="5.8" cy="5.8" r=".9" fill="currentColor" stroke="none"/><circle cx="10.2" cy="10.2" r=".9" fill="currentColor" stroke="none"/><circle cx="10.2" cy="5.8" r=".9" fill="currentColor" stroke="none"/><circle cx="5.8" cy="10.2" r=".9" fill="currentColor" stroke="none"/></svg>',
  chevron: '<svg class="row-toggle__chev" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5l4.5 4.5L6 12.5"/></svg>',
};

// ------------------------------------------------------------- odds cell

/** Odds cell: ramp background, honest-rounded percentage. */
export function oddsCell(p) {
  return `<span class="odds odds--${oddsBucket(p)}">${esc(formatPct(p))}</span>`;
}

// ------------------------------------------------------- provenance line

export const ODDS_MODES = {
  projected: { label: "Projected", glyph: ICONS.trend },
  tossup: { label: "Toss-up", glyph: ICONS.dice },
};

/** The odds-mode segment: trend glyph for Projected, dice + italic for Toss-up. */
export function modeLabel(mode) {
  const m = ODDS_MODES[mode];
  return m ? `<span class="mode mode--${mode}">${m.glyph}${m.label}</span>` : "";
}

/**
 * The odds mode over a table's odds columns ("Projected odds"), so a table
 * cropped from the page still says which odds it shows. Screen readers get
 * the mode from the caption's own words.
 */
export function tableMode(mode) {
  return ODDS_MODES[mode] ? `<span class="table-mode" aria-hidden="true">${modeLabel(mode)} odds</span>` : "";
}

/**
 * What the reader is looking at. Each segment owns its leading separator so
 * an omitted segment never leaves an orphaned dot.
 *   { label: "Week 9", date: "2025-10-24" }  -> "Through Week 9 · Oct 24"
 *   { ..., mode: "projected" }               -> "... · Projected" (trend glyph)
 *   { live: true, label: "Week 9" }          -> "● LIVE · Week 9"
 */
export function provenance({ label, date, live = false, mode = null } = {}, formatDate = (d) => d) {
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
  if (mode && ODDS_MODES[mode]) segments.push(modeLabel(mode));
  if (!segments.length) return "";
  const body = segments.map((s, i) => (i === 0 ? s : `<span aria-hidden="true"> · </span>${s}`)).join("");
  return `<p class="provenance">${body}</p>`;
}

// --------------------------------------------------------- status badge

/**
 * Every status that applies to a standings row, most important first: the
 * clinch (the specific seed when locked) or elimination, then a coin flip,
 * which can sit alongside a clinch. The coin flip shows only once region play
 * is complete: before that, possible coin-flip ties are everywhere and almost
 * always get settled on the field.
 *
 * Once a playoff team has played in the bracket (`clazz` given), its run
 * replaces the clinch: "Advanced to Semifinals", "Lost in First Round",
 * "State Champion". Teams that missed the playoffs stay "Eliminated".
 */
export function teamStatuses(entry, { regionComplete = false, clazz = null } = {}) {
  if (!entry) return [];
  const statuses = [];
  const o = entry.odds ?? {};
  const seed = [1, 2, 3, 4].find((s) => isCertain(o[`p${s}`]));
  const run = clazz ? playoffStatus(entry, clazz) : null;
  if (run) statuses.push({ kind: run.kind === "lost" ? "eliminated" : run.kind === "champion" ? "champion" : "clinched", label: run.label });
  else if (entry.eliminated) statuses.push({ kind: "eliminated", label: "Eliminated" });
  else if (seed) statuses.push({ kind: "clinched", label: `Clinched #${seed}` });
  else if (entry.clinched) statuses.push({ kind: "clinched", label: "Clinched" });
  if (regionComplete && entry.coin_flip_needed) statuses.push({ kind: "coinflip", label: "Coin flip" });
  return statuses;
}

const BADGE_ICONS = { clinched: ICONS.check, champion: ICONS.check, eliminated: ICONS.cross, coinflip: ICONS.coin };

export function statusBadges(entry, options) {
  return teamStatuses(entry, options)
    .map((st) => `<span class="badge badge--${st.kind}">${BADGE_ICONS[st.kind]}${esc(st.label)}</span>`)
    .join("");
}

/** A small "i" button that opens an inline note (never hover-only). */
export function infoButton(controls, label) {
  return `<button type="button" class="info-button" aria-expanded="false" aria-controls="${esc(controls)}">`
    + '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6.5"/><path d="M8 7.2v4" stroke-linecap="round"/><circle cx="8" cy="4.9" r=".9" fill="currentColor" stroke="none"/></svg>'
    + `<span class="visually-hidden">${esc(label)}</span></button>`;
}

// ---------------------------------------------------------- team identity

/**
 * A generic side-view helmet in the team's own colors: shell in the primary,
 * crown stripe in the first secondary, grey facemask. Faces right, toward
 * the team name. Team colors are artwork here, so they're not clamped; a
 * white keyline keeps dark shells visible in dark mode, and pale shells get
 * a grey one in light mode.
 */
export function genericHelmet({ shell, stripe }, size = 24) {
  const pale = isPale(shell) ? " mark--pale" : "";
  return `<svg class="mark mark--generic${pale}" viewBox="0 0 32 28" width="${size}" height="${size}" aria-hidden="true">`
    + '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M20 13H30.2V22.4H21.6M19.6 17.8H30.2M25 13V22.4" stroke="#8C8C8C" stroke-width="1.7"/>'
    + `<path class="helmet__shell" d="M2.5 16.2C2.5 8.2 8.8 2.6 16.4 2.6C22.4 2.6 26.6 6.2 27.8 11.3L20.2 12.2L19.2 19.4L21.4 22.9C18.8 25.2 14.6 26 10.6 25.2C5.6 24.2 2.5 20.9 2.5 16.2Z" fill="${esc(shell)}" stroke-width="1.5" paint-order="stroke"/>`
    + `<path d="M5.2 11.8C7.2 7.4 11 5 15.6 4.6" stroke="${esc(stripe)}" stroke-width="1.8"/>`
    + '<circle cx="12.4" cy="16.4" r="1.6" fill="#8C8C8C"/>'
    + "</g></svg>";
}

/**
 * The state championship trophy, after the MHSAA's own: a gold football on
 * end (laces at the top, a seam down the middle) on a gold cup, on a wooden
 * base with a black plaque. Its colors are the trophy's, the same in both
 * themes. Decorative: the words beside it say what it means. *size* is its
 * height in px. static_pages.py's TROPHY_SHAPES draws the same shapes, and
 * bracket_image.py traces them for the share images.
 */
export function trophyIcon(size = 56) {
  return `<svg class="trophy" viewBox="0 0 40 56" width="${Math.round(size * 4000 / 56) / 100}" height="${size}" aria-hidden="true">${TROPHY_SHAPES}</svg>`;
}
export const TROPHY_SHAPES = '<rect x="5.5" y="50" width="29" height="4.5" rx="1" fill="#6B4426"/>'
  + '<rect x="8" y="40.5" width="24" height="10.5" rx="1" fill="#8A5A33"/>'
  + '<rect x="10.5" y="42.6" width="19" height="6.6" rx="0.6" fill="#1F1F1F"/>'
  + '<path d="M15 44.6H25M13.5 46H26.5M16 47.4H24" stroke="#C9A33A" stroke-width="0.7" stroke-linecap="round"/>'
  + '<path d="M12.5 40.5C13.5 37.6 16.6 36.8 18.4 36.6H21.6C23.4 36.8 26.5 37.6 27.5 40.5Z" fill="#C8961C"/>'
  + '<rect x="18.3" y="31" width="3.4" height="6" fill="#C8961C"/>'
  + '<path d="M15 27.6H25L23 31.4H17Z" fill="#D9A520"/>'
  + '<ellipse cx="20" cy="28" rx="5" ry="1" fill="#A87A12"/>'
  + '<ellipse cx="20" cy="15" rx="11" ry="13.6" fill="#D9A520"/>'
  + '<path d="M12.6 8.5C11.4 11.6 11.2 16.4 12.4 20.4" stroke="#F3D27A" stroke-width="1.6" stroke-linecap="round" fill="none"/>'
  + '<path d="M20 2.6V27.4" stroke="#A87A12" stroke-width="0.9" stroke-linecap="round"/>'
  + '<path d="M18.2 5.4H21.8M18 7.6H22M18 9.8H22M18.2 12H21.8" stroke="#A87A12" stroke-width="1.2" stroke-linecap="round"/>';

/**
 * Where a season's championship games are played, from the API's
 * /championships location: "Davis Wade Stadium • Starkville" (every venue is
 * in Mississippi, so the state is left off); in a sentence (*sep* " in "),
 * "Davis Wade Stadium in Starkville". Null when none is on record.
 * static_pages.venue_name() is the same.
 */
export function venueName(venue, sep = " • ") {
  if (!venue?.name) return null;
  const city = String(venue.city ?? "").replace(/,\s*MS$/i, "").trim();
  return city ? `${venue.name}${sep}${city}` : venue.name;
}

/** "Projected champion" with a small trophy, over "Winona · 22%"; *champ* is projectedChampion()'s. */
export function championLine(champ) {
  return `<p class="champ-line"><span class="champ-line__label">${trophyIcon(18)}Projected champion:</span> `
    + `<span class="champ-line__team"><strong>${esc(champ.team)}</strong> · ${esc(formatPct(champ.p))}</span></p>`;
}

/**
 * Under the championship game's card in the bracket: where it's played, and
 * while it's still to play in Projected odds, the projected champion (*champ*,
 * or null). "" when there's neither. static_pages.final_note() is the same.
 */
export function finalNote(venue, champ) {
  const where = venueName(venue);
  const parts = `${where ? `<p class="tfinal__venue">${esc(where)}</p>` : ""}${champ ? championLine(champ) : ""}`;
  return parts ? `<div class="tfinal">${parts}</div>` : "";
}

/**
 * A finished season's champion, over its bracket: the trophy, "2025 Class 3A
 * State Champion", the team, and the championship game's result and venue.
 * *result* is layoutResults()'s for the final ({ winner, loser, winnerScore,
 * loserScore }); *venue* the season's championship venue, or null.
 * static_pages.py's champion_banner() writes the same.
 */
export function championBanner(season, clazz, result, teams, venue = null) {
  const score = result.winnerScore != null && result.loserScore != null ? ` ${result.winnerScore}–${result.loserScore}` : "";
  const where = venueName(venue, " in ");
  const beat = result.loser ? `<p class="champion__game">Beat ${esc(result.loser)}${score} in the Championship Game${where ? ` at ${esc(where)}` : ""}</p>` : "";
  return `<section class="champion" aria-label="State champion">${trophyIcon(56)}`
    + `<div class="champion__text"><p class="champion__label">${esc(String(season))} Class ${esc(String(clazz))}A State Champion</p>`
    + `<p class="champion__team">${teamLabel(result.winner, teams)}</p>${beat}</div></section>`;
}

/**
 * Helmet image when one exists, else a generic helmet in the team's colors,
 * else initials in a neutral squircle. Always decorative (alt="") because
 * it's never shown without the team name beside it.
 */
export function teamMark(name, team, { size = 24 } = {}) {
  const lg = size >= 48 ? " mark--lg" : "";
  if (team?.helmet_url) {
    return `<img class="mark mark--helmet${lg}" src="${esc(team.helmet_url)}" alt="" width="${size}" height="${size}" loading="lazy">`;
  }
  const colors = teamRawColors(team);
  if (colors) return genericHelmet(colors, size);
  return `<span class="mark mark--initials${lg}" aria-hidden="true">${esc(initials(name))}</span>`;
}

/** Inline style carrying a team's clamped UI color for both themes. */
export function teamColorStyle(team) {
  const colors = teamUiColors(team);
  // Escaped even though the colors are computed server-side: an attribute is no place to trust data.
  return colors ? ` style="--team-ui-light:${esc(colors.light)};--team-ui-dark:${esc(colors.dark)}"` : "";
}

/**
 * Breadcrumbs: where this page sits (Home › Class 7A › Region 2-7A). *trail*
 * is [[label, href], …]; the last entry is this page, shown but not linked.
 * static_pages.py's breadcrumb_nav() writes the same markup.
 */
export function breadcrumbs(trail) {
  const items = trail.map(([label, href], i) => (i === trail.length - 1
    ? `<li aria-current="page">${esc(label)}</li>`
    : `<li><a href="${esc(href)}">${esc(label)}</a></li>`));
  return `<nav class="crumbs" aria-label="Breadcrumb"><ol>${items.join("")}</ol></nav>`;
}

/** Helmet + name: how a team is usually shown. */
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
  if (cond.type === "playoff_win") {
    // "wins its First Round game vs the Region 2 #2 Seed", "wins its Quarterfinal game vs Neshoba Central"
    const vs = cond.opponent ? ` vs ${cond.byPosition ? "the " : ""}${cond.opponent}` : "";
    return `<span class="chip">${teamMark(cond.school, teams?.[cond.school])}<span><span class="chip__subject">${esc(cond.school)}</span> wins its ${esc(cond.round.replace(/s$/, ""))} game${esc(vs)}</span></span>`;
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

/**
 * Requirements that must all hold (scenarios.js's `allOf`): their shared
 * conditions, then each set of alternatives in a box headed "AND ONE OF"
 * ("ONE OF" when nothing comes before it). A lone set of alternatives needs
 * no box.
 */
export function allOfConditions({ common, alternatives }, teams) {
  if (!common.length && alternatives.length === 1) return conditionGroups(alternatives[0], teams);
  let html = common.length ? conditionGroups([common], teams) : "";
  for (const ways of alternatives) {
    const label = html ? "AND ONE OF" : "ONE OF";
    html += `<div class="oneof${label === "ONE OF" ? " oneof--first" : ""}" role="group" aria-label="${label === "ONE OF" ? "One of" : "And one of"}">`
      + `<span class="oneof__label" aria-hidden="true">${label}</span>${conditionGroups(ways, teams)}</div>`;
  }
  return html;
}

/**
 * Conditions in the order they happen: `regular` (scenarios.js's `allOf` of
 * the regular-season requirements: a seed's results, or two teams'), then
 * `after`, which must all hold too (playoff games, in order). Shared results
 * first, each set of alternatives in its own box ("ONE OF", then "AND ONE
 * OF"), then an AND down to the games. Nothing before the games leaves just
 * the games.
 */
export function conditionsThen(regular, after, teams) {
  const { common, alternatives } = regular;
  if (!alternatives.length) return common.length || after.length ? conditionGroups([[...common, ...after]], teams) : "";
  let html = common.length ? conditionGroups([common], teams) : "";
  for (const ways of alternatives) {
    const first = !html;
    html += `<div class="oneof${first ? " oneof--first" : ""}" role="group" aria-label="${first ? "One of" : "And one of"}">`
      + `<span class="oneof__label" aria-hidden="true">${first ? "ONE OF" : "AND ONE OF"}</span>${conditionGroups(ways, teams)}</div>`;
  }
  return after.length ? `${html}<div class="and"><span>AND</span></div>${conditionGroups([after], teams)}` : html;
}

// -------------------------------------------------------- scenario card

/** An outcome card; `level` is its heading's level, one below the heading it sits under. */
export function scenarioCard({ title, p = null, groups, provenanceHtml = "", team = null, teams, level = 4 }) {
  const odds = p == null ? "" : oddsCell(p);
  return `<article class="scenario"${teamColorStyle(team)}>
    <div class="scenario__head"><h${level} class="scenario__title">${esc(title)}\u00a0<span class="scenario__if">IF</span></h${level}>${odds}</div>
    ${provenanceHtml}
    <div class="scenario__body">${conditionGroups(groups, teams)}</div>
  </article>`;
}

// ------------------------------------------------------------- game card

/** A game card's report links: "Wrong date?", and "Wrong score?" or "Report score" (see gameCard). */
function reportButtons(game, label, played, today) {
  if (!game.date) return "";
  const at = `data-date="${esc(game.date)}" data-away="${esc(game.away)}" data-home="${esc(game.home)}" data-joiner="${esc(game.joiner)}"`;
  const buttons = [`<button type="button" class="game-card__report" data-date-report ${at}>Wrong date?<span class="visually-hidden"> Report the right date for ${esc(label)}</span></button>`];
  if (played) {
    buttons.push(`<button type="button" class="game-card__report" data-score-report ${at} data-away-score="${esc(game.awayScore)}" data-home-score="${esc(game.homeScore)}">Wrong score?<span class="visually-hidden"> Report a correction for ${esc(label)}</span></button>`);
  } else if (today && game.date <= today) {
    buttons.push(`<button type="button" class="game-card__report" data-score-report ${at}>Report score<span class="visually-hidden"> for ${esc(label)}</span></button>`);
  }
  return `<div class="game-card__reports">${buttons.join("")}</div>`;
}

/**
 * One region game: the visitor on top with "at" (or "vs" at a neutral
 * site), the home team below. Finished games add each side's score and
 * bold the winner. `game` is { date?, away, home, joiner, awayScore?,
 * homeScore?, winner? }; `focus` outlines the card when the picked team
 * plays in it. With `report`, a game with a date offers "Wrong date?"; a
 * finished game also offers "Wrong score?", and a game without a score whose
 * date is `today` (ISO) or earlier "Report score".
 */
export function gameCard(game, teams, { focus = null, report = false, today = null } = {}) {
  const played = game.awayScore != null && game.homeScore != null;
  const side = (name, score) => {
    const won = played && game.winner === name;
    return `<span class="game-card__team${won ? " is-winner" : ""}">${teamLabel(name, teams)}`
      + `${played ? `<span class="game-card__score">${esc(score)}</span>` : ""}</span>`;
  };
  const mine = focus && (game.away === focus || game.home === focus);
  const label = played
    ? `${game.away} ${game.awayScore}, ${game.home} ${game.homeScore}`
    : `${game.away} ${game.joiner} ${game.home}`;
  return `<li class="game-card${mine ? " is-focus" : ""}">
    <span class="visually-hidden">${esc(label)}</span>
    <div class="game-card__row" aria-hidden="true">${side(game.away, game.awayScore)}<span class="game-card__joiner">${esc(game.joiner)}</span></div>
    <div class="game-card__row" aria-hidden="true">${side(game.home, game.homeScore)}</div>
    ${report ? reportButtons(game, label, played, today) : ""}
  </li>`;
}

// ---------------------------------------------------- complete scenario

/**
 * One complete scenario: its label (and its chance, when given), the seeds it
 * produces (and who misses out), then the results that produce it. `focus`
 * highlights the picked team's line; `provenanceHtml` goes under the head
 * with the chance, so a cropped card still says what it shows. `level` is
 * its heading's level, one below the heading it sits under.
 */
export function outcomeScenarioCard({ label, seeds, out, groups, common = [], why = [] }, teams, { focus = null, p = null, provenanceHtml = "", explainId = null, level = 4 } = {}) {
  // A tie left to the tiebreaker is one row over its places: its teams, unordered, and what decides it.
  const seedRows = seeds.map(({ seed, team, teams: tied, note }) => (tied
    ? `<li class="outcome__tie${tied.includes(focus) ? " is-focus" : ""}"><span class="outcome__seed">${esc(seed)}</span>`
      + `<span class="outcome__tie-body"><span class="outcome__tie-teams">${tied.map((t) => teamLabel(t, teams)).join("")}</span>`
      + `<span class="outcome__tie-note">${esc(note)}</span></span></li>`
    : `<li${team === focus ? ' class="is-focus"' : ""}><span class="outcome__seed">${seed}</span>${teamLabel(team, teams)}</li>`));
  const outLine = out.length
    ? `<p class="outcome__out"><span class="outcome__out-label">Out</span> ${out.map((t) => (t === focus ? `<strong>${esc(t)}</strong>` : esc(t))).join(", ")}</p>`
    : "";
  // Shared conditions once, then the alternatives in a box headed "AND ONE OF", so it's clear where
  // they end.
  const alternatives = common.length
    ? `${conditionGroups([common], teams)}<div class="oneof" role="group" aria-label="And one of">`
      + `<span class="oneof__label" aria-hidden="true">AND ONE OF</span>${conditionGroups(groups, teams)}</div>`
    : conditionGroups(groups, teams);
  const body = groups.length || common.length
    ? `<p class="outcome__if">IF</p><div class="scenario__body">${alternatives}</div>`
    : "";
  const title = `<h${level} class="scenario__title">${esc(label)}</h${level}>`;
  const head = p == null ? title : `<div class="scenario__head">${title}${oddsCell(p)}</div>${provenanceHtml}`;
  return `<article class="scenario outcome">
    ${head}
    <ol class="outcome__seeds" aria-label="Seeds">${seedRows.join("")}</ol>
    ${outLine}
    ${body}
    ${why.length && explainId != null ? explainButton(explainId, label) : ""}
  </article>`;
}

/** The card's button to its explanation sheet (the app opens it by `data-explain-open`). */
function explainButton(id, label) {
  return `<button type="button" class="outcome__explain" data-explain-open="${esc(id)}" aria-haspopup="dialog">`
    + `${ICONS.bulb}Explanation<span class="visually-hidden"> of ${esc(label)}</span></button>`;
}

/**
 * A scenario's ties, explained: for each tie reaching the playoff places,
 * its teams and places, the results it holds for when it doesn't hold for
 * all of them, and one numbered sentence per tiebreaker step.
 */
export function whyTies(why) {
  return why.map((w) => `<div class="why-tie">
      <h4 class="why-tie__title">${esc(w.title)}</h4>
      ${w.when ? `<p class="why-tie__when">${esc(w.when)}:</p>` : ""}
      <ol class="tiebreak__steps">${w.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    </div>`).join("");
}

// -------------------------------------------------------- class scrubber

/**
 * The class row: one link per class (each its own page), styled as a
 * segmented control. The current class is marked aria-current.
 */
export function classScrubber(classes, selected, hrefFor = (c) => `/standings/${c}a`) {
  const items = classes.map((c) => {
    const current = c === selected ? ' aria-current="page"' : "";
    return `<a class="scrubber__item" href="${esc(hrefFor(c))}" data-class="${c}"${current}>${c}A</a>`;
  });
  return `<nav class="scrubber" aria-label="Classification">${items.join("")}</nav>`;
}

export const chevronIcon = ICONS.chevron;
