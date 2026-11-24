// URL shape: the path says what you're looking at, the query says how.
//   /                          landing (what the site does, and a featured race)
//   /standings/3a              every region in a class
//   /standings/3a/6            one region (Region 6-3A)
//   /brackets/3a               a class's playoff bracket
//   /maps/regions/3a           a class's regions on a map (/regions/3a, its first address, too)
//   /maps/regions/3a/compare   two of them side by side (?vs=2026&vsclass=4a: the second map's)
//   /maps/regions/3a/timeline  every season's, in order (?team=: following one school)
//   /maps/counties             every county, to pick one
//   /maps/counties/hinds       one county's schools, their classes and regions
//   /maps/counties/hinds/compare   two seasons of them side by side (?vs=2026: the second map's)
//   /maps/counties/hinds/timeline  every season's, in order
//   ?season=2025&week=9&odds=tossup&team=st-martin
// Defaults are left out of the URL (current season, latest week, Projected,
// no team), so a link to "now" is just the path. No DOM, so it runs under
// `node --test`.

export const CLASSES = [1, 2, 3, 4, 5, 6, 7];

/**
 * Team links from before a school's new name (backend/helpers/data_helpers.py
 * SCHOOL_RENAMES and SCHOOL_SUCCESSORS): an old ?team= slug finds the school by
 * its new name in a season where the old name isn't there ("leake-central" in
 * 2026 is Leake, "walnut" in 2027 is North Tippah).
 */
export const FORMER_SLUGS = { "leake-central": "Leake", "walnut": "North Tippah" };

/** "St. Martin" -> "st-martin", "D'Iberville" -> "diberville". */
export function slugify(name) {
  return String(name ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/['’.]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const positiveInt = (v) => (/^\d+$/.test(v ?? "") && Number(v) > 0 ? Number(v) : null);
const classFromSlug = (v) => {
  const m = /^([1-7])a$/i.exec(v ?? "");
  return m ? Number(m[1]) : null;
};

/**
 * Read a location into a route:
 * { page, clazz, region, season, week, odds, team, legacy }.
 * page is "landing", "class", "region", "bracket", "regions", "counties", "feedback", or "notfound"
 * (on "counties", county is the county's slug, or null for the statewide picker). team is the raw
 * `team` value (a slug, or a school name in an old link). legacy is true for
 * an old query-string link (?class=3&region=6) the app should rewrite.
 */
export function parseLocation(pathname, search) {
  const q = new URLSearchParams(search);
  const odds = q.get("odds");
  const route = {
    page: "notfound",
    clazz: null,
    region: null,
    season: positiveInt(q.get("season")),
    week: positiveInt(q.get("week")),
    odds: odds === "projected" || odds === "tossup" ? odds : null,
    team: q.get("team") || null,
    legacy: false,
    view: "map", // a map page's view: "map", "compare" or "timeline"
    vs: positiveInt(q.get("vs")), // compare: the second map's season (null: the one before the first's)
    vsClass: classFromSlug(q.get("vsclass")), // compare: the second map's class (null: the first's)
    county: null, // the Counties pages: the county's slug (null: the statewide picker)
  };
  const parts = pathname.replace(/\/+$/, "").split("/").filter(Boolean);

  if (parts.length === 0) {
    // Old links put everything in the query: /?class=3&region=6.
    const clazz = positiveInt(q.get("class"));
    if (CLASSES.includes(clazz)) {
      const region = positiveInt(q.get("region"));
      return { ...route, page: region ? "region" : "class", clazz, region, legacy: true };
    }
    return { ...route, page: "landing" };
  }
  if (parts[0] === "standings" && parts.length <= 3) {
    const clazz = classFromSlug(parts[1]);
    if (!clazz) return route;
    if (parts.length === 2) return { ...route, page: "class", clazz };
    const region = positiveInt(parts[2]);
    return region ? { ...route, page: "region", clazz, region } : route;
  }
  if (parts[0] === "feedback" && parts.length === 1) return { ...route, page: "feedback" };
  if (parts[0] === "brackets" && parts.length === 2) {
    const clazz = classFromSlug(parts[1]);
    return clazz ? { ...route, page: "bracket", clazz } : route;
  }
  // The Maps section's regions (/maps/regions/3a), and their first address (/regions/3a), which
  // nginx redirects; the app writes the new one back to the address bar.
  if (parts[0] === "maps" && parts[1] === "regions" && (parts.length === 3 || (parts.length === 4 && ["compare", "timeline"].includes(parts[3])))) {
    const clazz = classFromSlug(parts[2]);
    return clazz ? { ...route, page: "regions", clazz, view: parts[3] ?? "map" } : route;
  }
  // The Counties pages: /maps/counties (pick one) and /maps/counties/hinds. Whether a slug is one of
  // the state's counties is the page's to say (it has the map); nginx serves only those.
  if (parts[0] === "maps" && parts[1] === "counties" && (parts.length <= 3 || (parts.length === 4 && ["compare", "timeline"].includes(parts[3])))) {
    if (parts.length >= 3 && !/^[a-z]+(?:-[a-z]+)*$/.test(parts[2])) return route;
    return { ...route, page: "counties", county: parts[2] ?? null, view: parts[3] ?? "map", vsClass: null };
  }
  if (parts[0] === "regions" && parts.length === 2) {
    const clazz = classFromSlug(parts[1]);
    return clazz ? { ...route, page: "regions", clazz } : route;
  }
  return route;
}

/**
 * The canonical URL for a route. `team` here is a slug. The season is left
 * out when it's the current one (on the Regions page, when it's the page's
 * own default, regionsSeason: the newest regions), the week when it's the
 * latest (null), and the odds mode when it's Projected.
 */
export function buildPath(route, { currentSeason = null, regionsSeason = null } = {}) {
  let path = "/";
  if (route.page === "feedback") return "/feedback";
  if (route.page === "class" || route.page === "region") {
    path = `/standings/${route.clazz}a`;
    if (route.page === "region") path += `/${route.region}`;
  } else if (route.page === "bracket") {
    path = `/brackets/${route.clazz}a`;
  } else if (route.page === "regions") {
    path = `/maps/regions/${route.clazz}a${route.view === "compare" || route.view === "timeline" ? `/${route.view}` : ""}`;
  } else if (route.page === "counties") {
    path = route.county ? `/maps/counties/${route.county}` : "/maps/counties";
    if (route.county && (route.view === "compare" || route.view === "timeline")) path += `/${route.view}`;
  }
  const q = new URLSearchParams();
  const maps = route.page === "regions" || route.page === "counties";
  const defaultSeason = maps ? regionsSeason : currentSeason;
  // (The Timeline shows every season, but keeps the one chosen on the Season view, for going back to it.)
  if (route.season && route.season !== defaultSeason) q.set("season", route.season);
  if (route.week) q.set("week", route.week);
  if (route.odds && route.odds !== "projected") q.set("odds", route.odds);
  if (maps && route.view === "compare") {
    if (route.vs) q.set("vs", route.vs);
    if (route.page === "regions" && route.vsClass && route.vsClass !== route.clazz) q.set("vsclass", `${route.vsClass}a`);
  }
  if (route.team) q.set("team", route.team);
  const query = q.toString();
  return query ? `${path}?${query}` : path;
}
