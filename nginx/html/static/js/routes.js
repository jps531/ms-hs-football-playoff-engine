// URL shape: the path says what you're looking at, the query says how.
//   /                          landing (every region race in the state)
//   /standings/3a              every region in a class
//   /standings/3a/6            one region (Region 6-3A)
//   /brackets/3a               a class's playoff bracket
//   ?season=2025&week=9&odds=tossup&team=st-martin
// Defaults are left out of the URL (current season, latest week, Projected,
// no team), so a link to "now" is just the path. No DOM, so it runs under
// `node --test`.

export const CLASSES = [1, 2, 3, 4, 5, 6, 7];

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
 * page is "landing", "class", "region", "bracket", "feedback", or "notfound". team is the raw
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
  return route;
}

/**
 * The canonical URL for a route. `team` here is a slug. The season is left
 * out when it's the current one, the week when it's the latest (null), and
 * the odds mode when it's Projected.
 */
export function buildPath(route, { currentSeason = null } = {}) {
  let path = "/";
  if (route.page === "feedback") return "/feedback";
  if (route.page === "class" || route.page === "region") {
    path = `/standings/${route.clazz}a`;
    if (route.page === "region") path += `/${route.region}`;
  } else if (route.page === "bracket") {
    path = `/brackets/${route.clazz}a`;
  }
  const q = new URLSearchParams();
  if (route.season && route.season !== currentSeason) q.set("season", route.season);
  if (route.week) q.set("week", route.week);
  if (route.odds && route.odds !== "projected") q.set("odds", route.odds);
  if (route.team) q.set("team", route.team);
  const query = q.toString();
  return query ? `${path}?${query}` : path;
}
