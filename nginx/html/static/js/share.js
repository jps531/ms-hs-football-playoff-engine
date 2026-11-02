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
// share-assets step to /static/region/): each in either odds mode and theme.

/** The images a region page offers. */
export const REGION_IMAGES = [
  { key: "overview", label: "Overview" },
];

export const REGION_MODES = [
  { key: "projected", label: "Projected odds" },
  { key: "tossup", label: "Toss-up odds" },
];

/** The odds modes a region's images come in: Projected only while there are Projected odds. */
export function regionModes({ projectedAvailable }) {
  return projectedAvailable ? ["projected", "tossup"] : ["tossup"];
}

/** The image to start from: the overview, in the page's odds mode and theme. */
export function regionShareDefaults({ mode, modes, dark }) {
  return { image: "overview", mode: modes.includes(mode) ? mode : modes[0], theme: dark ? "dark" : "light" };
}

/** Where the image is served: /static/region/2026/3a-6-overview-projected-dark.png. */
export function regionImagePath(season, clazz, region, { image, mode, theme }) {
  return `/static/region/${season}/${clazz}a-${region}-${image}-${mode}-${theme}.png`;
}

/** The file's name when shared or saved: "region-6-3a-overview-2026.png" ("…-tossup.png" in Toss-up odds). */
export function regionImageName(season, clazz, region, { image, mode }) {
  return `region-${region}-${clazz}a-${image}-${season}${mode === "tossup" ? "-tossup" : ""}.png`;
}

/** What the image shows, for its alt text and the share sheet: "Region 6-3A overview, with Projected odds". */
export function regionImageLabel(clazz, region, { image, mode }) {
  const what = REGION_IMAGES.find((i) => i.key === image)?.label.toLowerCase() ?? image;
  return `Region ${region}-${clazz}A ${what}, with ${mode === "tossup" ? "Toss-up" : "Projected"} odds`;
}
