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
