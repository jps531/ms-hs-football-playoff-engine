// The Maps and Counties pages' share sheet: one sheet for every view, the same rows in the same order.
// Share (a dropdown: the class or a team; every county or one), Show (One season | Compare | Timeline),
// Season (which season, which two, or every season on the Timeline) and Theme. Every option names an
// image the share-assets step draws (backend/prefect/share_regions.py); one it doesn't draw is greyed
// out, with a note saying why.

import { countyTitle, nameIn, place, seasonsLabel } from "./regions.js";
import { buildPath, slugify } from "./routes.js";

export const MAP_VIEWS = [
  { key: "season", label: "One season" },
  { key: "compare", label: "Compare" },
  { key: "timeline", label: "Timeline" },
];

/** The seasons a Timeline covers, oldest to newest: { from, to } (every choice's seasons). */
function span(index) {
  const all = index.options.flatMap((o) => o.seasons ?? [o.season]);
  return { from: Math.min(...all), to: Math.max(...all) };
}

/** "Every season, 2025 to 2028" (the Timeline's one choice) and "2025 to 2028 seasons" (its line). */
function spanLabels(index) {
  const { from, to } = span(index);
  return from === to
    ? { option: `Every season, ${from}`, line: `${from} season` }
    : { option: `Every season, ${from} to ${to}`, line: `${from} to ${to} seasons` };
}

/** The choices newest first. */
const newestFirst = (index) => [...index.options].sort((a, b) => b.season - a.season);

/**
 * The share sheet's model for a Maps page: *index* (regions/index.json), *payloads* (season -> its
 * regions/{season}.json) and the page's *classes* (one, or Compare's two). A team is any school that
 * was in one of those classes in some season, under its newest name; each image is drawn as the
 * share-assets step draws it, so an option is offered only when its file exists.
 */
export function regionsShareModel(index, payloads, classes) {
  const options = newestFirst(index);
  const newest = options[0].season;
  const rows = (season) => payloads[season]?.schools ?? [];
  // The season before *o* that its comparison is drawn against: the choice whose season is the year before.
  const before = (o) => options.find((b) => b.season === o.season - 1) ?? null;
  const teams = new Map();
  for (const o of options) {
    for (const r of rows(o.season)) {
      if (!classes.includes(r.class)) continue;
      const name = nameIn(r.school, o.season, newest);
      if (!teams.has(name)) teams.set(name, name);
    }
  }
  const subjects = [
    ...classes.map((c) => ({ key: `class:${c}`, label: `Class ${c}A, every region` })),
    ...[...teams.keys()].sort((a, b) => a.localeCompare(b)).map((name) => ({ key: `team:${name}`, label: name })),
  ];
  // A team's row in a season, by the name it had then.
  const rowOf = (name, season) => rows(season).find((r) => r.school === nameIn(name, newest, season)) ?? null;
  const is = (c) => {
    const [kind, ...rest] = c.subject.split(":");
    const value = rest.join(":");
    return kind === "class" ? { clazz: Number(value) } : { team: value };
  };
  const labels = spanLabels(index);

  /** Whether *view* has an image for *subject* in choice *o* (or at all, for the Timeline). */
  const has = (subject, view, o) => {
    const { clazz, team } = subject;
    if (view === "timeline") {
      return clazz != null
        ? options.some((x) => rows(x.season).some((r) => r.class === clazz))
        : options.some((x) => rowOf(team, x.season));
    }
    const prior = view === "compare" ? before(o) : null;
    if (view === "compare" && !prior) return false;
    if (clazz != null) {
      const here = rows(o.season).some((r) => r.class === clazz);
      return view === "season" ? here : here && rows(prior.season).some((r) => r.class === clazz);
    }
    const row = rowOf(team, o.season);
    if (view === "season") return Boolean(row);
    return Boolean(row && rows(prior.season).some((r) => r.school === nameIn(row.school, o.season, prior.season)));
  };
  const seasonsFor = (view) => (view === "compare" ? options.filter((o) => before(o)) : options);
  const subjectName = (s) => (s.clazz != null ? `Class ${s.clazz}A` : s.team);

  return {
    subjects,
    views: MAP_VIEWS,
    /** The Season row's options for *c*'s view: each season (or pair) with whether it has an image. */
    seasons(c) {
      const s = is(c);
      if (c.view === "timeline") return [{ key: "all", label: labels.option, disabled: !has(s, "timeline") }];
      return seasonsFor(c.view).map((o) => ({
        key: String(o.season),
        label: c.view === "compare" ? `${before(o).label} vs. ${o.label}` : o.label,
        disabled: !has(s, c.view, o),
      }));
    },
    /** Each view, greyed out when the subject has no image in it at all. */
    viewOptions(c) {
      const s = is(c);
      return MAP_VIEWS.map((v) => ({
        ...v,
        disabled: v.key === "timeline" ? !has(s, "timeline") : !seasonsFor(v.key).some((o) => has(s, v.key, o)),
      }));
    },
    /** Why a view is greyed out (under the Show row), or "". */
    viewNote(c) {
      const views = this.viewOptions(c).filter((v) => v.disabled).map((v) => v.label);
      if (!views.length) return "";
      const who = subjectName(is(c));
      return views.includes("Compare") && views.length === 1
        ? `${who} wasn’t in an MHSAA region in two seasons in a row.`
        : `No ${views.join(" or ")} image for ${who}.`;
    },
    /** Why a season is greyed out (under the Season row), or "". */
    seasonNote(c) {
      const off = this.seasons(c).filter((o) => o.disabled).map((o) => o.label);
      if (!off.length || c.view === "timeline") return "";
      const who = subjectName(is(c));
      return c.view === "compare"
        ? `${who} wasn’t in an MHSAA region in both seasons of ${off.join(" or ")}.`
        : `${who} wasn’t in an MHSAA region in ${off.join(" or ")}.`;
    },
    /** *c* moved to a view and season that have an image: the same season if it has one, else the newest that does. */
    fix(c) {
      let next = { ...c };
      const views = this.viewOptions(next);
      if (views.find((v) => v.key === next.view)?.disabled) next.view = views.find((v) => !v.disabled)?.key ?? next.view;
      if (next.view !== "timeline") {
        const seasons = this.seasons(next);
        if (!seasons.find((o) => o.key === next.season && !o.disabled)) next.season = seasons.find((o) => !o.disabled)?.key ?? next.season;
      }
      return next;
    },
    /** The image under /static/regions/, without "-{theme}.png". */
    file(c) {
      const s = is(c);
      if (c.view === "timeline") return s.clazz != null ? `timeline/${s.clazz}a` : `timeline/team/${slugify(s.team)}`;
      const season = Number(c.season);
      if (s.clazz != null) return c.view === "compare" ? `${season}/compare/${s.clazz}a` : `${season}/${s.clazz}a`;
      const row = rowOf(s.team, season);
      return `${season}/${c.view === "compare" ? "compare" : "team"}/${row?.slug ?? slugify(s.team)}`;
    },
    /** The downloaded file's name, without ".png". */
    name(c) {
      const s = is(c);
      const who = s.clazz != null ? `class-${s.clazz}a` : slugify(s.team);
      if (c.view === "timeline") return `${who}-regions-timeline`;
      const o = options.find((x) => String(x.season) === c.season);
      return c.view === "compare" ? `${who}-regions-${before(o)?.season}-vs-${o.season}` : `${who}-regions-${o.season}`;
    },
    /** The image's description (its alt text, and the text it's shared with). */
    label(c) {
      const s = is(c);
      if (c.view === "timeline") return `${s.clazz != null ? `Class ${s.clazz}A` : `${s.team}’s`} regions, ${labels.line}`;
      const o = options.find((x) => String(x.season) === c.season);
      if (c.view === "compare") {
        return s.clazz != null
          ? `Class ${s.clazz}A regions, ${before(o).label} vs. ${o.label}`
          : `${s.team}: ${before(o).label} region vs. ${o.label} region`;
      }
      if (s.clazz != null) return `Class ${s.clazz}A regions, ${o.label}`;
      const row = rowOf(s.team, o.season);
      return `${s.team}: ${place(row)}, ${o.label}`;
    },
    title: (c) => `Share ${is(c).clazz != null ? `Class ${is(c).clazz}A’s` : `${is(c).team}’s`} regions`,
    /** The line under the title: the seasons the image shows. */
    when(c) {
      if (c.view === "timeline") return labels.line;
      const o = options.find((x) => String(x.season) === c.season);
      if (!o) return "";
      return c.view === "compare" ? `${before(o).label} vs. ${o.label}` : seasonsLabel(o.seasons);
    },
    /** The page the image is shared with: the Maps view that shows it. */
    page(c) {
      const s = is(c);
      const o = options.find((x) => String(x.season) === c.season);
      const season = c.view === "timeline" || !o ? null : o.season;
      // A team's map is its class's that season (its newest, on the Timeline).
      const row = s.team ? rowOf(s.team, season ?? newest) ?? options.map((x) => rowOf(s.team, x.season)).find(Boolean) : null;
      const clazz = s.clazz ?? row?.class;
      return buildPath(
        { page: "regions", clazz, view: c.view === "season" ? "map" : c.view, season, team: s.team ? slugify(s.team) : null },
        { regionsSeason: index.default },
      );
    },
    /** For the share event: { class, team, image } (image: "class" or "team", what's shared). */
    track(c) {
      const s = is(c);
      const row = s.team ? rowOf(s.team, Number(c.season)) : null;
      return { class: s.clazz ?? row?.class ?? null, team: s.team ?? null, image: s.team ? "team" : "class" };
    },
  };
}

/**
 * The share sheet's model for the Counties pages: every county's map (each season's; it has no
 * Compare or Timeline), or a county's own: a season, against the season before, or every season.
 * *counties* are the base map's county names.
 */
export function countiesShareModel(index, payloads, counties) {
  const options = newestFirst(index);
  const rows = (season, county) => (payloads[season]?.schools ?? []).filter((r) => r.county === county);
  // The choice holding the season before *o*'s (the counties' comparisons are drawn against it).
  const before = (o) => options.find((b) => (b.seasons ?? [b.season]).includes(o.season - 1)) ?? null;
  const named = counties.filter((county) => options.some((o) => rows(o.season, county).length));
  const subjects = [
    { key: "all", label: "Every county" },
    ...[...named].sort((a, b) => a.localeCompare(b)).map((county) => ({ key: `county:${county}`, label: countyTitle(county) })),
  ];
  const countyOf = (c) => (c.subject === "all" ? null : c.subject.slice("county:".length));
  const labels = spanLabels(index);
  const has = (county, view, o) => {
    if (!county) return view === "season";
    if (view === "timeline") return options.some((x) => rows(x.season, county).length);
    if (view === "season") return rows(o.season, county).length > 0;
    const prior = before(o);
    return Boolean(prior) && (rows(o.season, county).length > 0 || rows(prior.season, county).length > 0);
  };
  const seasonsFor = (view) => (view === "compare" ? options.filter((o) => before(o)) : options);

  return {
    subjects,
    views: MAP_VIEWS,
    seasons(c) {
      const county = countyOf(c);
      if (c.view === "timeline") return [{ key: "all", label: labels.option, disabled: !has(county, "timeline") }];
      return seasonsFor(c.view).map((o) => ({
        key: String(o.season),
        label: c.view === "compare" ? `${before(o).label} vs. ${o.label}` : o.label,
        disabled: !has(county, c.view, o),
      }));
    },
    viewOptions(c) {
      const county = countyOf(c);
      return MAP_VIEWS.map((v) => ({
        ...v,
        disabled: v.key === "timeline" ? !has(county, "timeline") : !seasonsFor(v.key).some((o) => has(county, v.key, o)),
      }));
    },
    viewNote(c) {
      return countyOf(c) ? "" : "Compare and Timeline are drawn for each county: pick one above.";
    },
    seasonNote(c) {
      const county = countyOf(c);
      const off = this.seasons(c).filter((o) => o.disabled).map((o) => o.label);
      if (!county || !off.length || c.view === "timeline") return "";
      return `${countyTitle(county)} had no MHSAA school in ${off.join(" or ")}.`;
    },
    fix(c) {
      let next = { ...c };
      const views = this.viewOptions(next);
      if (views.find((v) => v.key === next.view)?.disabled) next.view = views.find((v) => !v.disabled)?.key ?? next.view;
      if (next.view !== "timeline") {
        const seasons = this.seasons(next);
        if (!seasons.find((o) => o.key === next.season && !o.disabled)) next.season = seasons.find((o) => !o.disabled)?.key ?? next.season;
      }
      return next;
    },
    file(c) {
      const county = countyOf(c);
      if (!county) return `${c.season}/counties`;
      const slug = slugify(county);
      if (c.view === "timeline") return `timeline/county/${slug}`;
      return `${c.season}/${c.view === "compare" ? "county-compare" : "county"}/${slug}`;
    },
    name(c) {
      const county = countyOf(c);
      if (!county) return `mhsaa-schools-by-county-${c.season}`;
      const slug = slugify(county);
      if (c.view === "timeline") return `${slug}-county-timeline`;
      const o = options.find((x) => String(x.season) === c.season);
      return c.view === "compare" ? `${slug}-county-${before(o)?.season}-vs-${o.season}` : `${slug}-county-${o.season}`;
    },
    label(c) {
      const county = countyOf(c);
      const o = options.find((x) => String(x.season) === c.season);
      if (!county) return `MHSAA schools by county, ${o?.label ?? ""}`;
      if (c.view === "timeline") return `${countyTitle(county)}’s MHSAA schools, ${labels.line}`;
      return c.view === "compare"
        ? `${countyTitle(county)}: ${before(o).label} vs. ${o.label}`
        : `${countyTitle(county)}’s MHSAA schools and their regions, ${o.label}`;
    },
    title: (c) => (countyOf(c) ? `Share ${countyTitle(countyOf(c))}` : "Share the counties map"),
    when(c) {
      if (c.view === "timeline") return labels.line;
      const o = options.find((x) => String(x.season) === c.season);
      if (!o) return "";
      return c.view === "compare" ? `${before(o).label} vs. ${o.label}` : seasonsLabel(o.seasons);
    },
    page(c) {
      const county = countyOf(c);
      const season = c.view === "timeline" ? null : Number(c.season);
      return buildPath(
        { page: "counties", county: county ? slugify(county) : null, view: c.view === "season" ? "map" : c.view, season },
        { regionsSeason: index.default },
      );
    },
    /** For the share event: { county, image } (image: "counties", every county's, or "county"). */
    track(c) {
      return { county: countyOf(c), image: countyOf(c) ? "county" : "counties" };
    },
  };
}
