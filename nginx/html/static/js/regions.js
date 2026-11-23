import { breadcrumbs, teamMark } from "./components.js";
import { escapeHtml as esc } from "./format.js";

// The Regions page (/maps/regions/5a), in the Maps section: a class's schools on a map of Mississippi, each a dot numbered by
// its region, every region's shape, and the schools listed by region. The data is written by the
// share-assets step (backend/prefect/share_regions.py) to /static/regions/: map.json (the state and
// its counties, projected to Mississippi Transverse Mercator, in 100 m units), index.json (the
// seasons) and {season}.json (that season's schools and region shapes). The region shapes are drawn
// around each region's schools (backend/helpers/region_map.py); MHSAA draws no boundaries.
//
// The markup functions here are pure, so they run under node; static_pages-style twins in
// backend/helpers/region_pages.py write the same page for search engines (renderer_parity_test.py).

export const REGIONS_DATA = "/static/regions";

// Room around the state in the map's whole view, as a share of its width and height (the same share
// both ways, so the view keeps the state's shape): region shapes reach past the state line.
const MARGIN = 0.04;

/** "/maps/regions/5a". */
export function regionsPath(clazz) {
  return `/maps/regions/${clazz}a`;
}

/** "Class 5A Regions". */
export function regionsTitle(clazz) {
  return `Class ${clazz}A Regions`;
}

/** "2027 and 2028 seasons", or "2026 season". */
export function seasonsLabel(seasons) {
  return `${seasons.join(" and ")} ${seasons.length > 1 ? "seasons" : "season"}`;
}

/** "Region 2-5A" (the site's {region}-{class}A). */
export function place(p) {
  return p ? `Region ${p.region}-${p.class}A` : "";
}

/** "2-5A". */
export function shortPlace(p) {
  return p ? `${p.region}-${p.class}A` : "";
}

/**
 * Where a school was the season before, for its line in the list: "4-4A in 2026", "New school";
 * nothing when it was in the same region then.
 */
export function teamNote(school, priorSeason) {
  if (priorSeason == null) return "";
  const was = school.before;
  if (was && was.class === school.class && was.region === school.region) return "";
  if (was) return `${shortPlace(was)} in ${priorSeason}`;
  if (school.successor_of) return "New school";
  return `Not in a region in ${priorSeason}`;
}

/** A team's line under the map once it's picked: "Region 2-5A · Moved up from Region 4-4A (2026)". */
export function teamChange(school, priorSeason) {
  if (priorSeason == null) return "";
  const was = school.before;
  if (!was) return school.successor_of ? `New school, on ${school.successor_of}’s campus` : `Not in a region in ${priorSeason}`;
  if (was.class !== school.class) return `Moved ${school.class > was.class ? "up" : "down"} from ${place(was)} (${priorSeason})`;
  if (was.region !== school.region) return `Moved from ${place(was)} (${priorSeason})`;
  return `Also ${place(was)} in ${priorSeason}`;
}

/**
 * Where a region's heading links: its standings in the newest of the choice's seasons that has
 * games, or nowhere while none has (the region has no standings yet).
 */
export function standingsHref(clazz, region, standingsSeason, currentSeason) {
  if (standingsSeason == null) return null;
  const path = `/standings/${clazz}a/${region}`;
  return standingsSeason === currentSeason ? path : `${path}?season=${standingsSeason}`;
}

/** Home › Class 5A (the class's standings, as on the bracket page) › Class 5A Regions. */
export function regionsTrail(clazz) {
  return [["Home", "/"], [`Class ${clazz}A`, `/standings/${clazz}a`], [regionsTitle(clazz), regionsPath(clazz)]];
}

/** The page's heading: breadcrumbs, the title (with *share*, its share button, beside it), and its seasons. */
export function regionsHeader(clazz, payload, share = "") {
  return `${breadcrumbs(regionsTrail(clazz))}<div class="title-row"><h1 class="title">${esc(regionsTitle(clazz))}</h1>${share}</div>`
    + `<p class="regions-sub">${esc(seasonsLabel(payload.seasons))}</p>`;
}

/** Schools by name, letter case aside, as Python's sorted(key=str.lower) puts them. */
const byName = (a, b) => {
  const [x, y] = [a.toLowerCase(), b.toLowerCase()];
  return x < y ? -1 : x > y ? 1 : 0;
};

/**
 * The class's schools by region, each a row with its helmet (*teams*: the season's /teams by school)
 * that picks it on the map, and where it was the season before when that differs. A region with
 * standings has a link to them beside its name ("2026 standings"); the name itself isn't a link.
 */
export function regionsLists(clazz, payload, currentSeason, teams = {}) {
  const schools = payload.schools.filter((s) => s.class === clazz);
  const regions = [...new Set(schools.map((s) => s.region))].sort((a, b) => a - b);
  return regions.map((g) => {
    const href = standingsHref(clazz, g, payload.standings_season, currentSeason);
    const standings = href
      ? `<a class="regions-list__standings" href="${esc(href)}"><span class="visually-hidden">Region ${g} </span>`
        + `${esc(payload.standings_season)} standings<span aria-hidden="true"> ›</span></a>`
      : "";
    const items = schools.filter((s) => s.region === g)
      .sort((a, b) => byName(a.school, b.school))
      .map((s) => {
        const note = teamNote(s, payload.prior_season);
        return `<li><a class="regions-list__row" href="${esc(regionsPath(clazz))}?team=${esc(s.slug)}" data-team="${esc(s.slug)}">`
          + `${teamMark(s.school, teams[s.school])}<span class="regions-list__team">${esc(s.school)}</span>`
          + (note ? `<span class="regions-list__was">${esc(note)}</span>` : "")
          + "</a></li>";
      });
    return `<section class="regions-list__region regions-list__region--${g}"><div class="regions-list__head">`
      + `<h2 class="regions-list__name"><span class="region-chip region-chip--${g}" aria-hidden="true">${g}</span>Region ${g}</h2>`
      + `${standings}</div><ul>${items.join("")}</ul></section>`;
  }).join("");
}

// ------------------------------------------------------------- the map

/** The SVG: land, the region shapes, county lines and names, the state's outline, then the dots. */
export function mapSvg(base, payload, clazz) {
  const counties = base.counties.map((c) => `<path class="map-county" d="${c.d}"/>`).join("");
  const names = base.counties.map((c) => `<text class="map-county-name" x="${c.label[0]}" y="${c.label[1]}">${esc(c.name)}</text>`).join("");
  const shapes = Object.entries(payload.regions[String(clazz)] ?? {})
    .map(([g, r]) => `<path class="map-region map-region--${g}" data-region="${g}" d="${r.d}"/>`).join("");
  const dots = payload.schools.filter((s) => s.class === clazz && s.x != null)
    .map((s) => `<g class="map-dot map-dot--${s.region}" data-team="${esc(s.slug)}" data-region="${s.region}" tabindex="-1">`
      + `<circle cx="${s.x}" cy="${s.y}" r="34"/><text x="${s.x}" y="${s.y}">${s.region}</text></g>`).join("");
  const v = wholeView(base);
  return `<svg class="regions-map__svg" viewBox="${v.x} ${v.y} ${v.w} ${v.h}" role="img" `
    + `aria-label="Map of Mississippi with each Class ${clazz}A school as a dot numbered by its region">`
    + `<path class="map-land" d="${base.state}"/><g class="map-regions">${shapes}</g>`
    + `<g class="map-counties">${counties}</g><g class="map-county-names">${names}</g>`
    + `<path class="map-state" d="${base.state}"/><g class="map-dots">${dots}</g></svg>`;
}

/**
 * One map with its buttons, under it, and the picked team's details: the map (with its zoom buttons,
 * tooltip and, with *full*, full screen) for the Map view and each side of Compare.
 */
export function mapFigure(base, payload, clazz, { full = true } = {}) {
  const button = (attr, label, icon) => `<button type="button" ${attr} aria-label="${label}" title="${label}">${icon}</button>`;
  return `<figure class="regions-map">`
    + `<div class="regions-map__frame" data-map>${mapSvg(base, payload, clazz)}`
    + `<div class="regions-map__hover" aria-hidden="true" hidden></div></div>`
    + `<div class="regions-map__tools"><div class="regions-map__zoom" role="group" aria-label="Zoom">`
    + `${button('data-zoom="in"', "Zoom in", MAP_ICONS.in)}${button('data-zoom="out"', "Zoom out", MAP_ICONS.out)}`
    + `${button('data-zoom="reset"', "Show the whole state", MAP_ICONS.reset)}</div>`
    + (full ? `<button type="button" class="regions-map__full" data-full aria-pressed="false">${MAP_ICONS.full}<span>Full screen</span></button>` : "")
    + `</div><p class="visually-hidden" aria-live="polite" data-picked-status></p>`
    + `<figcaption class="regions-map__picked" hidden></figcaption></figure>`;
}

/**
 * The views every map page has, as links in the bracket's half switch's style (.half-control): Season
 * (one season's map; the "map" view), Compare (two side by side) and Timeline (every season's, in
 * order). *view* is the one shown; *hrefs* is each one's address ({ map, compare, timeline }), keeping
 * the season and picked team.
 */
export function mapsViews(view, hrefs) {
  const views = [["map", "Season"], ["compare", "Compare"], ["timeline", "Timeline"]];
  return `<nav class="half-control maps-views" aria-label="View">`
    + views.map(([key, label]) => `<a class="half-control__item maps-views__item" href="${esc(hrefs[key])}"${key === view ? ' aria-current="page"' : ""}>${label}</a>`).join("")
    + "</nav>";
}

/** The whole page: heading and controls, the map (with its zoom buttons and tooltip), the lists. On a
 * computer the map is beside the heading and the lists; on a phone, between them. */
export function regionsPage(clazz, base, payload, currentSeason, { controls = "", share = "", teams = {}, views = "" } = {}) {
  return `<div class="page regions-page"><header class="entry-head">${regionsHeader(clazz, payload, share)}${views}${controls}`
    + `<p class="focus-note muted regions-note">Pick a team on the map or in the lists to see where it is and highlight its region.</p></header>`
    + `<div class="regions-layout">${mapFigure(base, payload, clazz)}`
    + `<div class="regions-side"><p class="focus-note muted regions-note regions-note--lists">Pick a team to see it on the map.</p>`
    + `<div class="regions-list">${regionsLists(clazz, payload, currentSeason, teams)}</div></div></div></div>`;
}

// ------------------------------------------------------------- compare

// A school renamed: its old name, its new one, and the first season under the new one
// (backend/helpers/data_helpers.py SCHOOL_RENAMES; school_renames_test.py keeps the two the same).
export const SCHOOL_RENAMES = [["Leake Central", "Leake", 2026]];

/** *name* (a school's name in *season*) as the school is called in *other*, a season before or after. */
export function nameIn(name, season, other) {
  let out = name;
  for (const [old, now, first] of SCHOOL_RENAMES) {
    if (other >= first && season < first && out === old) out = now;
    else if (other < first && season >= first && out === now) out = old;
  }
  return out;
}

/** "Region 2-4A in 2026", or "not in a region in 2026". */
const placeIn = (p, label) => (p ? `${place(p)} in ${label}` : `not in a region in ${label}`);

/**
 * What changed between two maps: *a* and *b* are { label, season, clazz, payload } (a season's data, and
 * the class its map shows), in either order; the older is the one before. Every school on either map,
 * with where it is in each season, in groups: moved in (on the newer map, not the older one), moved out,
 * changed region (on both, in another region), and same region. Each school is
 * { school, slug, season, class, region, older, newer }: its name and place in *season* (the newer one,
 * or the older for a school gone since), and older and newer, its {class, region} then (or null).
 * Null when both maps show the same season: nothing changed between them.
 */
export function compareChanges(a, b) {
  if (a.season === b.season) return null;
  const [older, newer] = a.season < b.season ? [a, b] : [b, a];
  const at = (side) => new Map(side.payload.schools.map((s) => [s.school, s]));
  const then = at(older);
  const now = at(newer);
  const groups = { in: [], out: [], moved: [], same: [] };
  const seen = new Set();
  for (const s of newer.payload.schools) {
    const was = then.get(nameIn(s.school, newer.season, older.season)) ?? null;
    const onNewer = s.class === newer.clazz;
    const onOlder = was?.class === older.clazz;
    if (!onNewer && !onOlder) continue;
    if (was) seen.add(was.school);
    const row = { school: s.school, slug: s.slug, season: newer.season, class: s.class, region: s.region, successorOf: s.successor_of ?? null,
      older: was && { class: was.class, region: was.region }, newer: { class: s.class, region: s.region } };
    if (onNewer && !onOlder) groups.in.push(row);
    else if (!onNewer) groups.out.push(row);
    else (was.region === s.region ? groups.same : groups.moved).push(row);
  }
  for (const s of older.payload.schools) {
    if (s.class !== older.clazz || seen.has(s.school)) continue;
    const successor = newer.payload.schools.find((n) => n.successor_of === s.school) ?? null;
    groups.out.push({ school: s.school, slug: s.slug, season: older.season, class: s.class, region: s.region,
      older: { class: s.class, region: s.region }, newer: null, successor: successor?.school ?? null });
  }
  for (const list of Object.values(groups)) list.sort((x, y) => byName(x.school, y.school));
  return { older, newer, groups };
}

/** The list under the two maps: what changed between them, each school picking it on both maps. */
export function compareChangesHtml(changes, teams = {}) {
  if (!changes) return `<p class="focus-note muted">Both maps show the same season, so nothing changed between them.</p>`;
  const { older, newer, groups } = changes;
  const map = (side) => `${side.label} ${side.clazz}A`;
  const sameClass = older.clazz === newer.clazz;
  // "Moved up from", "Moved down to": a move between classes says which way; one within a class doesn't.
  const way = (from, to) => (from.class === to.class ? "Moved" : to.class > from.class ? "Moved up" : "Moved down");
  const detail = {
    in: (r) => (r.older ? `${way(r.older, r.newer)} from ${placeIn(r.older, older.label)}`
      : r.successorOf ? `New school, on ${r.successorOf}’s campus` : `Not in a region in ${older.label}`),
    out: (r) => (r.newer ? `${way(r.older, r.newer)} to ${placeIn(r.newer, newer.label)}`
      : r.successor ? `Now part of ${r.successor}` : `Not in a region in ${newer.label}`),
    moved: (r) => `${place(r.older)} → ${place(r.newer)}`,
    same: (r) => place(r.newer),
  };
  const titles = sameClass
    ? { in: `Moved into ${newer.clazz}A`, out: `Moved out of ${older.clazz}A`, moved: "Changed region", same: "Same region" }
    : { in: `On the ${map(newer)} map only`, out: `On the ${map(older)} map only`, moved: "On both, in another region", same: "On both, in the same region" };
  const row = (key) => (r) => `<li><a class="compare-changes__row" href="?team=${esc(r.slug)}" data-team="${esc(r.slug)}" data-school="${esc(r.school)}" data-season="${esc(r.season)}">`
    + `${teamMark(r.school, teams[r.school])}<span class="compare-changes__team">${esc(r.school)}</span>`
    + `<span class="compare-changes__detail">${esc(detail[key](r))}</span></a></li>`;
  const group = (key) => {
    const list = groups[key];
    if (!list.length) return "";
    const body = `<ul>${list.map(row(key)).join("")}</ul>`;
    const head = `${esc(titles[key])} <span class="compare-changes__count">${list.length}</span>`;
    // The schools that stayed put are the least news: folded away.
    return key === "same"
      ? `<details class="compare-changes__group"><summary><h3>${head}</h3></summary>${body}</details>`
      : `<section class="compare-changes__group"><h3>${head}</h3>${body}</section>`;
  };
  const counts = ["in", "out", "moved"].reduce((n, k) => n + groups[k].length, 0);
  return `<h2 class="compare-changes__title">What changed from ${esc(map(older))} to ${esc(map(newer))}</h2>`
    + (counts ? "" : `<p class="focus-note muted">No school moved: every one is in the same region on both maps.</p>`)
    + `<div class="compare-changes__groups">${["in", "out", "moved", "same"].map(group).join("")}</div>`;
}

/**
 * Where the team picked on one map is on the other, when it isn't on it: "Bay isn't on this map: in
 * Region 8-4A in 2027 and 2028." *school* is its row in this map's season (or null: no school by that
 * name then).
 */
export function notOnMapHtml(name, school, label) {
  return `<p class="picked__facts"><strong>${esc(name)}</strong> isn’t on this map: `
    + `${esc(school ? `${placeIn(school, label)}` : `not in a region in ${label}`)}.</p>`;
}

// ------------------------------------------------------------- timeline

/**
 * The timeline's maps, oldest first: one for each of *options* (the seasons of regions, any order) with
 * its data (*payloads*, in the same order). Each shows *clazz*, or, following a team (*follow*: { name,
 * season }, its name in a season), the class the team was in that season. Each is { option, payload,
 * clazz, row }: row is the team's line that season (null: not in a region then, or no team followed).
 */
export function timelineSeasons(options, payloads, clazz, follow = null) {
  return options.map((option, i) => ({ option, payload: payloads[i] }))
    .sort((a, b) => a.option.season - b.option.season)
    .map(({ option, payload }) => {
      const name = follow && nameIn(follow.name, follow.season, option.season);
      const row = name ? payload.schools.find((r) => r.school === name) ?? null : null;
      return { option, payload, clazz: row ? row.class : clazz, row };
    });
}

/** The seasons the timeline covers: "2025 to 2028 seasons" (or "2026 season", just one). */
export function timelineSpan(seasons) {
  const from = seasons[0]?.option.season;
  const to = seasons[seasons.length - 1]?.option.seasons?.at(-1) ?? seasons[seasons.length - 1]?.option.season;
  if (from == null) return "";
  return from === to ? `${from} season` : `${from} to ${to} seasons`;
}

/** The followed team's way through the seasons: "Purvis: Region 4-5A in 2025 → … → Region 7-4A in 2027 and 2028". */
export function timelinePathHtml(name, seasons) {
  const steps = seasons.map((s) => `<span class="timeline-path__step">${esc(placeIn(s.row, s.option.label))}</span>`);
  return `<p class="timeline-path"><strong>${esc(name)}</strong>: ${steps.join('<span class="timeline-path__arrow" aria-hidden="true"> → </span><span class="visually-hidden">, then </span>')}</p>`;
}

/**
 * The Timeline view: the page's heading, its views and controls, a map for each season of regions in
 * order (each zoomed to the followed team's region, if one is), and the team's way through them.
 * *seasons* is timelineSeasons'; *follow* is the followed team's name, or null.
 */
export function timelinePage(clazz, base, seasons, { controls = "", share = "", views = "", follow = null } = {}) {
  const span = timelineSpan(seasons);
  const note = follow
    ? `Each map shows ${esc(follow)}’s class that season. Pick another team to follow it, or an empty spot on a map to stop.`
    : "Pick a team on any map to follow it through every season: each map shows its class and region that season.";
  return `<div class="page regions-page regions-page--timeline"><header class="entry-head">`
    + `${breadcrumbs(regionsTrail(clazz))}<div class="title-row"><h1 class="title">${esc(regionsTitle(clazz))}</h1>${share}</div>`
    + `<p class="regions-sub">${esc(span)}</p>`
    + `${views}${controls}<p class="focus-note muted regions-note">${note}</p></header>`
    + (follow ? timelinePathHtml(follow, seasons) : "")
    + `<div class="timeline">${seasons.map((s, i) => `<section class="timeline__season" data-season="${s.option.season}" data-index="${i}">`
      + `<h2 class="timeline__label">${esc(s.option.label)} <span class="timeline__class">${s.clazz}A</span></h2>`
      + `${mapFigure(base, s.payload, s.clazz, { full: false })}</section>`).join("")}</div></div>`;
}

/**
 * One side of Compare: its season and class pickers over its map. *side* is "a" (the page's class and
 * season) or "b" (?vs=, ?vsclass=); *name* says which it is on screen ("Map 1").
 */
export function compareSide(side, base, option, payload, clazz, index, name) {
  const seasons = index.options.map((o) => `<option value="${esc(o.season)}"${o.season === option.season ? " selected" : ""}>${esc(o.label)}</option>`).join("");
  const classes = [1, 2, 3, 4, 5, 6, 7].map((c) => `<option value="${c}"${c === clazz ? " selected" : ""}>${c}A</option>`).join("");
  return `<section class="compare__side" data-side="${side}" aria-label="${name}">`
    + `<div class="compare__pickers">`
    + `<label><span class="visually-hidden">${name}: seasons</span><select class="select-box" data-control="compare-season" data-side="${side}">${seasons}</select></label>`
    + `<label><span class="visually-hidden">${name}: class</span><select class="select-box" data-control="compare-class" data-side="${side}">${classes}</select></label>`
    + `</div>${mapFigure(base, payload, clazz, { full: false })}</section>`;
}

/**
 * The Compare view: the page's heading, its views and controls, two maps side by side (each with its
 * own season and class), and what changed between them. *a* and *b* are { option, payload, clazz }.
 */
export function comparePage(clazz, base, a, b, index, { controls = "", share = "", teams = {}, views = "" } = {}) {
  const changes = compareChanges(
    { label: a.option.label, season: a.option.season, clazz: a.clazz, payload: a.payload },
    { label: b.option.label, season: b.option.season, clazz: b.clazz, payload: b.payload },
  );
  // In time order, the older map first (on the left, or on top on a phone), whichever is the page's.
  const [first, second] = b.option.season < a.option.season ? [{ ...b, key: "b" }, { ...a, key: "a" }] : [{ ...a, key: "a" }, { ...b, key: "b" }];
  return `<div class="page regions-page regions-page--compare"><header class="entry-head">`
    + `${breadcrumbs(regionsTrail(clazz))}<div class="title-row"><h1 class="title">${esc(regionsTitle(clazz))}</h1>${share}</div>`
    + `<p class="regions-sub">${esc(`${first.option.label} ${first.clazz}A vs. ${second.option.label} ${second.clazz}A`)}</p>`
    + `${views}${controls}<p class="focus-note muted regions-note">Pick a team on either map, or in the list under them, to see where it is on both.</p></header>`
    + `<div class="compare">${[first, second].map((x, i) => compareSide(x.key, base, x.option, x.payload, x.clazz, index, `Map ${i + 1}`)).join("")}</div>`
    + `<section class="compare-changes" aria-label="What changed">${compareChangesHtml(changes, teams)}</section></div>`;
}

// The map's buttons, under it so they never cover a school: zoom in and out and back to the whole state
// (a "reset" arrow), and apart from them, full screen, with its name (the corners, pointing in once
// it's on, and "Exit full screen").
const icon = (d) => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" `
  + `stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const MAP_ICONS = {
  in: icon('<path d="M12 5v14M5 12h14"/>'),
  out: icon('<path d="M5 12h14"/>'),
  reset: icon('<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 3.5v4h4"/>'),
  full: icon('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
  leave: icon('<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>'),
};

/** The map's whole view (in map units): the state, with room around it. */
export function wholeView(base) {
  const [mx, my] = [base.width * MARGIN, base.height * MARGIN];
  return { x: -mx, y: -my, w: base.width + 2 * mx, h: base.height + 2 * my };
}

/**
 * What's under the map once a team is picked: its helmet, name and region, where it is and where it
 * was the season before, and the region's other schools (each picks that school).
 */
export function pickedHtml(school, payload, teams = {}) {
  const others = payload.schools
    .filter((s) => s.class === school.class && s.region === school.region && s.slug !== school.slug)
    .sort((a, b) => byName(a.school, b.school));
  const facts = [school.county ? `${school.city}, ${school.county} County` : "", teamChange(school, payload.prior_season)].filter(Boolean);
  return `<div class="picked__head">${teamMark(school.school, teams[school.school], { size: 32 })}`
    + `<span class="picked__name">${esc(school.school)}</span>`
    + `<span class="picked__region"><span class="region-chip region-chip--${school.region}" aria-hidden="true">${school.region}</span>`
    + `<strong>${esc(place(school))}</strong></span></div>`
    + (facts.length ? `<p class="picked__facts">${esc(facts.join(" · "))}</p>` : "")
    + (others.length
      ? `<p class="picked__others"><span class="picked__label">Other schools in ${esc(place(school))}:</span> `
        + others.map((s) => `<a href="${esc(regionsPath(school.class))}?team=${esc(s.slug)}" data-team="${esc(s.slug)}">`
          + `${teamMark(s.school, teams[s.school], { size: 20 })}<span>${esc(s.school)}</span></a>`).join("")
        + "</p>"
      : "");
}

/** The box (in map units) that shows a region whole, with room around it, in the map's shape. */
export function regionView(box, base, pad = 0.3) {
  const [x0, y0, x1, y1] = box;
  let w = (x1 - x0) * (1 + 2 * pad);
  let h = (y1 - y0) * (1 + 2 * pad);
  const whole = wholeView(base);
  const shape = whole.w / whole.h;
  if (w / h > shape) h = w / shape;
  else w = h * shape;
  w = Math.min(w, whole.w);
  h = Math.min(h, whole.h);
  return { x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2, w, h };
}

/**
 * *view* moved, if need be, so the map can't be dragged away from Mississippi: the view's middle stays
 * over the state's box (so some of the state is always in view, at any zoom). Returns {x, y}.
 */
export function keepInView(view, base) {
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  return {
    x: clamp(view.x + view.w / 2, 0, base.width) - view.w / 2,
    y: clamp(view.y + view.h / 2, 0, base.height) - view.h / 2,
  };
}

/** Where the tooltip goes (its top-left, in pixels in the frame) for a dot at (x, y) of radius r:
 * centered above the dot, or below it when there's no room above, and kept inside the frame. */
export function hoverSpot(x, y, r, tip, frame, gap = 6) {
  const edge = 4;
  const left = Math.min(Math.max(x - tip.w / 2, edge), Math.max(edge, frame.w - tip.w - edge));
  const above = y - r - gap - tip.h;
  return { left, top: above >= edge ? above : Math.min(y + r + gap, frame.h - tip.h - edge) };
}

/**
 * Make the map on the page work: zoom (wheel, pinch, buttons), pan (drag), a name on hover, and a
 * team picked (from the map, the list, the team under the map or the page's link) highlighted with
 * its region and zoomed to. onPick(slug or null) tells the page, to keep the address in step.
 */
export function wireRegionsMap(root, base, payload, clazz, { picked = null, teams = {}, onPick = () => {}, onMove = () => {}, onFull = () => {}, elsewhere = null } = {}) {
  const frame = root.querySelector("[data-map]");
  const svg = frame?.querySelector("svg");
  if (!svg) return null;
  const figure = frame.closest(".regions-map");
  const hover = frame.querySelector(".regions-map__hover");
  const caption = root.querySelector(".regions-map__picked");
  const status = root.querySelector("[data-picked-status]");
  const whole = wholeView(base);
  let view = { ...whole };
  let current = null;
  const bySlug = new Map(payload.schools.filter((s) => s.class === clazz).map((s) => [s.slug, s]));

  // The view always has the frame's shape (it's the state's shape, except in full screen): widened or
  // heightened about its middle when it doesn't.
  const aspect = () => {
    const box = svg.getBoundingClientRect();
    return box.width && box.height ? box.width / box.height : whole.w / whole.h;
  };
  const widest = () => Math.max(whole.w, whole.h * aspect());
  const apply = () => {
    const a = aspect();
    if (Math.abs(view.w / view.h - a) > 1e-3) {
      const [cx, cy] = [view.x + view.w / 2, view.y + view.h / 2];
      if (view.w / view.h < a) view.w = view.h * a;
      else view.h = view.w / a;
      view = { x: cx - view.w / 2, y: cy - view.h / 2, w: view.w, h: view.h };
    }
    view = { ...view, ...keepInView(view, base) };
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
    const zoom = whole.w / view.w;
    const px = view.w / (svg.getBoundingClientRect().width || 600);
    const r = 11 * px; // dots keep their size on screen at any zoom
    for (const g of svg.querySelectorAll(".map-dot")) {
      g.firstChild.setAttribute("r", r);
      g.lastChild.setAttribute("font-size", r * 1.2);
    }
    svg.classList.toggle("is-zoomed", zoom >= 2.2); // county names once there's room for them
    for (const t of svg.querySelectorAll(".map-county-name")) t.setAttribute("font-size", 40 / Math.max(1, zoom / 2.2));
  };
  const zoomAt = (factor, cx, cy) => {
    const w = Math.min(widest(), Math.max(whole.w / 40, view.w / factor));
    const k = w / view.w;
    view = { x: cx - (cx - view.x) * k, y: cy - (cy - view.y) * k, w, h: view.h * k };
    moves += 1;
    apply();
  };
  const toMap = (clientX, clientY) => {
    const box = svg.getBoundingClientRect();
    return [view.x + ((clientX - box.left) / box.width) * view.w, view.y + ((clientY - box.top) / box.height) * view.h];
  };
  const middle = () => [view.x + view.w / 2, view.y + view.h / 2];
  // The first time the reader moves the map, and how ("wheel", "pinch", "drag", "buttons"): once a page.
  let moved = false;
  let moves = 0; // every time the view changes, for full screen to know whether the map was moved
  const used = (how) => {
    if (moved) return;
    moved = true;
    onMove(how);
  };

  const motion = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
  // On a computer the map sticks under the header once the page scrolls a little: a team picked
  // before then could have its details below the fold, so the page scrolls just enough to show them.
  const show = (el) => {
    if (getComputedStyle(el.closest(".regions-map")).position !== "sticky") return;
    const below = el.getBoundingClientRect().bottom - innerHeight + 12;
    if (below > 0) scrollBy({ top: below, behavior: motion() });
  };

  const pick = (slug, { zoom = true, reveal = true } = {}) => {
    const school = slug ? bySlug.get(slug) : null;
    for (const g of svg.querySelectorAll(".map-dot")) {
      g.classList.toggle("is-picked", Boolean(school) && g.dataset.team === school.slug);
      g.classList.toggle("is-dim", Boolean(school) && Number(g.dataset.region) !== school.region);
    }
    for (const p of svg.querySelectorAll(".map-region")) p.classList.toggle("is-dim", Boolean(school) && Number(p.dataset.region) !== school.region);
    for (const a of root.querySelectorAll(".regions-list [data-team]")) {
      if (school && a.dataset.team === school.slug) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    }
    if (caption) {
      // A team not on this map (Compare: picked on the other one) says where it is instead.
      const html = school ? pickedHtml(school, payload, teams) : slug && elsewhere ? elsewhere(slug) : "";
      caption.innerHTML = html;
      caption.hidden = !html;
      if (school && reveal) show(caption);
    }
    if (status) status.textContent = school ? `${school.school}: ${place(school)}` : "";
    // Another team in the region already shown, its dot in view: the map stays where it is.
    const stay = school && current && current.region === school.region && school.x != null
      && school.x >= view.x && school.x <= view.x + view.w && school.y >= view.y && school.y <= view.y + view.h;
    current = school;
    const box = school && payload.regions[String(clazz)]?.[String(school.region)]?.box;
    if (zoom && !stay) {
      view = box ? regionView(box, base) : { ...whole };
      moves += 1;
      apply();
    }
    return school;
  };

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [x, y] = toMap(e.clientX, e.clientY);
    zoomAt(e.deltaY < 0 ? 1.25 : 0.8, x, y);
    used("wheel");
  }, { passive: false });
  const pointers = new Map();
  let spread = null;
  let dragged = false;
  svg.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, e);
    dragged = false;
  });
  svg.addEventListener("pointermove", (e) => {
    const dot = e.target.closest?.(".map-dot");
    const school = dot && bySlug.get(dot.dataset.team);
    if (school && e.pointerType === "mouse") {
      const box = frame.getBoundingClientRect();
      const d = dot.firstChild.getBoundingClientRect();
      hover.textContent = school.school;
      hover.hidden = false;
      const spot = hoverSpot(d.left + d.width / 2 - box.left, d.top + d.height / 2 - box.top, d.width / 2,
        { w: hover.offsetWidth, h: hover.offsetHeight }, { w: box.width, h: box.height });
      hover.style.left = `${spot.left}px`;
      hover.style.top = `${spot.top}px`;
    } else hover.hidden = true;
    if (!pointers.has(e.pointerId)) return;
    const before = pointers.get(e.pointerId);
    pointers.set(e.pointerId, e);
    const box = svg.getBoundingClientRect();
    if (pointers.size === 1) {
      const dx = e.clientX - before.clientX;
      const dy = e.clientY - before.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        dragged = true;
        svg.setPointerCapture?.(e.pointerId);
        used("drag");
      }
      view = { ...view, x: view.x - (dx / box.width) * view.w, y: view.y - (dy / box.height) * view.h };
      moves += 1;
      apply();
    } else if (pointers.size === 2) {
      dragged = true;
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (spread) zoomAt(d / spread, ...toMap((a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2));
      spread = d;
      used("pinch");
    }
  });
  for (const type of ["pointerup", "pointercancel", "pointerleave"]) {
    svg.addEventListener(type, (e) => {
      pointers.delete(e.pointerId);
      spread = null;
      if (type === "pointerleave") hover.hidden = true;
    });
  }
  svg.addEventListener("click", (e) => {
    if (dragged) return;
    const dot = e.target.closest(".map-dot");
    const school = pick(dot ? dot.dataset.team : null, { zoom: Boolean(dot) });
    onPick(school?.slug ?? null, "map");
  });
  figure?.querySelector(".regions-map__zoom")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-zoom]");
    if (!b) return;
    if (b.dataset.zoom === "reset") {
      view = { ...whole };
      moves += 1;
      apply();
    } else zoomAt(b.dataset.zoom === "in" ? 1.6 : 1 / 1.6, ...middle());
    used("buttons");
  });
  // Full screen: the map (with its buttons and the picked team) over the page between the site's header
  // and the class picker's bar, and on a phone the tab bar, which stay (onFull(on) tells the page, to show what's on screen in the
  // bar), until the button, Escape or the page changes. Coming back, the map shows what it did before,
  // unless it was moved.
  const fitUnderBars = () => {
    const bars = [...document.querySelectorAll(".site-header-bar, .scrubber-bar:not([hidden])")];
    const top = Math.max(0, ...bars.map((b) => b.getBoundingClientRect().bottom));
    // On a phone the tab bar along the bottom stays too: the map ends above it.
    const tabs = document.querySelector(".tab-bar");
    const shown = tabs && getComputedStyle(tabs).display !== "none" ? tabs.getBoundingClientRect() : null;
    const bottom = shown && shown.height ? Math.max(0, innerHeight - shown.top) : 0;
    figure.style.setProperty("--map-full-top", `${Math.round(top)}px`);
    figure.style.setProperty("--map-full-bottom", `${Math.round(bottom)}px`);
  };
  const fullButton = figure?.querySelector("[data-full]");
  let before = null;
  const full = (on) => {
    if (!figure || on === figure.classList.contains("is-full")) return;
    if (on) before = { ...view };
    const kept = !on && before && moves === movesAtFull ? before : null;
    onFull(on);
    figure.classList.toggle("is-full", on);
    document.documentElement.classList.toggle("is-map-full", on);
    if (on) fitUnderBars();
    fullButton.setAttribute("aria-pressed", String(on));
    fullButton.innerHTML = `${on ? MAP_ICONS.leave : MAP_ICONS.full}<span>${on ? "Exit full screen" : "Full screen"}</span>`;
    if (on) movesAtFull = moves;
    if (kept) view = kept;
    else if (!on) view = { x: view.x + (view.w - Math.min(view.w, view.h * aspect())) / 2, y: view.y, w: Math.min(view.w, view.h * aspect()), h: view.h };
    apply();
  };
  let movesAtFull = null;
  fullButton?.addEventListener("click", () => full(!figure.classList.contains("is-full")));
  const onKey = (e) => {
    if (!figure.isConnected) return removeEventListener("keydown", onKey);
    if (e.key === "Escape" && figure.classList.contains("is-full")) full(false);
  };
  addEventListener("keydown", onKey);

  root.querySelector(".regions-list")?.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-team]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    pick(a.dataset.team);
    onPick(a.dataset.team, "list");
    frame.scrollIntoView?.({ block: "nearest", behavior: motion() });
  });
  caption?.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-team]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    pick(a.dataset.team);
    onPick(a.dataset.team, "caption");
  });
  // How much height the site's bars take (the header, which wraps to two lines on a narrow phone, the
  // class picker's bar and the phone's tab bar): the CSS sizes the map to fit with its buttons in the
  // rest (--map-bars). They don't change as a phone's address bar comes and goes.
  const measureBars = () => {
    const height = (sel) => {
      const el = document.querySelector(sel);
      return el && !el.hidden && getComputedStyle(el).display !== "none" ? el.getBoundingClientRect().height : 0;
    };
    const bars = height(".site-header-bar") + height(".scrubber-bar") + height(".tab-bar");
    figure?.style.setProperty("--map-bars", `${Math.round(bars)}px`);
  };
  measureBars();
  // Until the map leaves the page (another page, class or season draws a new one): then it lets go, so
  // maps already gone don't redraw on every resize.
  const onResize = () => {
    if (!svg.isConnected) return removeEventListener("resize", onResize);
    measureBars();
    if (figure?.classList.contains("is-full")) fitUnderBars();
    apply();
  };
  addEventListener("resize", onResize);
  apply();
  if (picked) pick(picked, { reveal: false }); // the page's link: the page opens at its top
  return { pick, full: (on) => full(on) };
}

// ------------------------------------------------------------- data

const cache = new Map();

/** A file under /static/regions/, fetched once per page load. */
export function regionsFile(name) {
  if (!cache.has(name)) {
    cache.set(name, fetch(`${REGIONS_DATA}/${name}`).then((res) => {
      if (!res.ok) throw Object.assign(new Error(String(res.status)), { status: res.status });
      return res.json();
    }).catch((err) => {
      cache.delete(name);
      throw err;
    }));
  }
  return cache.get(name);
}

/** The choice a season belongs to (2028 is in "2027 and 2028"), or the default. */
export function pickOption(index, season) {
  return index.options.find((o) => o.seasons.includes(season)) ?? index.options.find((o) => o.season === index.default) ?? index.options[0];
}
