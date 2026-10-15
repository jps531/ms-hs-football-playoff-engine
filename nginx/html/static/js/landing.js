// The front page ("/"): every region race in the state, one compact row per
// region, from /standings/summary. backend/helpers/static_pages.py's
// landing_body renders the same markup from the same data for the static
// copy nginx serves first, so the page doesn't change when the app loads.
// Keep the two in step.

import { escapeHtml as esc, joinNames, recordText, shortDate } from "./format.js";

export const LANDING_TITLE = "Mississippi high school football playoff races";

/** Who leads a region: everyone tied with the leader on region record, or a note before any region games. */
export function leaders(card) {
  const statuses = card.statuses ?? [];
  const top = statuses[0]?.record;
  if (!top || top.region_wins + top.region_losses + (top.region_ties ?? 0) === 0) return null;
  const tied = statuses.filter((s) => s.record.region_wins === top.region_wins
    && s.record.region_losses === top.region_losses
    && (s.record.region_ties ?? 0) === (top.region_ties ?? 0));
  const names = tied.map((s) => s.school);
  return {
    names: names.length > 3 ? `${names.length} teams` : joinNames(names),
    record: recordText(top.region_wins, top.region_losses, top.region_ties ?? 0),
  };
}

function regionRow(clazz, card) {
  const lead = leaders(card);
  const leading = lead
    ? `${esc(lead.names)} <span class="muted">${esc(lead.record)}</span>`
    : '<span class="muted">No region games yet</span>';
  return `<tr><th scope="row" class="col-region"><a href="/standings/${clazz}a/${card.region}">Region ${card.region}</a></th>`
    + `<td class="col-leading">${leading}</td>`
    + `<td class="col-num">${card.num_clinched}</td><td class="col-num">${card.teams_alive}</td><td class="col-num">${card.num_eliminated}</td></tr>`;
}

function classBlock(block) {
  const c = block.class_;
  const rows = [...block.regions].sort((a, b) => a.region - b.region).map((card) => regionRow(c, card)).join("");
  return `<section class="landing-class" aria-labelledby="class-${c}">`
    + `<h2 class="landing-class__title" id="class-${c}"><a href="/standings/${c}a">Class ${c}A</a>`
    + `<a class="landing-class__bracket" href="/brackets/${c}a">${c}A Bracket</a></h2>`
    + '<table class="standings standings--compact landing-table">'
    + `<caption class="visually-hidden">Class ${c}A regions: who leads, and how many teams have clinched a playoff spot, are still undecided, or are out</caption>`
    + '<thead><tr><th scope="col" class="col-region">Region</th><th scope="col" class="col-leading">Leading</th>'
    + '<th scope="col" class="col-num">Clinched</th><th scope="col" class="col-num">Undecided</th><th scope="col" class="col-num">Out</th></tr></thead>'
    + `<tbody>${rows}</tbody></table></section>`;
}

/** The whole front page for a /standings/summary response. */
export function landingHtml(summary, season) {
  const classes = [...(summary.classes ?? [])].sort((a, b) => a.class_ - b.class_);
  return '<div class="page landing">'
    + '<header class="entry-head">'
    + `<h1 class="title">${LANDING_TITLE}</h1>`
    + '<p class="prose">Every MHSAA region race: who’s in, who’s out, and exactly what has to happen next. Pick a region to see its odds and scenarios.</p>'
    + `<p class="provenance provenance--static">${season} season · Updated ${esc(shortDate(summary.as_of_date))}</p>`
    + '<p class="landing-key muted"><strong>Clinched</strong>: sure of a playoff spot. <strong>Undecided</strong>: could still make or miss the playoffs. <strong>Out</strong>: eliminated.</p>'
    + '</header>'
    + classes.map(classBlock).join("")
    + "</div>\n";
}
