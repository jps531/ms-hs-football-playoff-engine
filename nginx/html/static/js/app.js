// 2026 interim UI: pick a class, pick a region, read that region's race.
// Two views on one page — the class's region list and a region — addressed
// by query string so every view has a shareable URL:
//   ?season=2026&class=7&region=2&team=Oxford&week=9&odds=tossup
// Every parameter is optional; omitted ones fall back to the current season,
// the latest week, and Projected odds.

import { escapeHtml as esc, formatPct, recordText, shortDate, gameDate } from "./format.js";
import {
  oddsCell, provenance, statusBadges, teamMark, teamLabel, scenarioCard, classScrubber, chevronIcon,
  ODDS_MODES, modeLabel, infoButton, gameCard, outcomeScenarioCard,
} from "./components.js";
import {
  outcomeCards, insightCards, oddsFor, hasProjectedOdds, completeScenarioCards,
} from "./scenarios.js";
import {
  standingPositions, playoffPath, regionGames, displayOrder, regionComplete, snapshotDate,
  orient, byDay, teamSchedule,
} from "./standings.js";

const API = "/api/v1";
const CLASSES = [1, 2, 3, 4, 5, 6, 7];
const STORE = { clazz: "mshsf.class", odds: "mshsf.odds" };

const app = document.getElementById("app");
const scrubberHost = document.getElementById("scrubber");
const teamSearch = document.getElementById("team-search");
const teamOptions = document.getElementById("team-options");

// --------------------------------------------------------------- data

const cache = new Map();
function getJSON(path) {
  if (!cache.has(path)) {
    const request = fetch(API + path, { headers: { Accept: "application/json" } }).then((res) => {
      if (!res.ok) {
        const err = new Error(`${res.status} ${path}`);
        err.status = res.status;
        throw err;
      }
      return res.json();
    });
    // Don't cache failures: a later navigation should retry.
    request.catch(() => cache.delete(path));
    cache.set(path, request);
  }
  return cache.get(path);
}

async function seasons() {
  const rows = await getJSON("/seasons");
  const list = rows.map((r) => r.season).sort((a, b) => b - a);
  if (!list.length) throw Object.assign(new Error("no seasons"), { status: 404 });
  return list;
}

/** school -> team metadata (colors, class, region) for the season. */
async function teamsBySchool(season) {
  try {
    const rows = await getJSON(`/teams?season=${season}`);
    return Object.fromEntries(rows.map((t) => [t.school, t]));
  } catch {
    return {}; // identity is a nicety; marks fall back to initials
  }
}

function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** The Sunday closing the Monday-Sunday week that contains an ISO date. */
function weekEnd(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  date.setUTCDate(date.getUTCDate() + ((7 - date.getUTCDay()) % 7));
  return date.toISOString().slice(0, 10);
}

/**
 * Played weeks for the season (and class, so 1A-4A / 5A-7A playoff rounds
 * label correctly), oldest first: [{ week, label, lastDate, end }].
 */
async function playedWeeks(season, clazz) {
  let dates;
  try {
    ({ dates } = await getJSON(`/seasons/${season}/dates${clazz ? `?class=${clazz}` : ""}`));
  } catch {
    return [];
  }
  const now = today();
  const weeks = new Map();
  for (const d of dates) {
    if (d.kind !== "games" || d.date > now) continue;
    weeks.set(d.week, { week: d.week, label: d.description, lastDate: d.date, end: weekEnd(d.date) });
  }
  return [...weeks.values()].sort((a, b) => a.week - b.week);
}

// ------------------------------------------------------------- routing

function readRoute() {
  const q = new URLSearchParams(location.search);
  const num = (k) => (Number.isInteger(Number(q.get(k))) && Number(q.get(k)) > 0 ? Number(q.get(k)) : null);
  const clazz = num("class");
  const odds = q.get("odds");
  return {
    season: num("season"),
    clazz: CLASSES.includes(clazz) ? clazz : null,
    region: num("region"),
    team: q.get("team") || null,
    week: num("week"),
    odds: odds in ODDS_MODES ? odds : null,
  };
}

let route = readRoute();

/** URL for the current route with some fields changed (null removes one). */
function hrefWith(changes) {
  const next = { ...route, ...changes };
  const q = new URLSearchParams();
  if (next.season) q.set("season", next.season);
  if (next.clazz) q.set("class", next.clazz);
  if (next.region) q.set("region", next.region);
  if (next.team) q.set("team", next.team);
  if (next.week) q.set("week", next.week);
  if (next.odds) q.set("odds", next.odds);
  return `/?${q}`;
}

function navigate(url, { scroll = false } = {}) {
  history.pushState(null, "", url);
  render();
  if (scroll) window.scrollTo(0, 0);
}

function stored(key, valid) {
  try {
    const v = localStorage.getItem(key);
    return valid(v) ? v : null;
  } catch {
    return null;
  }
}
function store(key, value) {
  try { localStorage.setItem(key, String(value)); } catch { /* storage unavailable */ }
}

// ------------------------------------------------------------- render

let renderToken = 0;
// Set when the team search jumps to a team, so the page scrolls to its row;
// picking a row in place leaves the scroll position alone.
let scrollToFocus = false;
async function render() {
  const token = ++renderToken;
  route = readRoute();
  const saved = Number(stored(STORE.clazz, (v) => CLASSES.includes(Number(v))));
  route.clazz ??= CLASSES.includes(saved) ? saved : CLASSES[0];
  store(STORE.clazz, route.clazz);
  renderScrubber(route.clazz);
  app.setAttribute("aria-busy", "true");
  try {
    const all = await seasons();
    const season = all.includes(route.season) ? route.season : all[0];
    const ctx = { ...route, season, seasons: all, currentSeason: all[0] };
    loadTeamSearch(season);
    const html = route.region ? await regionView(ctx) : await classView(ctx);
    if (token !== renderToken) return;
    app.innerHTML = html;
    if (scrollToFocus && route.team && route.region) focusTeamRow();
    scrollToFocus = false;
  } catch (err) {
    if (token !== renderToken) return;
    app.innerHTML = notice(
      err?.status === 404
        ? "There’s nothing published for this yet. Try another week or season, or check back once region play is underway."
        : "This page couldn’t load right now. Please try again in a moment.",
    );
  } finally {
    if (token === renderToken) app.removeAttribute("aria-busy");
  }
  document.title = pageTitle(route.clazz, route.region);
}

function pageTitle(clazz, region) {
  const base = "Mississippi High School Football Playoff Races";
  return region ? `Region ${region}-${clazz}A · ${base}` : `${clazz}A Regions · ${base}`;
}

function notice(text) {
  return `<div class="page"><p class="notice">${esc(text)}</p></div>`;
}

// ------------------------------------------------------------ scrubber

function renderScrubber(clazz) {
  scrubberHost.innerHTML = classScrubber(CLASSES, clazz);
  scrubberHost.querySelector('[aria-checked="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

const classHref = (clazz) => hrefWith({ clazz, region: null, team: null, week: null });

scrubberHost.addEventListener("click", (e) => {
  const item = e.target.closest("[data-class]");
  if (item) navigate(classHref(Number(item.dataset.class)));
});

scrubberHost.addEventListener("keydown", (e) => {
  const items = [...scrubberHost.querySelectorAll("[data-class]")];
  const i = items.indexOf(document.activeElement);
  if (i < 0) return;
  const moves = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
  let next;
  if (e.key in moves) next = (i + moves[e.key] + items.length) % items.length;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = items.length - 1;
  else return;
  e.preventDefault();
  const target = items[next].dataset.class;
  navigate(classHref(Number(target)));
  scrubberHost.querySelector(`[data-class="${target}"]`)?.focus();
});

// --------------------------------------------------------- team search
// One field that's both a dropdown and a search: a text input bound to a
// datalist of every team in the season. Picking a team opens its region.

let teamSearchSeason = null;
let teamIndex = {};

async function loadTeamSearch(season) {
  if (!teamSearch || teamSearchSeason === season) return;
  teamSearchSeason = season;
  teamIndex = await teamsBySchool(season);
  const options = Object.values(teamIndex)
    .sort((a, b) => a.school.localeCompare(b.school))
    .map((t) => `<option value="${esc(t.school)}">${t.class_}A · Region ${t.region}</option>`);
  teamOptions.innerHTML = options.join("");
}

function findTeam(text) {
  const q = text.trim().toLowerCase();
  if (!q) return null;
  const all = Object.values(teamIndex);
  return all.find((t) => t.school.toLowerCase() === q)
    ?? (() => {
      const starts = all.filter((t) => t.school.toLowerCase().startsWith(q));
      return starts.length === 1 ? starts[0] : null;
    })();
}

function goToTeam(team) {
  teamSearch.value = "";
  teamSearch.blur();
  scrollToFocus = true;
  navigate(hrefWith({ clazz: team.class_, region: team.region, team: team.school }), { scroll: true });
}

teamSearch?.addEventListener("input", () => {
  // Picking from the datalist fills the exact name; jump straight there.
  const team = teamIndex[teamSearch.value];
  if (team) goToTeam(team);
});

teamSearch?.closest("form")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const team = findTeam(teamSearch.value);
  if (team) {
    goToTeam(team);
    return;
  }
  teamSearch.setCustomValidity("No team by that name this season.");
  teamSearch.reportValidity();
});
teamSearch?.addEventListener("keydown", () => teamSearch.setCustomValidity(""));

// ---------------------------------------------------- provenance controls
// The page's provenance line doubles as its controls: which season, through
// which week, and which odds mode. Cards repeat it as plain text.

function select(name, label, options, selected) {
  const opts = options.map((o) => `<option value="${esc(o.value)}"${String(o.value) === String(selected) ? " selected" : ""}>${esc(o.label)}</option>`);
  return `<label class="inline-select"><span class="visually-hidden">${esc(label)}</span><select data-control="${name}">${opts.join("")}</select></label>`;
}

function controlsLine(ctx, weeks, { asOf, mode, projectedAvailable }) {
  const sep = '<span class="sep" aria-hidden="true">·</span>';
  const parts = [];
  parts.push(select("season", "Season", ctx.seasons.map((s) => ({ value: s, label: `${s} season` })), ctx.season));
  if (weeks.length) {
    // Without an explicit week, show the week the snapshot actually covers,
    // which can trail the calendar (e.g. before the morning recompute).
    const covered = asOf ? [...weeks].reverse().find((w) => w.lastDate <= asOf) : null;
    const chosen = ctx.week && weeks.some((w) => w.week === ctx.week)
      ? ctx.week
      : (covered ?? weeks[weeks.length - 1]).week;
    const options = [...weeks].reverse().map((w) => ({ value: w.week, label: w.label }));
    const shown = weeks.find((w) => w.week === chosen);
    parts.push(`<span class="ctl">Through ${select("week", "Through week", options, chosen)}</span>`);
    // The date is what the data actually covers. When the newest snapshot
    // predates the chosen week's games (e.g. no post-round playoff snapshot
    // was written), say so instead of implying the week's date.
    if (shown && asOf && asOf < shown.lastDate) parts.push(`<span>Latest update ${esc(shortDate(asOf))}</span>`);
    else if (shown) parts.push(`<span>${esc(shortDate(shown.lastDate))}</span>`);
  } else if (asOf) {
    parts.push(`<span>Updated ${esc(shortDate(asOf))}</span>`);
  }
  if (projectedAvailable) {
    parts.push(`<span class="ctl ctl--mode mode--${mode}">${ODDS_MODES[mode].glyph}${select("odds", "Odds", [
      { value: "projected", label: "Projected" }, { value: "tossup", label: "Toss-up" },
    ], mode)}${infoButton("mode-help", "What Projected and Toss-up mean")}</span>`);
  } else if (mode) {
    parts.push(`<span class="ctl">${modeLabel("tossup")}${infoButton("mode-help", "What Toss-up means")}</span>`);
  }
  const help = mode ? MODE_HELP : "";
  // Each separator travels with the segment after it, so a wrapped line
  // never ends on a dangling dot.
  const segs = parts.map((part, i) => (i === 0 ? part : `<span class="seg">${sep}${part}</span>`));
  return `<p class="provenance provenance--controls">${segs.join("")}</p>${help}`;
}

const MODE_HELP = `<div class="mode-help" id="mode-help" hidden>
  <p><strong>Projected</strong> weighs every way the season can finish by how likely it is, using each team’s Elo rating and home-field advantage to set its chance of winning each game.</p>
  <p><strong>Toss-up</strong> counts every way the season can finish equally, as if each remaining game were a coin flip.</p>
  <p><a href="/methodology">More on how the odds work</a></p>
</div>`;

app.addEventListener("change", (e) => {
  const control = e.target.closest("[data-control]");
  if (!control) return;
  const value = control.value;
  if (control.dataset.control === "season") {
    navigate(hrefWith({ season: Number(value), week: null, team: null }));
  } else if (control.dataset.control === "week") {
    const latest = control.options[0].value; // options run newest first
    navigate(hrefWith({ week: value === latest ? null : Number(value) }));
  } else if (control.dataset.control === "odds") {
    store(STORE.odds, value);
    navigate(hrefWith({ odds: value === "projected" ? null : value }));
  }
});

/** Snapshot date to request for the chosen week (null = latest). */
function dateParam(ctx, weeks) {
  return snapshotDate(weeks, ctx.week, ctx.season !== ctx.currentSeason);
}

function oddsMode(ctx) {
  return ctx.odds ?? stored(STORE.odds, (v) => v in ODDS_MODES) ?? "projected";
}

// ------------------------------------------------------ class view (entry)
// Every region in the class as a condensed standings table: position,
// team, region record, and odds of the title and a playoff spot.

async function classView(ctx) {
  const { season, clazz } = ctx;
  const weeks = await playedWeeks(season, clazz);
  const date = dateParam(ctx, weeks);
  const [data, teams] = await Promise.all([
    getJSON(`/standings/${clazz}?season=${season}${date ? `&date=${date}` : ""}`),
    teamsBySchool(season),
  ]);
  const allTeams = data.regions.flatMap((r) => r.teams);
  const projectedAvailable = hasProjectedOdds(allTeams);
  const mode = projectedAvailable ? oddsMode(ctx) : "tossup";

  const head = `<div class="page entry-head">
    <h1 class="title">Class ${clazz}A</h1>
    ${controlsLine(ctx, weeks, { asOf: data.as_of_date, mode, projectedAvailable })}
  </div>`;
  if (!data.regions.length) return head + notice("No standings have been published for this class yet.");

  const blocks = data.regions.map((r) => {
    const ordered = displayOrder(r.teams);
    const positions = standingPositions(ordered);
    const complete = regionComplete(ordered);
    const rows = ordered.map((t, i) => {
      const o = oddsFor(t, mode);
      const rec = t.record;
      return `<tr class="${t.eliminated ? "is-eliminated" : ""}">
        <td class="col-pos">${positions[i]}</td>
        <th scope="row" class="col-team"><a class="team-link" href="${esc(hrefWith({ region: r.region, team: t.school }))}">${teamMark(t.school, teams[t.school])}<span class="row-toggle__label"><span class="team-name">${esc(t.school)}</span>${statusBadges(t, { regionComplete: complete })}</span></a></th>
        <td class="col-rec">${esc(recordText(rec.region_wins, rec.region_losses, rec.region_ties))}</td>
        <td class="col-odds">${oddsCell(o.p1)}</td>
        <td class="col-odds">${oddsCell(o.p_playoffs)}</td>
      </tr>`;
    });
    return `<section class="region-block" aria-labelledby="region-${r.region}">
      <h2 class="region-block__title" id="region-${r.region}"><a href="${esc(hrefWith({ region: r.region, team: null }))}">Region ${r.region}</a></h2>
      <table class="standings standings--compact">
        <caption class="visually-hidden">Region ${r.region}-${clazz}A standings</caption>
        <thead><tr>
          <th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>
          <th scope="col" class="col-team">Team</th>
          <th scope="col" class="col-rec">Region</th>
          <th scope="col" class="col-odds">1st</th>
          <th scope="col" class="col-odds">Playoffs</th>
        </tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    </section>`;
  });

  return `${head}<div class="page region-blocks">${blocks.join("")}</div>`;
}

// ------------------------------------------------------------ region view

async function regionView(ctx) {
  const { season, clazz, region } = ctx;
  const weeks = await playedWeeks(season, clazz);
  const date = dateParam(ctx, weeks);
  const [data, teams, games] = await Promise.all([
    getJSON(`/standings/${clazz}/${region}?season=${season}&include_team_scenarios=true${date ? `&date=${date}` : ""}`),
    teamsBySchool(season),
    getJSON(`/games?season=${season}&class=${clazz}&region=${region}`).catch(() => []),
  ]);
  const { results, dateFor } = regionGames(games, data.as_of_date);

  const projectedAvailable = hasProjectedOdds(data.teams);
  const mode = projectedAvailable ? oddsMode(ctx) : "tossup";
  const focus = data.teams.some((t) => t.school === ctx.team) ? ctx.team : null;

  // Cards carry the same provenance as plain text, so a cropped screenshot
  // of one still says what it shows.
  const shownWeek = [...weeks].reverse().find((w) => w.lastDate <= data.as_of_date);
  const cardProv = provenance(
    { label: shownWeek?.label, date: shownWeek?.lastDate ?? data.as_of_date, mode },
    shortDate,
  );

  const remaining = (data.remaining_games ?? []).map((g) => ({
    date: dateFor(g.team_a, g.team_b), ...orient(g.team_a, g.team_b, g.location_a),
  }));
  const schedule = { results, remaining };
  return `<div class="page">
    <header class="region-head">
      <a class="region-head__back" href="${esc(hrefWith({ region: null, team: null }))}">All ${clazz}A regions</a>
      <h1 class="title">Region ${region}-${clazz}A</h1>
      ${data.headline ? `<p class="headline">${esc(data.headline)}</p>` : ""}
      ${controlsLine(ctx, weeks, { asOf: data.as_of_date, mode, projectedAvailable })}
    </header>
    ${standingsTable(data, teams, mode, focus, clazz, schedule)}
    ${remaining.length ? gamesSection("remaining", "Remaining games", remaining, teams, focus) : ""}
    ${remaining.length ? scenariosSection(data, teams, cardProv, mode, focus) : ""}
    ${data.scenarios?.length ? allScenariosSection(data.scenarios, teams, focus) : ""}
    ${results.length ? gamesSection("results", "Completed games", results, teams, focus) : ""}
  </div>`;
}

const ODDS_COLUMNS = [
  { key: "p1", label: "1st", mid: false },
  { key: "p2", label: "2nd", mid: true },
  { key: "p3", label: "3rd", mid: true },
  { key: "p4", label: "4th", mid: true },
  { key: "p_playoffs", label: "Playoffs", mid: false },
];

function standingsTable(data, teams, mode, focus, clazz, games) {
  const ordered = displayOrder(data.teams);
  const positions = standingPositions(ordered);
  const complete = !(data.remaining_games ?? []).length;
  const rows = ordered.map((t, i) => {
    const r = t.record;
    const o = oddsFor(t, mode);
    const detailId = `detail-${i}`;
    const focused = t.school === focus;
    const cells = ODDS_COLUMNS.map(
      (c) => `<td class="col-odds${c.mid ? " col-mid" : ""}">${oddsCell(o[c.key])}</td>`,
    );
    const cls = [t.eliminated ? "is-eliminated" : "", focused ? "is-focus" : ""].filter(Boolean).join(" ");
    return `<tr class="${cls}"${focused ? ' id="focus-row"' : ""}>
        <td class="col-pos">${positions[i]}</td>
        <th scope="row" class="col-team">
          <button type="button" class="row-toggle" data-team="${esc(t.school)}" aria-expanded="${focused}" aria-controls="${detailId}">
            ${chevronIcon}${teamMark(t.school, teams[t.school])}<span class="row-toggle__label"><span class="team-name">${esc(t.school)}</span>${statusBadges(t, { regionComplete: complete })}</span>
          </button>
        </th>
        <td class="col-rec">${esc(recordText(r.region_wins, r.region_losses, r.region_ties))}</td>
        <td class="col-rec col-overall">${esc(recordText(r.wins, r.losses, r.ties))}</td>
        ${cells.join("")}
      </tr>
      <tr class="detail${focused ? " is-focus" : ""}" id="${detailId}"${focused ? "" : " hidden"}><td colspan="9">${focused ? rowDetail(t, mode, clazz, complete, teams, games) : ""}</td></tr>`;
  });

  const oddsHeads = ODDS_COLUMNS.map(
    (c) => `<th scope="col" class="col-odds${c.mid ? " col-mid" : ""}">${c.label}</th>`,
  );
  return `<table class="standings">
    <caption class="visually-hidden">Standings and ${mode === "projected" ? "projected" : "toss-up"} odds of finishing in each playoff position. Select a team to see its playoff path and scenarios.</caption>
    <thead><tr>
      <th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>
      <th scope="col" class="col-team">Team</th>
      <th scope="col" class="col-rec">Region</th>
      <th scope="col" class="col-rec col-overall">Overall</th>
      ${oddsHeads.join("")}
    </tr></thead>
    <tbody>${rows.join("")}</tbody>
  </table>`;
}

/**
 * Expanded row, three panels side by side (stacked on phones): the team's
 * record and region schedule, its seeding odds, and its road through the
 * bracket.
 */
function rowDetail(t, mode, clazz, complete, teams, games) {
  const r = t.record;
  const o = oddsFor(t, mode);
  const { completed, upcoming } = teamSchedule(t.school, games.results, games.remaining);

  const opponent = (g) => `<span class="sched__joiner">${esc(g.joiner)}</span>${teamLabel(g.opponent, teams)}`;
  const schedList = (title, rows) => (rows.length
    ? `<h4 class="detail__sub">${title}</h4><ul class="sched">${rows.join("")}</ul>`
    : "");
  const playedRows = completed.map((g) => `<li>${opponent(g)}`
    + `<span class="sched__result">${esc(`${g.scoreFor}–${g.scoreAgainst}`)} <span class="sched__wl sched__wl--${g.result}">${g.result}</span></span></li>`);
  const upcomingRows = upcoming.map((g) => `<li>${opponent(g)}${g.date ? `<span class="sched__date">${esc(gameDate(g.date))}</span>` : ""}</li>`);
  const coinFlip = complete && t.coin_flip_needed
    ? '<p class="detail__note">A coin flip is needed to settle a tie involving this team.</p>'
    : "";
  const record = `<section class="detail__panel" aria-label="Record">
      <h3 class="detail__title">Record</h3>
      <p class="detail__records">
        <span><strong>${esc(recordText(r.region_wins, r.region_losses, r.region_ties))}</strong> Region</span>
        <span><strong>${esc(recordText(r.wins, r.losses, r.ties))}</strong> Overall</span>
      </p>
      ${coinFlip}
      ${schedList("Completed region games", playedRows)}
      ${schedList("Remaining region games", upcomingRows)}
    </section>`;

  const seeding = `<section class="detail__panel" aria-label="Seeding odds">
      <h3 class="detail__title">Seeding odds</h3>
      <dl class="detail__odds">${ODDS_COLUMNS.map((c) => `<div><dt>${c.label}</dt><dd>${oddsCell(o[c.key])}</dd></div>`).join("")}</dl>
    </section>`;

  // Teams that made the playoffs keep their path after elimination: it
  // records how far they got.
  const path = t.eliminated && !t.clinched ? [] : playoffPath(t, mode, clazz);
  const pathPanel = path.length
    ? `<section class="detail__panel detail__panel--path" aria-label="Playoff path">
        <h3 class="detail__title">Playoff path</h3>
        <table class="path">
          <thead><tr><th scope="col">Round</th><th scope="col">Reaches</th><th scope="col">Hosts if there</th><th scope="col">Hosts overall</th></tr></thead>
          <tbody>${path.map((p) => `<tr>
            <th scope="row">${esc(p.round)}</th>
            <td>${oddsCell(p.reach)}</td>
            <td>${p.neutral ? '<span class="muted">Neutral</span>' : p.hostIfReach == null ? "" : esc(formatPct(p.hostIfReach))}</td>
            <td>${p.hostOverall == null ? "" : esc(formatPct(p.hostOverall))}</td>
          </tr>`).join("")}</tbody>
        </table>
      </section>`
    : "";
  return `<div class="detail__panels">${record}${seeding}${pathPanel}</div>`;
}

function focusTeamRow() {
  document.getElementById("focus-row")?.scrollIntoView({ block: "center" });
}

app.addEventListener("click", (e) => {
  const info = e.target.closest(".info-button");
  if (info) {
    const open = info.getAttribute("aria-expanded") === "true";
    info.setAttribute("aria-expanded", String(!open));
    document.getElementById(info.getAttribute("aria-controls")).hidden = open;
    return;
  }
  const toggle = e.target.closest(".row-toggle");
  if (!toggle) {
    const link = e.target.closest("a[href^='/?']");
    if (link && !e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) {
      e.preventDefault();
      navigate(link.getAttribute("href"), { scroll: !link.hasAttribute("data-keep-scroll") });
    }
    return;
  }
  // Picking a row selects that team (its playoff path opens and the
  // scenarios narrow to it); picking it again clears the selection.
  const selected = toggle.getAttribute("aria-expanded") === "true";
  navigate(hrefWith({ team: selected ? null : toggle.dataset.team }));
});

/** Region games as a card grid under a heading for each game day. */
function gamesSection(id, title, games, teams, focus) {
  const days = byDay(games).map(({ date, items }) => `<div class="game-day">
      <h3 class="game-day__title">${date ? esc(gameDate(date)) : "Date to be announced"}</h3>
      <ul class="game-grid">${items.map((g) => gameCard(g, teams, { focus })).join("")}</ul>
    </div>`);
  return `<section class="section" aria-labelledby="${id}-title">
    <h2 class="section-title" id="${id}-title">${title}</h2>
    ${days.join("")}
  </section>`;
}

// ------------------------------------------------------------ scenarios

function scenariosSection(data, teams, prov, mode, focus) {
  const cardHtml = (c) => scenarioCard({ ...c, team: teams[c.team], teams, provenanceHtml: prov });
  const grid = (cards) => `<div class="scenario-grid">${cards.map(cardHtml).join("")}</div>`;
  const forFocus = (cards) => (focus ? cards.filter((c) => c.team === focus) : cards);
  const remainingCount = data.remaining_games.length;
  const focusNote = focus
    ? `<p class="focus-note">Showing ${esc(focus)} only. <a href="${esc(hrefWith({ team: null }))}" data-keep-scroll>Show every team</a></p>`
    : "";

  let body;
  if (data.scenarios_available && data.teams.some((t) => t.paths?.length)) {
    const g = outcomeCards(data.teams, mode);
    const title = forFocus(g.title);
    const playoffs = forFocus(g.playoffs);
    const seeding = forFocus(g.seeding);
    // Every group folds away. Seeding matters less than who's in, and can
    // run long, so it starts closed — unless it's all there is, or the
    // reader picked one team.
    const parts = [
      ["The region title", title, true],
      ["Playoff spots", playoffs, true],
    ].filter(([, cards]) => cards.length).map(([label, cards, open]) => collapsible(label, cards.length, grid(cards), open));
    if (seeding.length) parts.push(collapsible("Seeding", seeding.length, grid(seeding), !parts.length || focus));
    body = parts.length
      ? parts.join("")
      : `<p class="prose muted">${focus ? `Nothing left to decide for ${esc(focus)}.` : "Every remaining outcome is already settled."}</p>`;
  } else {
    const cards = forFocus(insightCards(data.key_insights));
    const intro = `Full scenarios appear once six or fewer region games remain; ${remainingCount} are left.`;
    body = cards.length
      ? `<p class="prose muted">${esc(intro)} Until then, these are results that settle a spot no matter what else happens.</p>
         <div class="scenario-group scenario-group--spaced">${grid(cards)}</div>`
      : `<p class="prose muted">${esc(intro)}</p>`;
  }

  return `<section class="section" aria-labelledby="scen-title">
    <h2 class="section-title" id="scen-title">What has to happen</h2>
    ${focusNote}
    ${body}
  </section>`;
}

/** A foldable group of cards with a count beside its heading. */
function collapsible(label, count, body, open) {
  return `<details class="scenario-group"${open ? " open" : ""}>
    <summary><h3 class="sub-title">${label}</h3><span class="muted">${count} ${count === 1 ? "outcome" : "outcomes"}</span></summary>
    ${body}</details>`;
}

/**
 * Every distinct way the region can finish, one box each. Long lists start
 * folded so they don't bury the completed games below.
 */
function allScenariosSection(scenarios, teams, focus) {
  const cards = completeScenarioCards(scenarios);
  const open = cards.length <= 12;
  return `<section class="section" aria-labelledby="all-scen-title">
    <details class="scenario-group scenario-group--section"${open ? " open" : ""}>
      <summary><h2 class="section-title" id="all-scen-title">Scenarios</h2><span class="muted">${cards.length} ${cards.length === 1 ? "way" : "ways"} the region can finish</span></summary>
      <div class="scenario-grid">${cards.map((c) => outcomeScenarioCard(c, teams, { focus })).join("")}</div>
    </details>
  </section>`;
}

// --------------------------------------------------------------- boot

if (app) {
  window.addEventListener("popstate", render);
  render();
}
