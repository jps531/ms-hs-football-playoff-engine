// /moderate's Games, Venues and Overrides tabs: a team's games in a season (score, status, round,
// region game, overtime, venue, kickoff and its helmet, as overrides of its row), every venue and each
// season's championship venues, and every override on file (each opened on its tab, or cleared) with
// the maintenance jobs. Built from the Schools tab's pieces (moderate-schools.js) and the site's own
// buttons and fields. The pure pieces are exported for the tests.

import { escapeHtml as esc } from "./format.js";
import { input, invalid, json, overrideChanges, schoolFinder, withOverride } from "./moderate-schools.js";
import { comboboxForm } from "./combobox.js";

// --------------------------------------------------------------- shared

export { json }; // (moderate-schools.js's)

/** A tab's status line: *text*, marked as an error when *bad*. */
function setStatus(root, text, bad = false) {
  const el = root.querySelector("[data-tab-status]");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("is-error", bad);
}

/** Check a form's values before sending; the first wrong one says why. */
function checkForm(form) {
  for (const el of form.querySelectorAll("input[data-kind]")) {
    const problem = invalid(el.dataset.kind, el.value);
    el.setCustomValidity(problem);
    if (problem) {
      el.reportValidity();
      return false;
    }
  }
  return true;
}

/** A select of *options* ([value, label]) with *value* chosen. */
function select(name, label, options, value, note = "") {
  return `<label class="fb-field"><span>${esc(label)}</span><select name="${esc(name)}">`
    + options.map(([v, l]) => `<option value="${esc(v)}"${String(v) === String(value ?? "") ? " selected" : ""}>${esc(l)}</option>`).join("")
    + `</select>${note ? `<small>${note}</small>` : ""}</label>`;
}

/** "Stored: …" under a field that has an override. */
const storedNote = (o, show = (v) => v) => (o.overridden ? `Stored: ${esc(show(o.stored) ?? "none")} <span class="ms-tag ms-tag--override">override</span>` : "");

// ---------------------------------------------------------------- games

export const GAME_STATUSES = [
  ["final", "Final"], ["final_forfeit", "Final (forfeit)"], ["not_started", "Not started"], ["in_progress", "In progress"],
  ["end_1q", "End of the 1st quarter"], ["halftime", "Halftime"], ["end_3q", "End of the 3rd quarter"], ["end_4q", "End of the 4th quarter"],
  ["end_ot", "End of overtime"], ["postponed", "Postponed"], ["suspended", "Suspended"], ["canceled", "Canceled"],
];
export const ROUNDS = ["First Round", "Second Round", "Quarterfinals", "Semifinals", "Championship Game"];

/** "Oct 9" for a game's date (YYYY-MM-DD). */
export function shortDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** "vs Leland", "at Leland", "vs Leland (neutral site)": a game from its school's side. */
export function matchup(location, opponent) {
  if (location === "away") return `at ${opponent}`;
  return location === "neutral" ? `vs ${opponent} (neutral site)` : `vs ${opponent}`;
}

/** A kickoff (an ISO moment) as a datetime-local value in Central time ("2025-10-09T19:00"), or "". */
export function centralLocal(iso) {
  if (!iso) return "";
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

/** A game's values as the form edits them (all strings): its stored values, or its overrides. */
export function gameValues(game, which = "value") {
  const out = {};
  for (const f of ["points_for", "points_against", "game_status", "round", "region_game", "overtime", "location", "location_id", "kickoff_time"]) {
    const o = withOverride(game.base, game.overrides, f);
    let v = which === "value" ? o.value : o.stored;
    if (f === "kickoff_time") v = centralLocal(v);
    out[f] = v == null ? "" : String(v);
  }
  return out;
}

/** A game's row in the list: date, matchup, score, region game or round, and an Edit. */
export function gameRow(school, game) {
  const v = gameValues(game);
  const score = v.points_for !== "" && v.points_against !== "" ? `${v.points_for}–${v.points_against}` : "—";
  const tag = v.round ? v.round : v.region_game === "true" ? "Region" : "";
  const over = Object.keys(game.overrides).filter((k) => k !== "ahsfhs_opponent").length ? `<span class="ms-tag ms-tag--override">override</span>` : "";
  return `<div class="ms-row ms-row--game"><span class="ms-k">${esc(shortDate(game.date))}</span>`
    + `<span>${esc(matchup(v.location, game.opponent))}${over}</span><b class="ms-score">${esc(score)}</b>`
    + `<span class="ms-act">${tag ? `<span class="ms-tag">${esc(tag)}</span>` : ""}<button type="button" class="mod-button" data-edit="game-${esc(game.date)}">Edit</button></span></div>`;
}

/** The form for one game (*venues*: [{ id, base }], *helmets*: the school's designs). */
export function gameForm(school, game, venues, helmets) {
  const v = gameValues(game);
  const o = (f) => withOverride(game.base, game.overrides, f);
  const yesNo = (b) => (String(b) === "true" ? "Yes" : "No");
  const roundOptions = [...(game.base.round == null ? [["", "Regular season"]] : []), ...ROUNDS.map((r) => [r, r])];
  const venueName = (id) => venues.find((x) => String(x.id) === String(id))?.base.name ?? "none";
  return `<form class="fb-form ms-form" data-form="game" data-date="${esc(game.date)}">`
    + `<p class="ms-when ms-wide">${esc(shortDate(game.date))} ${esc(matchup(v.location, game.opponent))}</p>`
    + input("points_for", `${school}’s points`, "count", v.points_for, storedNote(o("points_for")))
    + input("points_against", `${game.opponent}’s points`, "count", v.points_against, storedNote(o("points_against")))
    + select("game_status", "Status", [...(game.base.game_status == null ? [["", "None on file"]] : []), ...GAME_STATUSES], v.game_status, storedNote(o("game_status")))
    + select("round", "Round", roundOptions, v.round, storedNote(o("round")))
    + select("region_game", "Region game", [["true", "Yes"], ["false", "No"]], v.region_game, o("region_game").overridden ? `By the region alignment: ${yesNo(game.base.region_game)} <span class="ms-tag ms-tag--override">override</span>` : "")
    + input("overtime", "Overtime periods", "count", v.overtime, storedNote(o("overtime")))
    + select("location", `${school} played`, [["home", "At home"], ["away", "Away"], ["neutral", "At a neutral site"]], v.location, storedNote(o("location")))
    + select("location_id", "Venue", [...(game.base.location_id == null ? [["", "None on file"]] : []), ...venues.map((x) => [x.id, x.base.name])], v.location_id, storedNote(o("location_id"), venueName))
    + `<label class="fb-field"><span>Kickoff (Central)</span><input type="datetime-local" name="kickoff_time" value="${esc(v.kickoff_time)}">${o("kickoff_time").overridden ? `<small>${storedNote(o("kickoff_time"), centralLocal)}</small>` : ""}</label>`
    + select("helmet", `${school}’s helmet`, [["", "None set"], ...helmets.map((h) => [h.id, `${h.year_first_worn}${h.year_last_worn ? `–${h.year_last_worn}` : " on"}${h.color ? `, ${h.color}` : ""}`])], game.helmet_design_id ?? "")
    + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button></div>`
    + `<p class="ms-src ms-wide">Changes are overrides of ${esc(school)}’s row of this game, and the standings and odds pick them up at the next update.</p></form>`;
}

/** The override calls a game form's changes take ({ field, value } or { field, clear }). */
export function gameChanges(game, values) {
  const fields = Object.keys(values).map((f) => [f]);
  const base = gameValues(game, "stored");
  const overrides = {};
  const now = gameValues(game);
  for (const f of Object.keys(game.overrides)) if (f in now) overrides[f] = now[f];
  return overrideChanges(fields, base, overrides, values).map((c) => (c.field === "kickoff_time" && !c.clear
    ? { ...c, value: `${c.value.replace("T", " ")}:00 America/Chicago` } : c));
}

/** The Games tab in *root*: a team and a season, its games, and each game's form. */
export function gamesTab(root, { api, start = {}, onOpen = () => {} }) {
  let names = [];
  let data = null;
  let editing = null;
  root.innerHTML = `<div class="ms-find">${comboboxForm({ id: "mg-school", placeholder: "Find a team", attrs: " data-games-find" })}`
    + `<label class="ms-season"><span class="visually-hidden">Season</span><select id="mg-season"></select></label></div>`
    + `<p class="fb-status" data-tab-status role="status"></p><div data-games></div>`;
  const season = () => Number(root.querySelector("#mg-season").value);

  const draw = () => {
    const box = root.querySelector("[data-games]");
    if (!data) {
      box.innerHTML = "";
      return;
    }
    const { school, season, games, venues, helmets } = data;
    box.innerHTML = `<section class="ms-sec"><h3>${esc(school)}’s ${esc(season)} games <span class="ms-src">${games.length} ${games.length === 1 ? "game" : "games"}</span></h3>`
      + (games.map((g) => (editing === `game-${g.date}` ? gameForm(school, g, venues, helmets) : gameRow(school, g))).join("") || `<p class="ms-src">No games that season.</p>`)
      + "</section>";
  };

  async function load(school, season) {
    setStatus(root, `Loading ${school}’s ${season} games…`);
    const enc = encodeURIComponent(school);
    const [games, venues, helmets] = await Promise.all([
      api(`/admin/games?school=${enc}&season=${season}`).then(json), api("/admin/venues").then(json), api(`/teams/${enc}/helmets`).then(json),
    ]);
    data = { school, season, games, venues, helmets };
    editing = null;
    draw();
    setStatus(root, "");
    onOpen({ school, season });
  }

  root.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (e.target.matches("[data-games-find]")) return; // the search box picks (schoolFinder)
    const form = e.target.closest("form[data-form=game]");
    if (!form || !checkForm(form)) return;
    const game = data.games.find((g) => g.date === form.dataset.date);
    const values = Object.fromEntries([...form.elements].filter((el) => el.name && el.name !== "helmet").map((el) => [el.name, el.value.trim()]));
    const path = `/admin/games/${encodeURIComponent(data.school)}/${game.date}`;
    setStatus(root, "Saving…");
    try {
      for (const c of gameChanges(game, values)) {
        await json(c.clear ? await api(`${path}/overrides/${c.field}`, { method: "DELETE" })
          : await api(`${path}/overrides`, { method: "PUT", body: { field: c.field, value: c.value } }));
      }
      const helmet = form.elements.helmet.value;
      if (helmet !== String(game.helmet_design_id ?? "")) {
        await json(await api(`${path}/helmet`, { method: "PUT", body: { helmet_design_id: helmet === "" ? null : Number(helmet) } }));
      }
      await load(data.school, data.season);
      setStatus(root, "Saved. The standings and odds pick it up at the next update.");
    } catch (err) {
      setStatus(root, err.message, true);
    }
  });
  root.addEventListener("input", (e) => {
    if (e.target.matches("input[data-kind]")) e.target.setCustomValidity("");
  });
  root.addEventListener("click", (e) => {
    const edit = e.target.closest("[data-edit]");
    if (edit) editing = edit.dataset.edit;
    else if (e.target.closest("[data-cancel]")) editing = null;
    else return;
    draw();
  });

  // A team picked opens its games in the season chosen; another season, once one's open, opens that.
  root.querySelector("#mg-season").addEventListener("change", () => {
    if (data) load(data.school, season()).catch((err) => setStatus(root, err.message, true));
  });
  const finder = schoolFinder(root.querySelector("[data-games-find]"), api, (school) => load(school, season()).catch((err) => setStatus(root, err.message, true)));
  Promise.all([finder, api("/seasons").then(json)]).then(([list, seasons]) => {
    names = list;
    root.querySelector("#mg-season").innerHTML = seasons.map((s) => `<option value="${s.season}">${s.season}</option>`).join("");
    if (start.season) root.querySelector("#mg-season").value = String(start.season);
    if (start.school && names.includes(start.school)) {
      root.querySelector("#mg-school").value = start.school;
      load(start.school, season()).catch((err) => setStatus(root, err.message, true));
    }
  }).catch((err) => setStatus(root, err.message, true));
}

// --------------------------------------------------------------- venues

/** A venue's values with overrides (home team and coordinates can be overridden; name and city are its own). */
export function venueValues(venue) {
  const out = {};
  for (const f of Object.keys(venue.base)) out[f] = withOverride(venue.base, venue.overrides, f).value;
  return out;
}

/** A venue's row: name, then town, whose home field it is, and its spot. */
export function venueRow(venue) {
  const v = venueValues(venue);
  const bits = [v.city, v.home_team ? `home of ${v.home_team}` : "", v.latitude != null && v.longitude != null ? `${Number(v.latitude).toFixed(4)}, ${Number(v.longitude).toFixed(4)}` : ""].filter(Boolean);
  const over = Object.keys(venue.overrides).length ? `<span class="ms-tag ms-tag--override">override</span>` : "";
  return `<div class="ms-row ms-row--action"><span><b>${esc(v.name)}</b>${over}${bits.length ? `<br><span class="ms-src">${esc(bits.join(" · "))}</span>` : ""}</span>`
    + `<span></span><button type="button" class="mod-button" data-edit="venue-${venue.id}">Edit</button></div>`;
}

/** A venue's form (or a new venue's, with *venue* null). */
export function venueForm(venue) {
  const o = (f) => (venue ? withOverride(venue.base, venue.overrides, f) : { value: "", stored: "", overridden: false });
  return `<form class="fb-form ms-form" data-form="${venue ? "venue" : "new-venue"}"${venue ? ` data-id="${venue.id}"` : ""}>`
    + input("name", "Name", "required", o("name").value) + input("city", "City", "text", o("city").value)
    + input("home_team", "Home team", "text", o("home_team").value, storedNote(o("home_team")))
    + `<span></span>`
    + input("latitude", "Latitude", "number", o("latitude").value, storedNote(o("latitude")))
    + input("longitude", "Longitude", "number", o("longitude").value, storedNote(o("longitude")))
    + `<div class="ms-save"><button class="fb-submit" type="submit">${venue ? "Save" : "Add the venue"}</button><button type="button" class="mod-button" data-cancel>Cancel</button></div>`
    + (venue ? `<p class="ms-src ms-wide">A changed home team or spot is kept as an override, which the schedule data can’t write over.</p>` : "")
    + "</form>";
}

/** The championship venues of *season*: each class with its venue, and a Change. */
export function championshipSection(season, seasons, assigned, editing, venues) {
  const rows = [1, 2, 3, 4, 5, 6, 7].map((c) => {
    const a = assigned.find((x) => x.class_ === c);
    if (editing === `champ-${c}`) {
      return `<form class="fb-form ms-form" data-form="champ" data-class="${c}"><p class="ms-when ms-wide">${c}A</p>`
        + select("location", "Venue", venues.map((x) => [x.base.name, x.base.name]), a?.location_name ?? "")
        + `<div class="ms-save"><button class="fb-submit" type="submit">Save</button><button type="button" class="mod-button" data-cancel>Cancel</button></div></form>`;
    }
    return `<div class="ms-row ms-row--action"><span class="ms-k">${c}A</span><span>${a ? esc(a.location_name) : `<span class="ms-src">Not set</span>`}</span>`
      + `<button type="button" class="mod-button" data-edit="champ-${c}">Change</button></div>`;
  }).join("");
  return `<section class="ms-sec"><h3>Championship games <label class="inline-select"><span class="visually-hidden">Season</span>`
    + `<select data-champ-season>${seasons.map((s) => `<option value="${s}"${s === season ? " selected" : ""}>${s}</option>`).join("")}</select></label></h3>${rows}</section>`;
}

/** The Venues tab in *root*: each season's championship venues, and every venue. */
export function venuesTab(root, { api }) {
  let venues = [];
  let seasons = [];
  let season = null;
  let assigned = [];
  let editing = null;
  let filter = "";
  // A filter, not a pick (the list below narrows as you type), in the search box's look.
  root.innerHTML = `<div class="ms-find"><div class="team-search team-search--page"><label for="mv-find" class="visually-hidden">Find a venue</label>`
    + `<input id="mv-find" type="search" placeholder="Find a venue" autocomplete="off" spellcheck="false"></div>`
    + `<button type="button" class="mod-button" data-edit="new-venue">Add a venue</button></div>`
    + `<p class="fb-status" data-tab-status role="status"></p><div data-venues></div>`;

  const draw = () => {
    const shown = venues.filter((v) => !filter || `${v.base.name} ${v.base.city ?? ""} ${v.base.home_team ?? ""}`.toLowerCase().includes(filter));
    root.querySelector("[data-venues]").innerHTML = championshipSection(season, seasons, assigned, editing, venues)
      + (editing === "new-venue" ? `<section class="ms-sec"><h3>A new venue</h3>${venueForm(null)}</section>` : "")
      + `<section class="ms-sec"><h3>Venues <span class="ms-src">${shown.length} of ${venues.length}</span></h3>`
      + shown.map((v) => (editing === `venue-${v.id}` ? venueForm(v) : venueRow(v))).join("") + "</section>";
  };
  async function load() {
    [venues, assigned] = await Promise.all([api("/admin/venues").then(json), api(`/admin/championship-venue?season=${season}`).then(json)]);
    editing = null;
    draw();
  }

  root.addEventListener("input", (e) => {
    if (e.target.id === "mv-find") {
      filter = e.target.value.trim().toLowerCase();
      draw();
    } else if (e.target.matches("input[data-kind]")) e.target.setCustomValidity("");
  });
  root.addEventListener("change", (e) => {
    if (!e.target.matches("[data-champ-season]")) return;
    season = Number(e.target.value);
    load().catch((err) => setStatus(root, err.message, true));
  });
  root.addEventListener("click", (e) => {
    const edit = e.target.closest("[data-edit]");
    if (edit) editing = edit.dataset.edit;
    else if (e.target.closest("[data-cancel]")) editing = null;
    else return;
    draw();
  });
  root.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target.closest("form[data-form]");
    if (!form || !checkForm(form)) return;
    const v = Object.fromEntries([...form.elements].filter((el) => el.name).map((el) => [el.name, el.value.trim()]));
    const num = (x) => (x === "" ? null : Number(x));
    setStatus(root, "Saving…");
    try {
      if (form.dataset.form === "champ") {
        await json(await api("/admin/championship-venue", { method: "POST", body: { season, location: v.location, class: Number(form.dataset.class) } }));
      } else if (form.dataset.form === "new-venue") {
        await json(await api("/admin/locations", { method: "POST", body: { name: v.name, city: v.city || null, home_team: v.home_team || null, latitude: num(v.latitude), longitude: num(v.longitude) } }));
      } else {
        const venue = venues.find((x) => String(x.id) === form.dataset.id);
        if (v.name !== venue.base.name || v.city !== (venue.base.city ?? "")) {
          await json(await api(`/admin/locations/${venue.id}`, { method: "PATCH", body: { name: v.name, city: v.city || null } }));
        }
        for (const c of overrideChanges([["home_team"], ["latitude"], ["longitude"]], venue.base, venue.overrides, v)) {
          await json(c.clear ? await api(`/admin/locations/${venue.id}/overrides/${c.field}`, { method: "DELETE" })
            : await api(`/admin/locations/${venue.id}/overrides`, { method: "PUT", body: { field: c.field, value: c.value } }));
        }
      }
      await load();
      setStatus(root, "Saved.");
    } catch (err) {
      setStatus(root, err.message, true);
    }
  });

  api("/seasons").then(json).then((list) => {
    seasons = list.map((s) => s.season);
    season = seasons[0] ?? new Date().getFullYear();
    return load();
  }).catch((err) => setStatus(root, err.message, true));
}

// ------------------------------------------------------------ overrides

/**
 * One override (``list_overrides``: { source, key, value }) as the tab shows it: what it's on, where to
 * open it, and how to clear it (null: not here, as for an opponent correction's record).
 */
export function describeOverride(row, venueNames = {}) {
  const [kind, ...rest] = row.source.split(":");
  if (kind === "school") {
    const school = rest.join(":");
    return { what: `School: ${school}`, open: `?tab=schools&school=${encodeURIComponent(school)}`, clear: `/admin/schools/${encodeURIComponent(school)}/overrides/${row.key}` };
  }
  if (kind === "look") {
    const [id, ...name] = rest;
    const school = name.join(":");
    return { what: `Past look: ${school}`, open: `?tab=schools&school=${encodeURIComponent(school)}`, clear: `/admin/looks/${id}/overrides/${row.key}` };
  }
  if (kind === "location") {
    const id = rest[0];
    return { what: `Venue: ${venueNames[id] ?? `#${id}`}`, open: "?tab=venues", clear: `/admin/locations/${id}/overrides/${row.key}` };
  }
  const date = rest[rest.length - 1];
  const school = rest.slice(0, -1).join(":");
  const season = Number(date.slice(0, 4));
  return {
    what: `Game: ${school}, ${shortDate(date)}, ${season}`,
    open: `?tab=games&school=${encodeURIComponent(school)}&season=${season}`,
    // An opponent correction's record of AHSFHS's name isn't an override to clear here.
    clear: row.key === "ahsfhs_opponent" ? null : `/admin/games/${encodeURIComponent(school)}/${date}/overrides/${row.key}`,
  };
}

/** The Overrides tab's table: every override, grouped as listed. */
export function overridesTable(rows, venueNames) {
  if (!rows.length) return `<p class="ms-src">No overrides on file.</p>`;
  // The roles are spelled out: on a phone the rows are laid out as blocks (app.css), which can cost a
  // table its roles in some browsers.
  return `<div class="ms-table"><table role="table"><thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">On</th><th scope="col" role="columnheader">Field</th><th scope="col" role="columnheader">Value</th><th scope="col" role="columnheader"><span class="visually-hidden">Actions</span></th></tr></thead><tbody role="rowgroup">`
    + rows.map((r, i) => {
      const d = describeOverride(r, venueNames);
      return `<tr role="row"><td role="cell">${esc(d.what)}</td><td role="cell">${esc(r.key)}</td><td role="cell">${esc(r.value)}</td><td role="cell" class="ms-act">`
        + `<a class="mod-button" href="/moderate${esc(d.open)}">Open</a>`
        + (d.clear ? `<button type="button" class="mod-button" data-clear="${i}">Clear</button>` : `<span class="ms-src">An opponent correction</span>`)
        + "</td></tr>";
    }).join("") + "</tbody></table></div>";
}

/** The Overrides tab in *root*: every override, and the maintenance jobs. */
export function overridesTab(root, { api }) {
  let rows = [];
  let names = {};
  root.innerHTML = `<p class="fb-status" data-tab-status role="status"></p><div data-overrides></div>`
    + `<section class="ms-sec"><h3>Maintenance</h3>`
    + `<div class="ms-row ms-row--action"><span class="ms-k">Colors</span><span>Work out every school’s color variants again (after a change to how they’re worked out)</span><button type="button" class="mod-button" data-recompute-all>Recompute all</button></div>`
    + `<div class="ms-row ms-row--action"><span class="ms-k">Logos</span><span data-recut-count>Logos published without their keyline, to re-cut</span><button type="button" class="mod-button" data-recut>Show</button></div>`
    + `<div data-recut-list></div></section>`;

  const draw = () => {
    root.querySelector("[data-overrides]").innerHTML = `<section class="ms-sec"><h3>Every override <span class="ms-src">${rows.length} on file</span></h3>${overridesTable(rows, names)}</section>`;
  };
  async function load() {
    const [list, venues] = await Promise.all([api("/admin/overrides").then(json), api("/admin/venues").then(json)]);
    rows = list;
    names = Object.fromEntries(venues.map((v) => [String(v.id), v.base.name]));
    draw();
  }

  root.addEventListener("click", async (e) => {
    const clear = e.target.closest("[data-clear]");
    try {
      if (clear) {
        const row = rows[Number(clear.dataset.clear)];
        const d = describeOverride(row, names);
        if (!window.confirm(`Clear ${row.key} on ${d.what}?`)) return;
        setStatus(root, "Clearing…");
        await json(await api(d.clear, { method: "DELETE" }));
        await load();
        setStatus(root, "Cleared.");
      } else if (e.target.closest("[data-recompute-all]")) {
        if (!window.confirm("Work out every school’s color variants again?")) return;
        setStatus(root, "Recomputing every school’s colors…");
        const res = await json(await api("/admin/schools/recompute-colors", { method: "POST", body: {} }));
        const failed = res.clamp_failed_schools ?? [];
        setStatus(root, `Recomputed ${res.recomputed} schools.${failed.length ? ` Colors that couldn’t be made readable: ${failed.join(", ")}.` : ""}`);
      } else if (e.target.closest("[data-recut]")) {
        const logos = await json(await api("/admin/logos/needs-recut"));
        root.querySelector("[data-recut-list]").innerHTML = logos.length
          ? `<ul class="ms-list">${logos.map((l) => `<li><a href="/moderate?tab=schools&amp;school=${esc(encodeURIComponent(l.school))}">${esc(l.school)}</a>: ${esc(l.logo_type)}</li>`).join("")}</ul>`
          : `<p class="ms-src">None to re-cut.</p>`;
        root.querySelector("[data-recut-count]").textContent = `Logos published without their keyline, to re-cut: ${logos.length}`;
      }
    } catch (err) {
      setStatus(root, err.message, true);
    }
  });

  load().catch((err) => setStatus(root, err.message, true));
}
