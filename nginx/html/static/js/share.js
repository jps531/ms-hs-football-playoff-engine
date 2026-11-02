import { slugify } from "./routes.js";

// Sharing a bracket as an image. The images themselves are drawn on the
// server after each update (backend/helpers/bracket_image.py, written by the
// share-assets step to /static/bracket/), so this only picks one and hands it
// to the device's share sheet, a download, or the clipboard.

/** The views an image can show, as the bracket's half control names them. */
export const SHARE_VIEWS = [
  { key: "north", label: "North", half: "N" },
  { key: "south", label: "South", half: "S" },
  { key: "all", label: "Whole bracket", half: "both" },
];

/** With Projected odds, or blank (results and locked teams only). */
export const SHARE_VERSIONS = [
  { key: "odds", label: "Projected odds" },
  { key: "blank", label: "Blank" },
];

export const SHARE_THEMES = [
  { key: "light", label: "Light" },
  { key: "dark", label: "Dark" },
];

/**
 * Which versions exist for a bracket: a Projected one only while there are
 * Projected odds and the season isn't over (a finished bracket is drawn
 * blank, with its results), and never for a past season, which is drawn once,
 * blank.
 */
export function shareVersions({ projectedAvailable, final, pastSeason }) {
  return projectedAvailable && !final && !pastSeason ? ["odds", "blank"] : ["blank"];
}

/**
 * The image to start from: the half on screen (both halves, the whole
 * bracket), Projected odds unless the page is in Toss-up odds (whose image
 * there isn't) or there's no Projected image, and the theme the page is in.
 */
export function shareDefaults({ half, mode, versions, dark }) {
  const view = SHARE_VIEWS.find((v) => v.half === half)?.key ?? "all";
  const version = mode === "projected" && versions.includes("odds") ? "odds" : "blank";
  return { view, version, theme: dark ? "dark" : "light" };
}

/** Where the image is served: /static/bracket/2026/3a-north-odds-dark.png. */
export function bracketImagePath(season, clazz, { view, version, theme }) {
  return `/static/bracket/${season}/${clazz}a-${view}-${version}-${theme}.png`;
}

/** The file's name when shared or saved: "class-3a-bracket-north-2026.png". */
export function bracketImageName(season, clazz, { view, version }) {
  const part = view === "all" ? "" : `-${view}`;
  return `class-${clazz}a-bracket${part}-${season}${version === "blank" ? "-blank" : ""}.png`;
}

/** What the image shows, for its alt text and the share sheet: "Class 3A Bracket, North half, with Projected odds". */
export function bracketImageLabel(clazz, { view, version }) {
  const where = view === "all" ? "" : `, ${SHARE_VIEWS.find((v) => v.key === view)?.label} half`;
  const what = version === "odds" ? ", with Projected odds" : "";
  return `Class ${clazz}A Bracket${where}${what}`;
}

// ---------------------------------------------------------------- regions
// A region's images (backend/helpers/region_image.py, written by the
// share-assets step to /static/region/): each in either odds mode and theme,
// some of several pages. The step also writes each region's index of them.

/** The images a region page offers, in order. */
export const REGION_IMAGES = [
  { key: "overview", label: "Overview" },
  { key: "scenarios", label: "Scenarios" },
];

export const REGION_MODES = [
  { key: "projected", label: "Projected odds" },
  { key: "tossup", label: "Toss-up odds" },
];

/** The odds modes a region's images come in: Projected only while there are Projected odds. */
export function regionModes({ projectedAvailable }) {
  return projectedAvailable ? ["projected", "tossup"] : ["tossup"];
}

/** Where a region's index of its images is served: /static/region/2026/3a-6.json. */
export function regionIndexPath(season, clazz, region) {
  return `/static/region/${season}/${clazz}a-${region}.json`;
}

/**
 * How many pages the chosen image has, from the region's index
 * ({ overview: { "projected-dark": 1, … }, scenarios: { … } }); 0 when it has
 * none (nothing to show). Without an index, the overview's one page.
 */
export function regionPages(index, { image, mode, theme }) {
  if (!index) return image === "overview" ? 1 : 0;
  return index[image]?.[`${mode}-${theme}`] ?? 0;
}

/** The images that have something to show in this odds mode and theme, in REGION_IMAGES order. */
export function regionImages(index, { mode, theme }) {
  return REGION_IMAGES.filter((i) => regionPages(index, { image: i.key, mode, theme }) > 0);
}

/** The image to start from: the overview, in the page's odds mode and theme. */
export function regionShareDefaults({ mode, modes, dark }) {
  return { image: "overview", mode: modes.includes(mode) ? mode : modes[0], theme: dark ? "dark" : "light" };
}

/** Where a page is served: /static/region/2026/3a-6-overview-projected-dark.png; "…-2.png" for page 2 of several. */
export function regionImagePath(season, clazz, region, { image, mode, theme }, page = 1, pages = 1) {
  return `/static/region/${season}/${clazz}a-${region}-${image}-${mode}-${theme}${pages > 1 ? `-${page}` : ""}.png`;
}

/** A page's file name when shared or saved: "region-6-3a-overview-2026.png", "…-scenarios-2026-tossup-2.png". */
export function regionImageName(season, clazz, region, { image, mode }, page = 1, pages = 1) {
  return `region-${region}-${clazz}a-${image}-${season}${mode === "tossup" ? "-tossup" : ""}${pages > 1 ? `-${page}` : ""}.png`;
}

/** What the image shows, for its alt text and the share sheet: "Region 6-3A scenarios, with Projected odds". */
export function regionImageLabel(clazz, region, { image, mode }) {
  const what = REGION_IMAGES.find((i) => i.key === image)?.label.toLowerCase() ?? image;
  return `Region ${region}-${clazz}A ${what}, with ${mode === "tossup" ? "Toss-up" : "Projected"} odds`;
}

// ---------------------------------------------------------------- teams
// A team's images (backend/helpers/team_image.py), beside its region's, listed
// in the region's index under "teams": { "Magee": { season: { "projected-dark": 1, … } } }.

/** The images a team's row offers, in order. */
export const TEAM_IMAGES = [{ key: "season", label: "Season" }];

/** How many pages the team's chosen image has, from its region's index; 0 when it has none. */
export function teamPages(index, school, { image, mode, theme }) {
  return index?.teams?.[school]?.[image]?.[`${mode}-${theme}`] ?? 0;
}

/** Where a page is served: /static/region/2026/3a-6-team-magee-season-projected-dark.png. */
export function teamImagePath(season, clazz, region, school, { image, mode, theme }, page = 1, pages = 1) {
  return `/static/region/${season}/${clazz}a-${region}-team-${slugify(school)}-${image}-${mode}-${theme}${pages > 1 ? `-${page}` : ""}.png`;
}

/** A page's file name when shared or saved: "magee-season-2026.png", "magee-season-2026-tossup.png". */
export function teamImageName(season, school, { image, mode }, page = 1, pages = 1) {
  return `${slugify(school)}-${image}-${season}${mode === "tossup" ? "-tossup" : ""}${pages > 1 ? `-${page}` : ""}.png`;
}

/** What the image shows, for its alt text and the share sheet: "Magee’s 2026 season, with Projected odds". */
export function teamImageLabel(season, school, { mode }) {
  return `${school}’s ${season} season, with ${mode === "tossup" ? "Toss-up" : "Projected"} odds`;
}
