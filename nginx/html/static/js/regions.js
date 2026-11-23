import { breadcrumbs, teamColorStyle, teamMark } from "./components.js";
import { escapeHtml as esc } from "./format.js";
import { slugify } from "./routes.js";

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

/**
 * What a map shows (a class's regions, or a county's schools and theirs): its schools; each one's
 * group (the dots and shape picked together: a region), color (1-8, the region colors) and the text on
 * its dot; each group's shape and box; and the SVG's description. *away*: schools drawn smaller and
 * faded, there only to show their region (a county's schools' region-mates elsewhere).
 */
export function classLayer(payload, clazz) {
  return {
    schools: payload.schools.filter((s) => s.class === clazz),
    group: (s) => String(s.region),
    color: (s) => s.region,
    mark: (s) => String(s.region),
    away: () => false,
    shapes: Object.entries(payload.regions[String(clazz)] ?? {}).map(([g, r]) => ({ group: g, color: Number(g), d: r.d, box: r.box })),
    county: null,
    label: `Map of Mississippi with each Class ${clazz}A school as a dot numbered by its region`,
  };
}

/** The SVG: land, the region shapes, county lines and names, the state's outline, then the dots. */
export function mapSvg(base, payload, clazz, layer = classLayer(payload, clazz)) {
  const focus = layer.county ? base.counties.find((c) => c.name === layer.county) : null;
  const counties = base.counties.map((c) => `<path class="map-county" data-county="${esc(c.name)}" d="${c.d}"/>`).join("");
  const names = base.counties.map((c) => `<text class="map-county-name" x="${c.label[0]}" y="${c.label[1]}">${esc(c.name)}</text>`).join("");
  const shapes = layer.shapes
    .map((r) => `<path class="map-region map-region--${r.color}" data-group="${esc(r.group)}"${r.fill ? ` style="fill:${r.fill};stroke:${r.fill}"` : ""} d="${r.d}"/>`).join("");
  const placed = layer.schools.filter((s) => s.x != null);
  // A pill (a county's map) has a line back to its school's spot, shown when it's moved off it.
  const dots = placed
    .map((s) => (layer.pill
      ? `<g class="map-dot map-dot--pill" data-team="${esc(s.slug)}" data-group="${esc(layer.group(s))}" data-x="${s.x}" data-y="${s.y}" tabindex="-1">`
        + `<rect style="fill:${layer.shade(s).fill}"/><text x="${s.x}" y="${s.y}" style="fill:${layer.shade(s).ink}">${esc(layer.mark(s))}</text></g>`
      : `<g class="map-dot map-dot--${layer.color(s)}${layer.away(s) ? " is-away" : ""}" data-team="${esc(s.slug)}" data-group="${esc(layer.group(s))}" tabindex="-1">`
        + `<circle cx="${s.x}" cy="${s.y}" r="34"/><text x="${s.x}" y="${s.y}">${esc(layer.mark(s))}</text></g>`)).join("");
  // A pill moved off its school's spot has a line back to it, under every pill.
  const pins = layer.pill
    ? `<g class="map-pins" aria-hidden="true">${placed.map((s) => `<g data-team="${esc(s.slug)}" data-group="${esc(layer.group(s))}" style="display:none">`
      + `<line class="map-pin-line" x1="${s.x}" y1="${s.y}"/><circle class="map-pin" cx="${s.x}" cy="${s.y}"/></g>`).join("")}</g>`
    : "";
  // Each school's name, shown beside its dot once the map is zoomed in far enough (wireRegionsMap
  // places them, and hides those with no room).
  const labels = placed
    .map((s) => `<line class="map-leader" data-team="${esc(s.slug)}" data-group="${esc(layer.group(s))}" hidden/>`
      + `<text class="map-label" data-team="${esc(s.slug)}" data-group="${esc(layer.group(s))}" x="${s.x}" y="${s.y}">${esc(s.school)}</text>`).join("");
  const v = wholeView(base);
  return `<svg class="regions-map__svg" viewBox="${v.x} ${v.y} ${v.w} ${v.h}" role="img" `
    + `aria-label="${esc(layer.label)}">`
    + `<path class="map-land" d="${base.state}"/><g class="map-regions">${shapes}</g>`
    + `<g class="map-counties">${counties}</g><g class="map-county-names">${names}</g>`
    + `<path class="map-state" d="${base.state}"/>${focus ? `<path class="map-county-focus" d="${focus.d}"/><path class="map-county-other" d=""/>` : ""}`
    + `<g class="map-labels" aria-hidden="true">${labels}</g>${pins}<g class="map-dots">${dots}</g></svg>`;
}

/**
 * One map with its buttons, under it, and the picked team's details: the map (with its zoom buttons,
 * tooltip and, with *full*, full screen) for the Map view and each side of Compare.
 */
export function mapFigure(base, payload, clazz, { full = true, layer = classLayer(payload, clazz), after = "" } = {}) {
  const button = (attr, label, icon) => `<button type="button" ${attr} aria-label="${label}" title="${label}">${icon}</button>`;
  return `<figure class="regions-map">`
    + `<div class="regions-map__frame" data-map>${mapSvg(base, payload, clazz, layer)}`
    + `<div class="regions-map__hover" aria-hidden="true" hidden></div></div>`
    + `<div class="regions-map__tools"><div class="regions-map__zoom" role="group" aria-label="Zoom">`
    + `${button('data-zoom="in"', "Zoom in", MAP_ICONS.in)}${button('data-zoom="out"', "Zoom out", MAP_ICONS.out)}`
    + `${button('data-zoom="reset"', "Show the whole state", MAP_ICONS.reset)}</div>`
    + (full ? `<button type="button" class="regions-map__full" data-full aria-pressed="false">${MAP_ICONS.full}<span>Full screen</span></button>` : "")
    + `</div><p class="visually-hidden" aria-live="polite" data-picked-status></p>`
    + `<figcaption class="regions-map__picked" hidden></figcaption>${after}</figure>`;
}

/**
 * The Timeline's buttons to step through its seasons, a season at a time, in the zoom buttons' style:
 * hidden until the seasons don't all fit (the app shows them and dims the one at an end it has reached).
 */
export function timelineSteps() {
  const button = (step, label, icon) => `<button type="button" data-step="${step}">${icon}${label}</button>`;
  return `<div class="timeline-steps" role="group" aria-label="Seasons" hidden>`
    + `${button(-1, "Older", MAP_ICONS.back)}${button(1, `Newer${MAP_ICONS.next}`, "")}</div>`;
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

// Schools merged into one: the new school, its first season, and the schools merged into it, the one
// whose campus it carries first (data_helpers.py SCHOOL_CONSOLIDATIONS; school_renames_test.py keeps
// the two the same).
export const SCHOOL_CONSOLIDATIONS = [
  ["Leake", 2026, ["Leake Central", "Leake County"]],
  ["North Tippah", 2027, ["Walnut", "Falkner"]],
];

/**
 * The school *name* (in *season*) was or became in *other*, as every name it had there: the schools
 * merged into it, for a season before a consolidation (North Tippah in 2026: Walnut and Falkner); the
 * school it merged into, for a season after (Falkner in 2027: North Tippah); else its one name then.
 */
export function namesIn(name, season, other) {
  for (const [merged, first, members] of SCHOOL_CONSOLIDATIONS) {
    const then = nameIn(name, season, first);
    if (season >= first && then === merged && other < first) return [...members];
    if (season < first && members.includes(name) && other >= first) return [merged];
  }
  return [nameIn(name, season, other)];
}

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
      // Every school it was that season: more than one before a consolidation, the campus's first.
      const names = follow ? namesIn(follow.name, follow.season, option.season) : [];
      const rows = names.map((n) => payload.schools.find((r) => r.school === n)).filter(Boolean);
      const row = rows[0] ?? null;
      return { option, payload, clazz: row ? row.class : clazz, row, rows };
    });
}

/** The seasons the timeline covers: "2025 to 2028 seasons" (or "2026 season", just one). */
export function timelineSpan(seasons) {
  const from = seasons[0]?.option.season;
  const to = seasons[seasons.length - 1]?.option.seasons?.at(-1) ?? seasons[seasons.length - 1]?.option.season;
  if (from == null) return "";
  return from === to ? `${from} season` : `${from} to ${to} seasons`;
}

/**
 * The followed team's seasons, as a table: each season's class and region, and the region's other
 * schools. A season before a consolidation lists each school merged into it; a season it wasn't in a
 * region says so.
 */
export function timelineTable(name, seasons, teams = {}) {
  const others = (s, row) => s.payload.schools
    .filter((r) => r.class === row.class && r.region === row.region && !s.rows.includes(r))
    .sort((a, b) => byName(a.school, b.school));
  const mates = (s, row) => others(s, row).map((r) => `<span class="timeline-table__mate">${teamMark(r.school, teams[r.school], { size: 18 })}${esc(r.school)}</span>`).join("");
  const where = (row, named) => `<span class="timeline-table__place">${named ? `${esc(row.school)}: ` : ""}`
    + `<span class="region-chip region-chip--${row.region}" aria-hidden="true">${row.region}</span>${esc(place(row))}</span>`;
  // A season before a consolidation has a line for each school merged into it, the season spanning them.
  const body = seasons.map((s) => {
    const season = (n) => `<th scope="row"${n > 1 ? ` rowspan="${n}"` : ""}>${esc(s.option.label)}</th>`;
    if (!s.rows.length) return `<tr>${season(1)}<td><span class="muted">Not in a region</span></td><td></td></tr>`;
    const named = s.rows.length > 1 || s.rows[0].school !== name;
    return s.rows.map((row, i) => `<tr>${i === 0 ? season(s.rows.length) : ""}<td>${where(row, named)}</td>`
      + `<td><span class="timeline-table__mates">${mates(s, row)}</span></td></tr>`).join("");
  }).join("");
  return `<div class="timeline-table__wrap"><table class="timeline-table">`
    + `<thead><tr><th scope="col">Season</th><th scope="col">Region</th><th scope="col">The region's other schools</th></tr></thead>`
    + `<tbody>${body}</tbody></table></div>`;
}

/**
 * The Timeline view: the page's heading, its views and controls, a map for each season of regions in
 * order (each zoomed to the followed team's region, if one is), and the team's way through them.
 * *seasons* is timelineSeasons'; *follow* is the followed team's name, or null.
 */
export function timelinePage(clazz, base, seasons, { controls = "", share = "", views = "", follow = null, teams = {} } = {}) {
  const span = timelineSpan(seasons);
  const note = follow
    ? `Each map shows ${esc(follow)}’s class that season. Pick another team to follow it, or an empty spot on a map to stop.`
    : "Pick a team on any map to follow it through every season: each map shows its class and region that season.";
  return `<div class="page regions-page regions-page--timeline"><header class="entry-head">`
    + `${breadcrumbs(regionsTrail(clazz))}<div class="title-row"><h1 class="title">${esc(regionsTitle(clazz))}</h1>${share}</div>`
    + `<p class="regions-sub">${esc(span)}</p>`
    + `${views}${controls}<p class="focus-note muted regions-note">${note}</p></header>`
    + `<div class="timeline">${seasons.map((s, i) => `<section class="timeline__season" data-season="${s.option.season}" data-index="${i}">`
      + `<h2 class="timeline__label">${esc(s.option.label)} <span class="timeline__class">${s.clazz}A</span></h2>`
      + `${mapFigure(base, s.payload, s.clazz, { full: false })}</section>`).join("")}</div>`
    + (follow ? `<h2 class="timeline-table__title">${esc(follow)}, season by season</h2>${timelineTable(follow, seasons, teams)}` : "")
    + "</div>";
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
  back: icon('<path d="M14.5 6 8.5 12l6 6"/>'),
  next: icon('<path d="M9.5 6l6 6-6 6"/>'),
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
export function pickedHtml(school, payload, teams = {}, color = school.region, href = regionsPath(school.class), chip = null) {
  const others = payload.schools
    .filter((s) => s.class === school.class && s.region === school.region && s.slug !== school.slug)
    .sort((a, b) => byName(a.school, b.school));
  const facts = [school.county ? `${school.city}, ${school.county} County` : "", teamChange(school, payload.prior_season)].filter(Boolean);
  return `<div class="picked__head">${teamMark(school.school, teams[school.school], { size: 32 })}`
    + `<span class="picked__name">${esc(school.school)}</span>`
    + `<span class="picked__region">${chip ?? `<span class="region-chip region-chip--${color}" aria-hidden="true">${school.region}</span>`}`
    + `<strong>${esc(place(school))}</strong></span></div>`
    + (facts.length ? `<p class="picked__facts">${esc(facts.join(" · "))}</p>` : "")
    + (others.length
      ? `<p class="picked__others"><span class="picked__label">Other schools in ${esc(place(school))}:</span> `
        + others.map((s) => `<a href="${esc(href)}?team=${esc(s.slug)}" data-team="${esc(s.slug)}">`
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

/**
 * When the map shows the schools' names: zoomed in this far, or zoomed in at all past the whole state
 * with a team picked (its region's names come first). Names with no room are left out either way.
 */
export const LABEL_ZOOM = 1.5;
export const LABEL_ZOOM_PICKED = 1.1;

/**
 * Where each school's name goes, in map units: *points* are { slug, x, y, name } (in the order they
 * get first pick: the picked team, its region, then the rest), *r* a dot's radius and *size* the
 * text's size. A spot must overlap no dot and no name already placed and stay inside *bounds* (the
 * view: { x0, y0, x1, y1 }). Right beside the dot first (right, left, above, below), where its own dot
 * must be plainly the nearest, so it can't be read as a neighbor's; else a little farther out, with a
 * line from the dot (*line*: [x1, y1, x2, y2]) that passes no other dot. A name with no such spot is
 * left out. Returns { slug: { x, y, anchor, line } }.
 */
export function placeLabels(points, r, size, bounds = null) {
  const width = (name) => name.length * size * 0.56; // Inter, about; a little room to spare
  const gap = r * 0.4;
  const far = r * 2.2; // how far out the farther spots are, past the dot's edge
  const boxes = points.map((p) => ({ x0: p.x - r, y0: p.y - r, x1: p.x + r, y1: p.y + r })); // the dots
  const outside = (b) => bounds != null && (b.x0 < bounds.x0 || b.x1 > bounds.x1 || b.y0 < bounds.y0 || b.y1 > bounds.y1);
  const overlaps = (b) => outside(b) || boxes.some((o) => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1);
  // From a dot's middle to the nearest point of a name's box.
  const reach = (q, b) => Math.hypot(Math.max(b.x0 - q.x, 0, q.x - b.x1), Math.max(b.y0 - q.y, 0, q.y - b.y1));
  // Its own dot is the nearest to it, by at least a dot's radius.
  const owned = (p, b) => points.every((q) => q === p || reach(q, b) > reach(p, b) + r);
  // A line from (x1, y1) to (x2, y2) keeps clear of every dot but p's.
  const clear = (p, [x1, y1, x2, y2]) => points.every((q) => {
    if (q === p) return true;
    const [dx, dy] = [x2 - x1, y2 - y1];
    const t = Math.max(0, Math.min(1, ((q.x - x1) * dx + (q.y - y1) * dy) / (dx * dx + dy * dy)));
    return Math.hypot(q.x - (x1 + t * dx), q.y - (y1 + t * dy)) > r * 1.2;
  });
  const placed = {};
  for (const p of points) {
    const w = width(p.name);
    const h = size;
    // { x, y, anchor } is where the text goes; box is what it covers; edge, where a line from the dot meets it.
    const beside = r + gap;
    const out = r + far;
    const spot = (x, y, anchor, edge = null) => {
      const x0 = anchor === "start" ? x : anchor === "end" ? x - w : x - w / 2;
      return { x, y, anchor, box: { x0, x1: x0 + w, y0: y - h / 2, y1: y + h / 2 }, edge };
    };
    const diag = out * 0.75;
    const spots = [
      spot(p.x + beside, p.y, "start"),
      spot(p.x - beside, p.y, "end"),
      spot(p.x, p.y - beside - h / 2, "middle"),
      spot(p.x, p.y + beside + h / 2, "middle"),
      spot(p.x + diag, p.y - diag, "start", [p.x + diag, p.y - diag]),
      spot(p.x + diag, p.y + diag, "start", [p.x + diag, p.y + diag]),
      spot(p.x - diag, p.y - diag, "end", [p.x - diag, p.y - diag]),
      spot(p.x - diag, p.y + diag, "end", [p.x - diag, p.y + diag]),
      spot(p.x + out, p.y, "start", [p.x + out, p.y]),
      spot(p.x - out, p.y, "end", [p.x - out, p.y]),
    ];
    for (const s of spots) {
      if (overlaps(s.box)) continue;
      let line = null;
      if (s.edge) {
        // From the dot's edge toward where the name starts, stopping a little short of it.
        const [ex, ey] = s.edge;
        const d = Math.hypot(ex - p.x, ey - p.y);
        const [ux, uy] = [(ex - p.x) / d, (ey - p.y) / d];
        line = [p.x + ux * r, p.y + uy * r, ex - ux * gap, ey - uy * gap];
        if (!clear(p, line)) continue;
      } else if (!owned(p, s.box)) continue;
      boxes.push(s.box);
      placed[p.slug] = { x: s.x, y: s.y, anchor: s.anchor, line };
      break;
    }
  }
  return placed;
}

/**
 * A dot's tooltip: the school's helmet, name and mascot over its region and town, and the seasons the
 * map is of (*seasons*: [2027, 2028]), edged in its color (*team*: its /teams entry, or nothing).
 */
export function hoverHtml(school, team, seasons = [], color = school.region, chip = null) {
  const where = [school.city, school.county ? `${school.county} County` : ""].filter(Boolean).join(", ");
  return `<span class="map-tip"${teamColorStyle(team)}>`
    + `<span class="map-tip__head">${teamMark(school.school, team, { size: 28 })}`
    + `<span class="map-tip__names"><strong class="map-tip__name">${esc(school.school)}</strong>`
    + (team?.mascot ? `<span class="map-tip__mascot">${esc(team.mascot)}</span>` : "")
    + `</span></span><span class="map-tip__place">${chip ?? `<span class="region-chip region-chip--${color}" aria-hidden="true">${school.region}</span>`}`
    + `<span>${esc(place(school))}${where ? ` · ${esc(where)}` : ""}</span></span>`
    + (seasons.length ? `<span class="map-tip__when">${esc(seasonsLabel(seasons))}</span>` : "")
    + "</span>";
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
export function wireRegionsMap(root, base, payload, clazz, { picked = null, teams = {}, onPick = () => {}, onMove = () => {}, onFull = () => {}, elsewhere = null, layer = classLayer(payload, clazz), home = null, href = undefined, otherCounty = null } = {}) {
  const frame = root.querySelector("[data-map]");
  const svg = frame?.querySelector("svg");
  if (!svg) return null;
  const figure = frame.closest(".regions-map");
  const hover = frame.querySelector(".regions-map__hover");
  const caption = root.querySelector(".regions-map__picked");
  const status = root.querySelector("[data-picked-status]");
  const whole = wholeView(base);
  // Where the map starts, and goes back to when a team is unpicked: the whole state, or *home*, a box
  // to fit with room around it (a county). The reset button always shows the whole state.
  const start = () => (home ? regionView(home, base, 0.45) : { ...whole });
  let view = start();
  let current = null;
  const bySlug = new Map(layer.schools.map((s) => [s.slug, s]));
  const groupOf = (s) => layer.group(s);
  const boxes = new Map(layer.shapes.map((r) => [r.group, r.box]));

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
    if (layer.pill) placePills(r, px);
    else {
      for (const g of svg.querySelectorAll(".map-dot")) {
        g.firstChild.setAttribute("r", g.classList.contains("is-away") ? r * 0.6 : r); // region-mates elsewhere: smaller
        g.lastChild.setAttribute("font-size", r * 1.2);
      }
    }
    svg.classList.toggle("is-zoomed", zoom >= 2.2); // county names once there's room for them
    for (const t of svg.querySelectorAll(".map-county-name")) t.setAttribute("font-size", 40 / Math.max(1, zoom / 2.2));
    const named = Boolean(layer.named) || zoom >= LABEL_ZOOM || (current != null && zoom >= LABEL_ZOOM_PICKED);
    svg.classList.toggle("is-named", named);
    if (named) labelDots(layer.pill ? pillReach : r, 12 * px);
  };
  // A county's pills ("3-6A"), a fixed size on screen: each about its school's spot, or, with *spread*,
  // pushed apart until none overlaps another (but never more than three pills' height from its spot), a
  // thin line back to the spot it left (as the share images do). Their names go beside where they end up.
  const pillAt = new Map(); // slug -> [x, y] in map units
  let pillReach = 0;
  const placePills = (r, px) => {
    const fs = r * 0.95;
    const h = r * 1.9;
    const pills = [...svg.querySelectorAll(".map-dot--pill")].map((g) => {
      const w = fs * (0.62 * g.lastChild.textContent.length + 0.9);
      const x = Number(g.dataset.x);
      const y = Number(g.dataset.y);
      return { g, w, x, y, at: [x, y], fixed: g.dataset.team === current?.slug }; // the picked one stays put
    });
    pillReach = Math.max(r, ...pills.map((p) => p.w / 2));
    if (layer.spread) {
      const gap = 5 * px;
      for (let round = 0; round < 80; round += 1) {
        let moved = false;
        for (let i = 0; i < pills.length; i += 1) {
          for (let j = i + 1; j < pills.length; j += 1) {
            const a = pills[i];
            const b = pills[j];
            const dx = b.at[0] - a.at[0];
            const dy = b.at[1] - a.at[1];
            const ox = (a.w + b.w) / 2 + gap - Math.abs(dx);
            const oy = h + gap - Math.abs(dy);
            if (ox <= 0 || oy <= 0) continue;
            moved = true;
            // Apart along the way that takes less, as the two already lean (ties: up and down).
            // (A picked pill doesn't move: the other takes the whole step.)
            const [sa, sb] = a.fixed ? [0, 1] : b.fixed ? [1, 0] : [0.5, 0.5];
            if (oy <= ox) {
              const k = (dy || (j - i)) > 0 ? 1 : -1;
              a.at[1] -= k * oy * sa;
              b.at[1] += k * oy * sb;
            } else {
              const k = dx > 0 ? 1 : -1;
              a.at[0] -= k * ox * sa;
              b.at[0] += k * ox * sb;
            }
          }
        }
        // None strays far from its school (zoomed out, a crowd overlaps instead: zooming in parts it).
        const most = h * 3;
        for (const q of pills) {
          const dx = q.at[0] - q.x;
          const dy = q.at[1] - q.y;
          const d = Math.hypot(dx, dy);
          if (d > most) q.at = [q.x + (dx / d) * most, q.y + (dy / d) * most];
        }
        if (!moved) break;
      }
    }
    const pinsBy = new Map([...svg.querySelectorAll(".map-pins > g")].map((g) => [g.dataset.team, g]));
    for (const p of pills) {
      const [cx, cy] = p.at;
      pillAt.set(p.g.dataset.team, p.at);
      const [rect, text] = p.g.children;
      const pinG = pinsBy.get(p.g.dataset.team);
      const [line, pin] = pinG.children;
      Object.entries({ x: cx - p.w / 2, y: cy - h / 2, width: p.w, height: h, rx: h / 2 }).forEach(([k, v]) => rect.setAttribute(k, v));
      text.setAttribute("x", cx);
      text.setAttribute("y", cy);
      text.setAttribute("font-size", fs);
      const off = Math.hypot(cx - p.x, cy - p.y) > h * 0.6;
      pinG.style.display = off ? "" : "none"; // (SVG has no hidden attribute)
      if (off) {
        line.setAttribute("x2", cx);
        line.setAttribute("y2", cy);
        pin.setAttribute("r", r * 0.28);
      }
    }
  };
  // The schools' names, placed so none overlaps a dot or another name: the picked team's first, then
  // its region's, then the rest in view.
  const labels = new Map([...svg.querySelectorAll(".map-label")].map((t) => [t.dataset.team, t]));
  const leaders = new Map([...svg.querySelectorAll(".map-leader")].map((l) => [l.dataset.team, l]));
  const labelDots = (r, size) => {
    const inView = (s) => s.x >= view.x && s.x <= view.x + view.w && s.y >= view.y && s.y <= view.y + view.h;
    // (On a county's map, its own schools before their region-mates elsewhere.)
    const first = (s) => (s.slug === current?.slug ? 0 : current && groupOf(s) === groupOf(current) ? 1 : layer.away(s) ? 3 : 2);
    const points = [...bySlug.values()].filter((s) => s.x != null && inView(s))
      .sort((a, b) => first(a) - first(b) || byName(a.school, b.school))
      .map((s) => ({ slug: s.slug, x: pillAt.get(s.slug)?.[0] ?? s.x, y: pillAt.get(s.slug)?.[1] ?? s.y, name: s.school }));
    const spots = placeLabels(points, r, size, { x0: view.x, y0: view.y, x1: view.x + view.w, y1: view.y + view.h });
    for (const [slug, t] of labels) {
      const spot = spots[slug];
      t.toggleAttribute("hidden", !spot);
      if (!spot) continue;
      t.setAttribute("x", spot.x);
      t.setAttribute("y", spot.y);
      t.setAttribute("text-anchor", spot.anchor);
      t.setAttribute("font-size", size);
      t.style.strokeWidth = `${size * 0.28}px`;
      const line = leaders.get(slug);
      line?.toggleAttribute("hidden", !spot.line);
      if (line && spot.line) ["x1", "y1", "x2", "y2"].forEach((k, i) => line.setAttribute(k, spot.line[i]));
    }
    for (const [slug, l] of leaders) if (!spots[slug]) l.setAttribute("hidden", "");
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
  // The county under a spot on the map (map units), as its outline's path, or null.
  const countyAt = (x, y) => [...svg.querySelectorAll(".map-county")].find((c) => c.isPointInFill?.(new DOMPoint(x, y))) ?? null;
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
    svg.querySelector(".map-county-other")?.setAttribute("d", "");
    for (const g of svg.querySelectorAll(".map-dot")) {
      g.classList.toggle("is-picked", Boolean(school) && g.dataset.team === school.slug);
      g.classList.toggle("is-dim", Boolean(school) && g.dataset.group !== groupOf(school));
    }
    for (const p of svg.querySelectorAll(".map-region, .map-label, .map-leader, .map-pins > g")) p.classList.toggle("is-dim", Boolean(school) && p.dataset.group !== groupOf(school));
    svg.classList.toggle("has-pick", Boolean(school));
    for (const a of root.querySelectorAll(".regions-list [data-team]")) {
      if (school && a.dataset.team === school.slug) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    }
    if (caption) {
      // A team not on this map (Compare: picked on the other one) says where it is instead.
      const html = school ? pickedHtml(school, payload, teams, layer.color(school), href, layer.chip?.(school)) : slug && elsewhere ? elsewhere(slug) : "";
      caption.innerHTML = html;
      caption.hidden = !html;
      if (school && reveal) show(caption);
    }
    if (status) status.textContent = school ? `${school.school}: ${place(school)}` : "";
    // Another team in the region already shown, its dot in view: the map stays where it is.
    const stay = school && current && groupOf(current) === groupOf(school) && school.x != null
      && school.x >= view.x && school.x <= view.x + view.w && school.y >= view.y && school.y <= view.y + view.h;
    current = school;
    const box = school && boxes.get(groupOf(school));
    // (A county's map stays on the county: its picked school's region is lit, running off its edges.)
    if (zoom && !stay && !layer.pill) {
      view = box ? regionView(box, base) : start();
      moves += 1;
    }
    apply(); // the names, too: the picked team's first
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
      const d = (dot.querySelector("rect") ?? dot.firstChild).getBoundingClientRect(); // (a pill's shape, not its pin line)
      hover.innerHTML = hoverHtml(school, teams[school.school], payload.seasons ?? [], layer.color(school), layer.chip?.(school));
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
    // A county's map: a tap on another county, off the schools, shows that county and a link to it
    // (*otherCounty*: its name to the panel's markup); it doesn't leave the page.
    const other = !dot && otherCounty ? countyAt(...toMap(e.clientX, e.clientY)) : null;
    if (other && other.dataset.county !== layer.county) {
      pick(null, { zoom: false });
      onPick(null, "map");
      svg.querySelector(".map-county-other")?.setAttribute("d", other.getAttribute("d"));
      if (caption) {
        caption.innerHTML = otherCounty(other.dataset.county);
        caption.hidden = false;
        show(caption);
      }
      if (status) status.textContent = other.dataset.county + " County";
      return;
    }
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

// ------------------------------------------------------------- counties
// The Counties pages (/maps/counties/hinds): one county's MHSAA schools, whatever their classes, each
// with its region; and /maps/counties, every county to pick one. A school's county is the county its
// campus is in (backend/helpers/region_map.py county_of), in each season's data.

export const MHSAA_NOTE = "Only schools in the MHSAA (Mississippi High School Activities Association) are shown.";

/** "/maps/counties/jefferson-davis" (or "/maps/counties", every county). */
export function countiesPath(county = null) {
  return county ? `/maps/counties/${slugify(county)}` : "/maps/counties";
}

/** "Hinds County". */
export function countyTitle(county) {
  return `${county} County`;
}

/** Home › Counties › Hinds County (or Home › Counties). */
export function countiesTrail(county = null) {
  const trail = [["Home", "/"], ["Counties", countiesPath()]];
  return county ? [...trail, [countyTitle(county), countiesPath(county)]] : trail;
}

// The colors a county's place takes when its own is taken, in order: the ones least like the others
// first (blue, green, purple), so two places never end up red and orange (8 and 2) side by side.
const PLACE_FALLBACK = [1, 3, 7, 4, 5, 6, 2, 8];

/**
 * The places (a region in a class) a county's *schools* are in, highest class first, each with a color
 * (1-8): its region's own, unless another of the county's places already has it (two regions with the
 * same number in different classes), then the first of PLACE_FALLBACK not in use. [{ key, clazz, region,
 * color }].
 */
export function countyPlaces(schools) {
  const seen = new Map();
  for (const s of [...schools].sort((a, b) => b.class - a.class || a.region - b.region)) {
    const key = `${s.class}-${s.region}`;
    if (!seen.has(key)) seen.set(key, { key, clazz: s.class, region: s.region });
  }
  const used = new Set();
  for (const p of seen.values()) {
    const own = ((p.region - 1) % 8) + 1;
    p.color = !used.has(own) ? own : PLACE_FALLBACK.find((c) => !used.has(c)) ?? own;
    used.add(p.color);
  }
  return [...seen.values()];
}

// Each class's hue on a county's map (the region colors' slots: 7A blue, 6A green, 5A orange, 4A purple,
// 3A yellow, 2A pink, 1A red). A county's regions in one class are shades of it.
export const CLASS_HUE = { 7: 1, 6: 3, 5: 2, 4: 7, 3: 4, 2: 5, 1: 8 };

/**
 * The shade of each of a county's places (a region in a class: "6-3"): its class's hue, lighter for its
 * lower-numbered regions there and darker for its higher (one region: the hue itself). { key -> { tone
 * (0 lightest .. 1 darkest, 0.5 the hue), fill (a CSS color, the theme's), ink (its text's color) } }.
 */
export function countyShades(schools) {
  const out = new Map();
  const places = countyPlaces(schools);
  for (const c of new Set(places.map((p) => p.clazz))) {
    const list = places.filter((p) => p.clazz === c).sort((a, b) => a.region - b.region);
    list.forEach((p, i) => {
      const tone = list.length === 1 ? 0.5 : i / (list.length - 1);
      const hue = `var(--region-${CLASS_HUE[c]})`;
      const fill = tone < 0.5 ? `color-mix(in srgb, ${hue} ${Math.round(55 + 90 * tone)}%, #fff)`
        : tone > 0.5 ? `color-mix(in srgb, ${hue} ${Math.round(100 - 60 * (tone - 0.5))}%, #000)` : hue;
      out.set(p.key, { tone, fill, ink: tone < 0.34 ? "#1B1B1B" : "#FFFFFF" });
    });
  }
  return out;
}

/** countyShades as a plain object (for the parity test against region_pages.county_shades). */
export function countyShadesObject(schools) {
  return Object.fromEntries(countyShades(schools));
}

/** A school's place as a pill in its shade: "3-6A". */
export function countyPill(school, shade) {
  return `<span class="county-pill" style="background:${shade.fill};color:${shade.ink}" aria-hidden="true">${school.region}-${school.class}A</span>`;
}

/**
 * A county's map: its own schools only, each a pill ("3-6A") in its place's shade (countyShades), always
 * named, and their regions' shapes (the schools elsewhere in them aren't drawn).
 */
export function countyLayer(payload, county) {
  const mine = payload.schools.filter((s) => s.county === county);
  const shades = countyShades(mine);
  const key = (s) => `${s.class}-${s.region}`;
  return {
    schools: mine,
    group: key,
    color: () => 0,
    shade: (s) => shades.get(key(s)),
    mark: (s) => `${s.region}-${s.class}A`,
    chip: (s) => countyPill(s, shades.get(key(s))),
    pill: true,
    named: true,
    spread: true,
    away: () => false,
    shapes: countyPlaces(mine).map((p) => {
      const r = payload.regions[String(p.clazz)]?.[String(p.region)];
      return r && { group: p.key, color: 0, fill: shades.get(p.key).fill, d: r.d, box: r.box };
    }).filter(Boolean),
    county,
    label: `Map of Mississippi with ${countyTitle(county)}'s MHSAA schools, each marked with its region and class`,
  };
}

/** The box (in map units) around an SVG path of absolute points ("M0,1L2,3…Z"). */
export function pathBox(d) {
  const nums = String(d).match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
  const xs = nums.filter((_, i) => i % 2 === 0);
  const ys = nums.filter((_, i) => i % 2 === 1);
  return xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] : null;
}

/**
 * A county's mark, as a team's helmet is its: its outline (map.json's simpler *icon*, else its full
 * outline), *size* pixels square, filled in its *shade* (countShade) or, without one, the site's color.
 */
export function countyMark(base, county, { size = 24, shade = null } = {}) {
  const c = base.counties.find((x) => x.name === county);
  if (!c) return "";
  const d = c.icon ?? c.d;
  const [x0, y0, x1, y1] = pathBox(d);
  const pad = Math.max(x1 - x0, y1 - y0) * 0.06;
  const box = [x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad].map((v) => Math.round(v * 10) / 10);
  const fill = shade == null ? "county-mark--site" : `county-shade--${shade}`;
  return `<svg class="mark county-mark ${fill}" viewBox="${box.join(" ")}" width="${size}" height="${size}" aria-hidden="true"><path d="${d}"/></svg>`;
}

/**
 * Where a county's map starts: the county, with room around it for its schools' names (its regions run
 * on past the edges; "Show the whole state" shows them whole). Null for a county the map doesn't have.
 */
export function countyHome(base, county) {
  const c = base.counties.find((x) => x.name === county);
  return c ? pathBox(c.d) : null;
}

/** "9 MHSAA schools", "1 MHSAA school", "No MHSAA schools". */
export function schoolsCount(n) {
  return n ? `${n} MHSAA ${n === 1 ? "school" : "schools"}` : "No MHSAA schools";
}

/** "9 MHSAA schools in 4 classes", "1 MHSAA school", "No MHSAA schools". */
export function countyCount(schools) {
  const classes = new Set(schools.map((s) => s.class)).size;
  return `${schoolsCount(schools.length)}${classes > 1 ? ` in ${classes} classes` : ""}`;
}

/** The county's schools by class, highest first: each a row that picks it, with its region and town. */
export function countyLists(county, payload, teams = {}) {
  const mine = payload.schools.filter((s) => s.county === county);
  const shades = countyShades(mine);
  const classes = [...new Set(mine.map((s) => s.class))].sort((a, b) => b - a);
  return classes.map((c) => {
    const rows = mine.filter((s) => s.class === c)
      .sort((a, b) => a.region - b.region || byName(a.school, b.school))
      .map((s) => `<li><a class="regions-list__row" href="${esc(countiesPath(county))}?team=${esc(s.slug)}" data-team="${esc(s.slug)}">`
        + `${teamMark(s.school, teams[s.school])}<span class="regions-list__team">${esc(s.school)}</span>`
        + `<span class="regions-list__was">${countyPill(s, shades.get(`${s.class}-${s.region}`))}`
        + `<span class="visually-hidden">${esc(place(s))}</span>${s.city ? esc(s.city) : ""}</span></a></li>`);
    return `<section class="regions-list__region county-list__class"><div class="regions-list__head">`
      + `<h2 class="regions-list__name">Class ${c}A</h2>`
      + `<a class="regions-list__standings" href="${esc(regionsPath(c))}">Class ${c}A regions<span aria-hidden="true"> ›</span></a></div>`
      + `<ul>${rows.join("")}</ul></section>`;
  }).join("");
}

/** The county page's heading: breadcrumbs, the title (with the county's mark), how many schools and the
 * seasons, and whose. */
export function countyHeader(county, payload, base, share = "") {
  const mine = payload.schools.filter((s) => s.county === county);
  return `${breadcrumbs(countiesTrail(county))}<div class="title-row"><h1 class="title county-title">`
    + `${countyMark(base, county, { size: 44 })}<span>${esc(countyTitle(county))}</span></h1>${share}</div>`
    + `<p class="regions-sub">${esc(countyCount(mine))}, ${esc(seasonsLabel(payload.seasons))}</p>`
    + `<p class="county-note muted">${esc(MHSAA_NOTE)}</p>`;
}

/** The county page: heading and controls, its map and its schools by class (or why there are none). */
export function countyPage(county, base, payload, { controls = "", share = "", teams = {}, views = "" } = {}) {
  const mine = payload.schools.filter((s) => s.county === county);
  const head = `<header class="entry-head">${countyHeader(county, payload, base, share)}${views}${controls}`;
  if (!mine.length) {
    return `<div class="page regions-page county-page">${head}</header>`
      + `<p class="notice">No MHSAA school is in ${esc(countyTitle(county))} in the ${esc(seasonsLabel(payload.seasons))}. `
      + `<a href="${esc(countiesPath())}">Pick another county</a>.</p>${countyNearby(base, county, payload)}</div>`;
  }
  const layer = countyLayer(payload, county);
  return `<div class="page regions-page county-page">${head}`
    + `<p class="focus-note muted regions-note">Each school is marked with its region and class (3-6A), in its class's color: lighter and darker for its regions. Pick one to see its region.</p></header>`
    + `<div class="regions-layout">${mapFigure(base, payload, null, { layer, after: countyNearby(base, county, payload) })}`
    + `<div class="regions-side"><div class="regions-list county-list">${countyLists(county, payload, teams)}</div></div></div></div>`;
}

/**
 * The counties next to *county* (map.json's *neighbors*), each a link with its mark shaded by its count
 * of schools, as on the statewide map. Nothing when map.json has no neighbors (one written before it
 * had them).
 */
export function countyNearby(base, county, payload) {
  const near = base.counties.find((c) => c.name === county)?.neighbors ?? [];
  if (!near.length) return "";
  const counts = countyCounts(base, payload);
  return `<nav class="county-nearby" aria-labelledby="county-nearby">`
    + `<p class="county-nearby__label" id="county-nearby">Nearby counties</p><ul class="county-nearby__list">`
    + near.map((n) => `<li><a href="${esc(countiesPath(n))}" data-county="${esc(n)}" aria-label="${esc(countyTitle(n))}: ${esc(schoolsCount(counts[n] ?? 0))}">`
      + `${countyMark(base, n, { size: 24, shade: countShade(counts[n] ?? 0) })}<span>${esc(n)}</span></a></li>`).join("")
    + "</ul></nav>";
}

/**
 * Another county tapped on a county's map: its mark and name, its count of schools (and that it's next
 * to *county*, when it is), and a link to its page.
 */
export function countyJumpHtml(base, name, county, count) {
  const next = base.counties.find((c) => c.name === county)?.neighbors?.includes(name);
  return `<div class="county-jump"><div><div class="picked__head">${countyMark(base, name, { size: 28, shade: countShade(count) })}`
    + `<span class="picked__name">${esc(countyTitle(name))}</span></div>`
    + `<p class="picked__facts">${esc(schoolsCount(count))}${next ? ` · next to ${esc(countyTitle(county))}` : ""}</p></div>`
    + `<a class="county-jump__open" href="${esc(countiesPath(name))}" data-county="${esc(name)}">Open ${esc(countyTitle(name))}${MAP_ICONS.next}</a></div>`;
}

/** How many of the season's schools each county has, by county name (every county, 0 for none). */
export function countyCounts(base, payload) {
  const counts = Object.fromEntries(base.counties.map((c) => [c.name, 0]));
  for (const s of payload.schools) if (s.county in counts) counts[s.county] += 1;
  return counts;
}

/** A count's shade on the statewide map: 0 (none), 1, 2, 3 (3 or 4), 4 (5 or more). */
export function countShade(n) {
  return n === 0 ? 0 : n === 1 ? 1 : n === 2 ? 2 : n <= 4 ? 3 : 4;
}

const SHADES = [["None", 0], ["1", 1], ["2", 2], ["3–4", 3], ["5 or more", 4]];

/** The statewide map: every county a link, shaded by how many MHSAA schools it has. */
export function countiesMapSvg(base, counts) {
  const v = wholeView(base);
  const shapes = base.counties.map((c) => {
    const n = counts[c.name] ?? 0;
    return `<a class="county-pick" href="${esc(countiesPath(c.name))}" data-county="${esc(c.name)}" aria-label="${esc(countyTitle(c.name))}: ${esc(schoolsCount(n))}">`
      + `<path class="county-pick__shape county-shade--${countShade(n)}" d="${c.d}"/></a>`;
  }).join("");
  const names = base.counties.map((c) => `<text class="county-pick__name" x="${c.label[0]}" y="${c.label[1]}">${esc(c.name)}</text>`).join("");
  return `<svg class="counties-map__svg" viewBox="${v.x} ${v.y} ${v.w} ${v.h}" role="group" aria-label="Mississippi's counties, each shaded by how many MHSAA schools it has">`
    + `<g class="county-picks">${shapes}</g><path class="map-state" d="${base.state}"/>`
    // The county pointed at (or focused), outlined over its neighbors (an SVG draws in order: a county's
    // own outline would be under those drawn after it).
    + `<path class="county-pick__ring" d="" aria-hidden="true"/>`
    + `<g class="county-pick__names" aria-hidden="true">${names}</g></svg>`;
}

/** The statewide page: heading and controls, the map with its key, and every county as a list. */
export function countiesPage(base, payload, { controls = "", share = "" } = {}) {
  const counts = countyCounts(base, payload);
  const key = SHADES.map(([label, shade]) => `<li><span class="county-shade-key county-shade--${shade}" aria-hidden="true"></span>${esc(label)}</li>`).join("");
  const list = countiesList(base, counts);
  return `<div class="page regions-page counties-page"><header class="entry-head">${breadcrumbs(countiesTrail())}`
    + `<div class="title-row"><h1 class="title">Counties</h1>${share}</div>`
    + `<p class="regions-sub">Each county's MHSAA schools, ${esc(seasonsLabel(payload.seasons))}</p>`
    + `<p class="county-note muted">${esc(MHSAA_NOTE)}</p>${controls}`
    + `<p class="focus-note muted regions-note">Pick a county on the map or in the list to see its schools, their classes and their regions.</p></header>`
    + `<div class="regions-layout"><figure class="regions-map counties-map"><div class="regions-map__frame counties-map__frame">${countiesMapSvg(base, counts)}`
    + `<div class="regions-map__hover" aria-hidden="true" hidden></div></div>`
    + `<figcaption class="counties-map__key"><span>MHSAA schools in the county:</span><ul>${key}</ul></figcaption></figure>`
    + `<div class="regions-side"><h2 class="counties-list__title">Every county</h2>${list}</div></div></div>`;
}

/** Every county, by name: a row each with its mark (in its shade on the map) and its MHSAA schools. */
export function countiesList(base, counts) {
  const rows = [...base.counties].sort((a, b) => byName(a.name, b.name)).map((c) => {
    const n = counts[c.name] ?? 0;
    return `<li><a class="regions-list__row county-row${n ? "" : " is-empty"}" href="${esc(countiesPath(c.name))}" data-county="${esc(c.name)}">`
      + `${countyMark(base, c.name, { size: 28, shade: countShade(n) })}<span class="regions-list__team">${esc(c.name)}</span>`
      + `<span class="regions-list__was">${esc(schoolsCount(n))}</span></a></li>`;
  });
  return `<ul class="counties-list">${rows.join("")}</ul>`;
}

// ------------------------------------------------------------- a county's Compare and Timeline

/** A county page's heading for its Compare and Timeline: breadcrumbs, the title with its mark, *line*. */
export function countyViewHeader(county, base, line, share = "") {
  return `${breadcrumbs(countiesTrail(county))}<div class="title-row"><h1 class="title county-title">`
    + `${countyMark(base, county, { size: 44 })}<span>${esc(countyTitle(county))}</span></h1>${share}</div>`
    + `<p class="regions-sub">${esc(line)}</p><p class="county-note muted">${esc(MHSAA_NOTE)}</p>`;
}

/**
 * What changed in a county between two seasons: *a* and *b* are { label, season, payload }, in either
 * order. Each of the county's schools in either season, in groups: in the newer season only (new, or
 * formed from schools merged into it), in the older only (gone, or now part of another), changed class
 * or region, and the same. A renamed school is the same school (Leake Central, then Leake). Each row is
 * { school, slug, season, older, newer, note }: its name and season to pick it by, and its places then
 * ({class, region}, or null). Null when both are the same season.
 */
export function countyChanges(a, b, county) {
  if (a.season === b.season) return null;
  const [older, newer] = a.season < b.season ? [a, b] : [b, a];
  const thenAll = new Map(older.payload.schools.map((s) => [s.school, s]));
  const nowAll = new Map(newer.payload.schools.map((s) => [s.school, s]));
  const groups = { in: [], out: [], moved: [], same: [] };
  const seen = new Set();
  const at = (s) => ({ class: s.class, region: s.region });
  for (const s of newer.payload.schools.filter((x) => x.county === county)) {
    const was = namesIn(s.school, newer.season, older.season).map((n) => thenAll.get(n)).filter(Boolean);
    was.forEach((w) => seen.add(w.school));
    const row = { school: s.school, slug: s.slug, season: newer.season, older: null, newer: at(s), note: null };
    if (was.length === 1) {
      row.older = at(was[0]);
      (was[0].class === s.class && was[0].region === s.region ? groups.same : groups.moved).push(row);
    } else {
      row.note = was.length > 1 ? `Formed from ${was.map((w) => `${w.school} (${shortPlace(w)})`).join(" and ")}`
        : s.successor_of ? `New school, on ${s.successor_of}’s campus` : `Not in a region in ${older.label}`;
      groups.in.push(row);
    }
  }
  for (const s of older.payload.schools.filter((x) => x.county === county && !seen.has(x.school))) {
    const now = namesIn(s.school, older.season, newer.season).map((n) => nowAll.get(n)).find(Boolean);
    groups.out.push({ school: s.school, slug: s.slug, season: older.season, older: at(s), newer: null,
      note: now ? `Now part of ${now.school}` : `Not in a region in ${newer.label}` });
  }
  for (const list of Object.values(groups)) list.sort((x, y) => byName(x.school, y.school));
  return { older, newer, groups };
}

/** The list under a county's two maps: what changed between them, each school picking it on both maps. */
export function countyChangesHtml(changes, county, teams = {}) {
  if (!changes) return `<p class="focus-note muted">Both maps show the same season, so nothing changed between them.</p>`;
  const { older, newer, groups } = changes;
  const detail = {
    in: (r) => `${place(r.newer)} · ${r.note}`,
    out: (r) => `${place(r.older)} in ${older.label} · ${r.note}`,
    moved: (r) => `${place(r.older)} → ${place(r.newer)}`,
    same: (r) => place(r.newer),
  };
  const titles = { in: `In ${newer.label} only`, out: `In ${older.label} only`, moved: "Changed class or region", same: "Same class and region" };
  const row = (key) => (r) => `<li><a class="compare-changes__row" href="?team=${esc(r.slug)}" data-team="${esc(r.slug)}" data-school="${esc(r.school)}" data-season="${esc(r.season)}">`
    + `${teamMark(r.school, teams[r.school])}<span class="compare-changes__team">${esc(r.school)}</span>`
    + `<span class="compare-changes__detail">${esc(detail[key](r))}</span></a></li>`;
  const group = (key) => {
    const list = groups[key];
    if (!list.length) return "";
    const body = `<ul>${list.map(row(key)).join("")}</ul>`;
    const head = `${esc(titles[key])} <span class="compare-changes__count">${list.length}</span>`;
    return key === "same"
      ? `<details class="compare-changes__group"><summary><h3>${head}</h3></summary>${body}</details>`
      : `<section class="compare-changes__group"><h3>${head}</h3>${body}</section>`;
  };
  const counts = ["in", "out", "moved"].reduce((n, k) => n + groups[k].length, 0);
  return `<h2 class="compare-changes__title">What changed in ${esc(countyTitle(county))} from ${esc(older.label)} to ${esc(newer.label)}</h2>`
    + (counts ? "" : `<p class="focus-note muted">Nothing changed: every school is in the same class and region in both.</p>`)
    + `<div class="compare-changes__groups">${["in", "out", "moved", "same"].map(group).join("")}</div>`;
}

/** One side of a county's Compare: its season picker over its map (*side* "a" or "b"). */
export function countyCompareSide(side, base, option, payload, county, index, name) {
  const seasons = index.options.map((o) => `<option value="${esc(o.season)}"${o.season === option.season ? " selected" : ""}>${esc(o.label)}</option>`).join("");
  const mine = payload.schools.filter((s) => s.county === county);
  const map = mine.length
    ? mapFigure(base, payload, null, { full: false, layer: countyLayer(payload, county) })
    : `<p class="notice">No MHSAA school was in ${esc(countyTitle(county))} in ${esc(option.label)}.</p>`;
  return `<section class="compare__side" data-side="${side}" aria-label="${name}">`
    + `<div class="compare__pickers"><label><span class="visually-hidden">${name}: seasons</span>`
    + `<select class="select-box" data-control="compare-season" data-side="${side}">${seasons}</select></label>`
    + `<span class="compare__count muted">${esc(schoolsCount(mine.length))}</span></div>${map}</section>`;
}

/** A county's Compare: two seasons of its map side by side, the older first, and what changed. */
export function countyComparePage(county, base, a, b, index, { controls = "", share = "", teams = {}, views = "" } = {}) {
  const changes = countyChanges(
    { label: a.option.label, season: a.option.season, payload: a.payload },
    { label: b.option.label, season: b.option.season, payload: b.payload },
    county,
  );
  const [first, second] = b.option.season < a.option.season ? [{ ...b, key: "b" }, { ...a, key: "a" }] : [{ ...a, key: "a" }, { ...b, key: "b" }];
  return `<div class="page regions-page regions-page--compare county-page"><header class="entry-head">`
    + countyViewHeader(county, base, `${first.option.label} vs. ${second.option.label}`, share)
    + `${views}${controls}<p class="focus-note muted regions-note">Pick a school on either map, or in the list under them, to see where it is on both.</p></header>`
    + `<div class="compare">${[first, second].map((x, i) => countyCompareSide(x.key, base, x.option, x.payload, county, index, `Map ${i + 1}`)).join("")}</div>`
    + `<section class="compare-changes" aria-label="What changed">${countyChangesHtml(changes, county, teams)}</section></div>`;
}

/**
 * The county's schools, season by season: a row for each school (by its newest name; a school merged
 * into another keeps its own row), a column for each season (*seasons*: [{ option, payload }], oldest
 * first), each cell its region then, in that season's map's color, or a dash.
 */
export function countyTimelineTable(county, seasons, teams = {}) {
  const newest = seasons[seasons.length - 1]?.option.season;
  const names = [];
  for (const s of seasons) {
    for (const r of s.payload.schools) {
      if (r.county !== county) continue;
      const name = nameIn(r.school, s.option.season, newest);
      if (!names.includes(name)) names.push(name);
    }
  }
  names.sort(byName);
  const shades = seasons.map((s) => countyShades(s.payload.schools.filter((r) => r.county === county)));
  const head = `<tr><th scope="col">School</th>${seasons.map((s) => `<th scope="col">${esc(s.option.label)}</th>`).join("")}</tr>`;
  const body = names.map((name) => {
    const cells = seasons.map((s, i) => {
      const r = s.payload.schools.find((x) => x.county === county && x.school === nameIn(name, newest, s.option.season));
      return r
        ? `<td><span class="timeline-table__place">${countyPill(r, shades[i].get(`${r.class}-${r.region}`))}<span class="visually-hidden">${esc(place(r))}</span></span></td>`
        : `<td><span class="muted" aria-label="Not on the list">—</span></td>`;
    }).join("");
    // A merger, said where the rows end and begin: "Part of North Tippah from 2027", "From Walnut and Falkner".
    const merged = SCHOOL_CONSOLIDATIONS.find(([, , members]) => members.includes(nameIn(name, newest, 0)) || members.includes(name));
    const formed = SCHOOL_CONSOLIDATIONS.find(([school]) => school === name);
    const note = formed ? `From ${formed[2].join(" and ")}, ${formed[1]}`
      : merged && merged[0] !== name ? `Part of ${merged[0]} from ${merged[1]}` : "";
    return `<tr><th scope="row"><span class="timeline-table__mate">${teamMark(name, teams[name], { size: 18 })}${esc(name)}</span>`
      + `${note ? `<span class="timeline-table__note muted">${esc(note)}</span>` : ""}</th>${cells}</tr>`;
  }).join("");
  return `<div class="timeline-table__wrap"><table class="timeline-table county-timeline-table"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}

/** A county's Timeline: its map each season, oldest first, and its schools season by season. */
export function countyTimelinePage(county, base, seasons, { controls = "", share = "", views = "", teams = {} } = {}) {
  const span = timelineSpan(seasons);
  return `<div class="page regions-page regions-page--timeline county-page"><header class="entry-head">`
    + countyViewHeader(county, base, span, share)
    + `${views}${controls}<p class="focus-note muted regions-note">Each map is ${esc(countyTitle(county))} that season: each school marked with its region and class, in its class's color. Pick a school to see its region.</p></header>`
    + `<div class="timeline">${seasons.map((s, i) => {
      const n = s.payload.schools.filter((r) => r.county === county).length;
      const map = n ? mapFigure(base, s.payload, null, { full: false, layer: countyLayer(s.payload, county) })
        : `<p class="notice">No MHSAA school in ${esc(s.option.label)}.</p>`;
      return `<section class="timeline__season" data-season="${s.option.season}" data-index="${i}">`
        + `<h2 class="timeline__label">${esc(s.option.label)} <span class="timeline__class">${esc(schoolsCount(n))}</span></h2>${map}</section>`;
    }).join("")}</div>`
    + `<h2 class="timeline-table__title">${esc(countyTitle(county))}, season by season</h2>${countyTimelineTable(county, seasons, teams)}`
    + "</div>";
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
