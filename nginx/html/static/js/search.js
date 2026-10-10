// Team search matching: which teams a typed query suggests, best first.
// Pure, so it runs under `node --test`.

/** Lowercase, accents and punctuation dropped, spaces collapsed. */
export function normalize(text) {
  return String(text ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Teams matching `query`, best first, at most `limit`: an exact name, then
 * names starting with the query, then names with a word starting with it
 * ("ox" finds "West Oxford"), then names containing it anywhere. Ties keep
 * alphabetical order. `teams` are objects with a `school` name.
 */
export function matchTeams(teams, query, limit = 8) {
  const q = normalize(query);
  if (!q) return [];
  const rank = (name) => {
    const n = normalize(name);
    if (n === q) return 0;
    if (n.startsWith(q)) return 1;
    if (n.includes(` ${q}`)) return 2;
    if (n.includes(q)) return 3;
    return null;
  };
  return teams
    .map((t) => ({ t, r: rank(t.school) }))
    .filter((x) => x.r !== null)
    .sort((a, b) => a.r - b.r || a.t.school.localeCompare(b.t.school))
    .slice(0, limit)
    .map((x) => x.t);
}
