// The front page ("/"): what the site does, links into each part of it, and
// one live region race to show it working. backend/helpers/static_pages.py's
// landing_body renders the same markup from the same data for the static
// copy nginx serves first, so nothing changes when the app loads (a test
// compares the two byte for byte). Keep the two in step.

import { escapeHtml as esc, shortDate } from "./format.js";
import { oddsCell } from "./components.js";
import { hasProjectedOdds, oddsFor } from "./scenarios.js";
import { displayOrder, standingPositions } from "./standings.js";

const CLASSES = [1, 2, 3, 4, 5, 6, 7];

/**
 * The race to feature: the region with the most teams still undecided, then
 * the more volatile race, then the higher class. null when no region has an
 * undecided team (the regular season is over).
 */
export function pickFeatured(summary) {
  const cards = (summary.classes ?? []).flatMap((c) => c.regions.map((card) => ({ clazz: c.class_, card })));
  const open = cards.filter(({ card }) => card.teams_alive > 0);
  open.sort((a, b) => b.card.teams_alive - a.card.teams_alive
    || b.card.volatility - a.card.volatility
    || b.clazz - a.clazz
    || a.card.region - b.card.region);
  return open[0] ?? null;
}

function chips(hrefFor, label) {
  return CLASSES.map((c) => `<a class="landing-chip" href="${hrefFor(c)}" aria-label="${label(c)}">${c}A</a>`).join("");
}

function featuredHtml(featured) {
  const { clazz, card, standings } = featured;
  const page = `/standings/${clazz}a/${card.region}`;
  const mode = hasProjectedOdds(standings.teams) ? "projected" : "tossup";
  const ordered = displayOrder(standings.teams);
  const positions = standingPositions(ordered);
  const rows = ordered.map((t, i) => {
    const r = t.record;
    const rec = r.region_ties ? `${r.region_wins}–${r.region_losses}–${r.region_ties}` : `${r.region_wins}–${r.region_losses}`;
    return `<tr class="${t.eliminated ? "is-eliminated" : ""}"><td class="col-pos">${positions[i]}</td>`
      + `<th scope="row" class="col-team"><span class="team-name">${esc(t.school)}</span></th>`
      + `<td class="col-rec">${rec}</td><td class="col-odds">${oddsCell(oddsFor(t, mode).p_playoffs)}</td></tr>`;
  }).join("");
  const modeName = mode === "projected" ? "Projected" : "Toss-up";
  return '<section class="landing-featured" aria-labelledby="featured-title">'
    + '<p class="landing-kicker">Race to watch</p>'
    + `<h2 class="landing-featured__title" id="featured-title"><a href="${page}">Region ${card.region}-${clazz}A</a></h2>`
    + (standings.headline ? `<p class="landing-featured__headline">${esc(standings.headline)}</p>` : "")
    + '<table class="standings standings--compact landing-table">'
    + `<caption class="visually-hidden">Region ${card.region}-${clazz}A standings and ${modeName.toLowerCase()} odds of making the playoffs</caption>`
    + '<thead><tr><th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th><th scope="col" class="col-team">Team</th>'
    + '<th scope="col" class="col-rec">Region</th><th scope="col" class="col-odds">Playoffs</th></tr></thead>'
    + `<tbody>${rows}</tbody></table>`
    + `<p class="landing-featured__meta muted">${card.num_clinched} clinched · ${card.teams_alive} undecided · ${card.num_eliminated} out`
    + ` · ${modeName} odds · Updated ${esc(shortDate(standings.as_of_date))}</p>`
    + `<p><a class="landing-button" href="${page}">See what has to happen</a></p>`
    + "</section>";
}

/** The whole front page; `featured` is { clazz, card, standings } or null. */
export function landingHtml(featured) {
  const example = featured ? `/standings/${featured.clazz}a/${featured.card.region}` : "/standings/1a";
  const exampleName = featured ? `Region ${featured.card.region}-${featured.clazz}A` : "Class 1A";
  return '<div class="page landing">'
    + '<section class="landing-hero">'
    + '<h1 class="title landing-hero__title">Every Mississippi high school football playoff race, worked out every possible way</h1>'
    + '<p class="landing-hero__lead">Standings, playoff odds, and exactly what each team needs to happen, for every MHSAA region. Updated every morning.</p>'
    + '<div class="landing-hero__actions">'
    + '<a class="landing-button" href="#team-search" data-focus-search>Find your team</a>'
    + `<nav class="landing-classes" aria-label="Standings by class"><span class="landing-classes__label">Standings by class</span>${chips((c) => `/standings/${c}a`, (c) => `Class ${c}A standings`)}</nav>`
    + "</div></section>"
    + (featured ? featuredHtml(featured) : "")
    + '<section class="landing-cards" aria-label="What’s here">'
    + '<article class="landing-card"><h2 class="landing-card__title">Standings and odds</h2>'
    + "<p>Every region’s standings, with each team’s chance of finishing first through fourth and of making the playoffs. "
    + "Projected odds weigh each game by team strength; Toss-up odds treat every game as a coin flip.</p>"
    + `<p><a href="${example}">See ${exampleName}</a></p></article>`
    + '<article class="landing-card"><h2 class="landing-card__title">What has to happen</h2>'
    + "<p>The exact results each team needs, checked against every MHSAA tiebreaker, down to the margin of victory when it matters: "
    + "“clinches the No. 2 seed with a win, no help needed.”</p>"
    + `<p><a href="${example}">See ${exampleName}</a></p></article>`
    + '<article class="landing-card"><h2 class="landing-card__title">Playoff brackets</h2>'
    + "<p>Each class’s bracket, filled in with who is likely to land in each spot, who each team might play, and where.</p>"
    + `<nav class="landing-classes" aria-label="Brackets by class">${chips((c) => `/brackets/${c}a`, (c) => `Class ${c}A bracket`)}</nav></article>`
    + "</section>"
    + '<p class="landing-sources">Scores from <a href="https://www.ahsfhs.org/">AHSFHS</a>. Seeding follows the MHSAA’s tiebreaker rules. '
    + 'Updated daily at 9:15 AM Central. <a href="/methodology">How it works</a></p>'
    + "</div>\n";
}
