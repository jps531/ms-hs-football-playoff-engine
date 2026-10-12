// 2026 interim UI: pick a class, pick a region, read that region's race.
// The path says what you're looking at and the query how (see routes.js):
//   /standings/7a           every region in 7A
//   /standings/7a/2         Region 2-7A
//   /brackets/7a            the 7A playoff bracket
//   ?season=2025&week=9&odds=tossup&team=oxford
// Defaults stay out of the URL, so a link to "now" is just the path.
// Moving between pages pushes history; changing the season, week, odds
// mode, or picked team replaces it, so Back goes to the previous page.

import { escapeHtml as esc, formatPct, recordText, shortDate, gameDate } from "./format.js";
import {
  oddsCell, provenance, statusBadges, teamMark, teamLabel, scenarioCard, classScrubber, chevronIcon,
  ODDS_MODES, modeLabel, infoButton, gameCard, outcomeScenarioCard,
} from "./components.js";
import { matchTeams } from "./search.js";
import { CLASSES, slugify, parseLocation, buildPath } from "./routes.js";
import {
  sideLabel, layoutResults, occupants, lockedTeam, gameState, hosting, matchups as gameMatchups,
  teamInGame, opponentsFor, pathGames, bracketStructure, positionName,
} from "./bracket.js";
import {
  outcomeCards, insightCards, oddsFor, hasProjectedOdds, completeScenarioCards,
} from "./scenarios.js";
import {
  standingPositions, playoffPath, regionGames, displayOrder, regionComplete, snapshotDate,
  orient, byDay, teamSchedule,
} from "./standings.js";

const API = "/api/v1";
const STORE = { clazz: "mshsf.class", odds: "mshsf.odds" };

const app = document.getElementById("app");
const scrubberHost = document.getElementById("scrubber");
const teamSearch = document.getElementById("team-search");
const resultsPopup = document.getElementById("team-results-popup");
const resultsList = document.getElementById("team-results");
const resultsEmpty = resultsPopup?.querySelector(".team-results__empty");
const searchStatus = document.getElementById("team-search-status");
const contextBar = document.getElementById("context-bar");

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
 * label correctly), oldest first: [{ week, label, firstDate, lastDate, end }].
 * A game day counts once it's over: today's games don't, since their
 * results only reach the numbers in the next morning's update.
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
    if (d.kind !== "games" || d.date >= now) continue;
    const prev = weeks.get(d.week);
    weeks.set(d.week, {
      week: d.week, label: d.description, firstDate: prev?.firstDate ?? d.date, lastDate: d.date, end: weekEnd(d.date),
    });
  }
  return [...weeks.values()].sort((a, b) => a.week - b.week);
}

// The newest snapshot seen per season and class. A week whose games haven't
// reached an update yet would only reload the same numbers, so the week list
// stops at the week this snapshot covers.
const latestAsOf = new Map();

/** Note the latest snapshot (when `date` was null) and trim weeks past it. */
function weeksUpToLatest(ctx, weeks, date, asOf) {
  const key = `${ctx.season}:${ctx.clazz}`;
  if (!date && asOf) latestAsOf.set(key, asOf);
  const latest = latestAsOf.get(key);
  return latest ? weeks.filter((w) => w.firstDate <= latest) : weeks;
}

// ------------------------------------------------------------- routing

function readRoute() {
  return { ...parseLocation(location.pathname, location.search), teamName: null };
}

let route = readRoute();
let currentSeason = null; // newest season, known once /seasons loads

/**
 * URL for the current route with some fields changed (null removes one).
 * `team` is a school name; the URL carries its slug. The landing page keeps
 * its "/" for view-state changes and only leaves it to change class or region.
 */
function hrefWith(changes) {
  const next = { ...route, ...changes };
  const moving = "clazz" in changes || "region" in changes;
  let page = next.page;
  if (!("page" in changes)) {
    if (route.page === "landing" && !moving) page = "landing";
    else if (route.page === "bracket" && !next.region) page = "bracket";
    else page = next.region ? "region" : "class";
  }
  const teamName = "team" in changes ? changes.team : route.teamName;
  return buildPath({ ...next, page, team: teamName ? slugify(teamName) : null }, { currentSeason });
}

/** Go to another page (push) or change how this one is shown (replace). */
function navigate(url, { scroll = false, replace = false } = {}) {
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  render();
  if (scroll) window.scrollTo(0, 0);
}

/** The school a `team` value names: its slug, or the name itself (old links). */
function resolveTeam(value, index) {
  if (!value) return null;
  const schools = Object.keys(index);
  return schools.find((s) => slugify(s) === value) ?? (value in index ? value : null);
}

/**
 * Rewrite the address bar to the canonical URL for what's on screen (old
 * query-string links, team names instead of slugs, a spelled-out default)
 * without adding a history entry.
 */
function canonicalize(season) {
  const storedOdds = stored(STORE.odds, (v) => v in ODDS_MODES);
  const canonical = buildPath({
    ...route,
    season,
    odds: route.odds ?? storedOdds,
    team: route.teamName ? slugify(route.teamName) : null,
  }, { currentSeason });
  if (canonical !== location.pathname + location.search) history.replaceState(null, "", canonical);
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
  if (route.page === "notfound") {
    renderScrubber(null);
    showContext(null);
    app.innerHTML = notice("There’s no page at this address. Pick a class above to find a region.");
    document.title = `Page not found — ${SITE}`;
    return;
  }
  const saved = Number(stored(STORE.clazz, (v) => CLASSES.includes(Number(v))));
  route.clazz ??= CLASSES.includes(saved) ? saved : CLASSES[0];
  store(STORE.clazz, route.clazz);
  renderScrubber(route.clazz);
  app.setAttribute("aria-busy", "true");
  try {
    const all = await seasons();
    currentSeason = all[0];
    const season = all.includes(route.season) ? route.season : all[0];
    route.season = season === currentSeason ? null : season;
    route.teamName = resolveTeam(route.team, await teamsBySchool(season));
    const ctx = { ...route, team: route.teamName, season, seasons: all, currentSeason };
    renderScrubber(route.clazz); // again, now that the picked team is known (the view links carry it)
    loadTeamSearch(season);
    const html = route.page === "bracket" ? await bracketView(ctx)
      : route.region ? await regionView(ctx) : await classView(ctx);
    if (token !== renderToken) return;
    app.innerHTML = html;
    if (route.page === "bracket") wireRoundStrips();
    showContext(nextContext);
    canonicalize(route.season);
    if (scrollToFocus && route.teamName && route.region) focusTeamRow();
    scrollToFocus = false;
  } catch (err) {
    if (token !== renderToken) return;
    showContext(null);
    app.innerHTML = notice(
      err?.status === 404
        ? "There’s nothing published for this yet. Try another week or season, or check back once region play is underway."
        : "This page couldn’t load right now. Please try again in a moment.",
    );
  } finally {
    if (token === renderToken) app.removeAttribute("aria-busy");
  }
  document.title = pageTitle(route.clazz, route.region, route.page);
}

// ---------------------------------------------------------- context bar
// Once the page title scrolls under the header, a slim bar takes its place
// saying what's on screen (region, week, date, odds mode), so a screenshot
// from anywhere down the page still carries its context. It repeats the
// visible title and controls, so it's hidden from screen readers.

let nextContext = null; // set by the view being rendered
let headObserver = null;

function contextHtml(title, summary, mode) {
  const sep = '<span class="sep" aria-hidden="true">·</span>';
  const parts = [`<span class="context-bar__title">${esc(title)}</span>`];
  if (summary?.week) parts.push(`<span>${esc(summary.week)}</span>`);
  if (summary?.date) parts.push(`<span>${esc(summary.date)}</span>`);
  if (mode) parts.push(modeLabel(mode));
  return parts.join(sep);
}

function showContext(html) {
  headObserver?.disconnect();
  contextBar.classList.remove("is-shown");
  contextBar.querySelector(".context-bar__inner").innerHTML = html ?? "";
  // The bar takes over as soon as the page title is out of view, not once
  // the whole heading block (headline and controls) has gone.
  const head = html && app.querySelector(".region-head .title, .entry-head .title");
  if (!head) return;
  const headerH = document.querySelector(".site-header-bar").getBoundingClientRect().height;
  headObserver = new IntersectionObserver(([entry]) => {
    const above = !entry.isIntersecting && entry.boundingClientRect.top < headerH;
    contextBar.classList.toggle("is-shown", above);
  }, { rootMargin: `-${Math.round(headerH)}px 0px 0px 0px` });
  headObserver.observe(head);
}

const SITE = "Mississippi High School Football";

function pageTitle(clazz, region, page) {
  if (page === "bracket") return `Class ${clazz}A playoff bracket — ${SITE}`;
  return region ? `Region ${region}-${clazz}A playoff race — ${SITE}` : `Class ${clazz}A playoff races — ${SITE}`;
}

function notice(text) {
  return `<div class="page"><p class="notice">${esc(text)}</p></div>`;
}

// ------------------------------------------------------------ scrubber

function renderScrubber(clazz) {
  scrubberHost.innerHTML = classScrubber(CLASSES, clazz) + (clazz ? viewTabs() : "");
  scrubberHost.querySelector('[aria-checked="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

/**
 * Standings / Bracket: the two views of the current class. Switching keeps
 * the class, season, week, odds mode, and picked team.
 */
function viewTabs() {
  const onBracket = route.page === "bracket";
  const tab = (label, href, current) => `<a class="view-tabs__item" href="${esc(href)}"${current ? ' aria-current="page"' : ""}>${label}</a>`;
  return `<nav class="view-tabs" aria-label="View">
    ${tab("Standings", hrefWith({ page: route.region ? "region" : "class" }), !onBracket)}
    ${tab("Bracket", hrefWith({ page: "bracket", region: null }), onBracket)}
  </nav>`;
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
// A combobox: typing lists matching teams under the field (best first, the
// top one highlighted), arrow keys move the highlight, and Enter or a tap
// opens that team's region. Nothing navigates until the reader commits.

let teamSearchSeason = null;
let teamIndex = {};
let matches = [];
let active = -1;

async function loadTeamSearch(season) {
  if (!teamSearch || teamSearchSeason === season) return;
  teamSearchSeason = season;
  teamIndex = await teamsBySchool(season);
  if (document.activeElement === teamSearch && teamSearch.value.trim()) updateResults();
}

function openResults(open) {
  resultsPopup.hidden = !open;
  teamSearch.setAttribute("aria-expanded", String(open && matches.length > 0));
  if (!open) teamSearch.removeAttribute("aria-activedescendant");
}

function setActive(i) {
  active = i;
  resultsList.querySelectorAll("[role=option]").forEach((el, k) => el.setAttribute("aria-selected", String(k === i)));
  const el = i >= 0 ? document.getElementById(`team-opt-${i}`) : null;
  if (el) {
    teamSearch.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  } else {
    teamSearch.removeAttribute("aria-activedescendant");
  }
}

function updateResults() {
  const query = teamSearch.value.trim();
  if (!query) {
    matches = [];
    searchStatus.textContent = "";
    openResults(false);
    return;
  }
  const loaded = Object.keys(teamIndex).length > 0;
  matches = matchTeams(Object.values(teamIndex), query);
  resultsList.innerHTML = matches.map((t, i) => `<li id="team-opt-${i}" role="option" aria-selected="false" data-index="${i}">
      ${teamMark(t.school, t)}<span class="team-results__name">${esc(t.school)}</span>
      <span class="team-results__meta">${t.class_}A · Region ${t.region}</span>
    </li>`).join("");
  resultsEmpty.hidden = matches.length > 0;
  resultsEmpty.textContent = loaded ? `No team matches “${query}”.` : "Loading teams…";
  searchStatus.textContent = !loaded ? ""
    : matches.length ? `${matches.length} ${matches.length === 1 ? "team" : "teams"} found. Press Enter to open ${matches[0].school}.`
      : "No teams found.";
  openResults(true);
  setActive(matches.length ? 0 : -1);
}

function goToTeam(team) {
  teamSearch.value = "";
  matches = [];
  openResults(false);
  teamSearch.blur();
  scrollToFocus = true;
  navigate(hrefWith({ clazz: team.class_, region: team.region, team: team.school }), { scroll: true });
}

teamSearch?.addEventListener("input", updateResults);
teamSearch?.addEventListener("focus", () => { if (teamSearch.value.trim()) updateResults(); });
teamSearch?.addEventListener("blur", () => openResults(false));

teamSearch?.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    if (resultsPopup.hidden) updateResults();
    if (!matches.length) return;
    e.preventDefault();
    const step = e.key === "ArrowDown" ? 1 : -1;
    setActive((active + step + matches.length) % matches.length);
  } else if (e.key === "Escape") {
    if (!resultsPopup.hidden) {
      e.preventDefault();
      openResults(false);
    }
  }
});

// Enter (or the keyboard's Search key) commits the highlighted team.
teamSearch?.closest("form")?.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!teamSearch.value.trim()) return;
  if (resultsPopup.hidden) updateResults();
  const team = matches[active] ?? matches[0];
  if (team) goToTeam(team);
});

// Pressing a result mustn't blur the field first (that would close the list
// before the tap lands); the click then opens the team.
resultsList?.addEventListener("pointerdown", (e) => e.preventDefault());
resultsList?.addEventListener("click", (e) => {
  const option = e.target.closest("[role=option]");
  if (option) goToTeam(matches[Number(option.dataset.index)]);
});
resultsList?.addEventListener("pointermove", (e) => {
  const option = e.target.closest("[role=option]");
  if (option && Number(option.dataset.index) !== active) setActive(Number(option.dataset.index));
});

// ---------------------------------------------------- provenance controls
// The page's provenance line doubles as its controls: which season, through
// which week, and which odds mode. Cards repeat it as plain text.

function select(name, label, options, selected) {
  const opts = options.map((o) => `<option value="${esc(o.value)}"${String(o.value) === String(selected) ? " selected" : ""}>${esc(o.label)}</option>`);
  return `<label class="inline-select"><span class="visually-hidden">${esc(label)}</span><select data-control="${name}">${opts.join("")}</select></label>`;
}

/** What the controls line shows, for the context bar: { week, date }. */
let controlsSummary = null;

function controlsLine(ctx, weeks, { asOf, mode, projectedAvailable }) {
  controlsSummary = { week: null, date: asOf ? `Updated ${shortDate(asOf)}` : null };
  const sep = '<span class="sep" aria-hidden="true">·</span>';
  const parts = [];
  parts.push(select("season", "Season", ctx.seasons.map((s) => ({ value: s, label: `${s} season` })), ctx.season));
  if (weeks.length) {
    // Without an explicit week, show the week the snapshot actually covers,
    // which can trail the calendar (e.g. before the morning recompute).
    const covered = asOf ? [...weeks].reverse().find((w) => w.firstDate <= asOf) : null;
    const chosen = ctx.week && weeks.some((w) => w.week === ctx.week)
      ? ctx.week
      : (covered ?? weeks[weeks.length - 1]).week;
    const options = [...weeks].reverse().map((w) => ({ value: w.week, label: w.label }));
    const shown = weeks.find((w) => w.week === chosen);
    parts.push(`<span class="ctl">Through ${select("week", "Through week", options, chosen)}</span>`);
    // The date is what the data actually covers. When the newest snapshot
    // predates the chosen week's games (e.g. no post-round playoff snapshot
    // was written), say so instead of implying the week's date.
    if (shown && asOf && asOf < shown.lastDate) {
      parts.push(`<span>Latest update ${esc(shortDate(asOf))}</span>`);
      controlsSummary = { week: shown.label, date: `Latest update ${shortDate(asOf)}` };
    } else if (shown) {
      parts.push(`<span>${esc(shortDate(shown.lastDate))}</span>`);
      controlsSummary = { week: shown.label, date: shortDate(shown.lastDate) };
    }
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
    navigate(hrefWith({ season: Number(value), week: null, team: null }), { replace: true });
  } else if (control.dataset.control === "week") {
    const latest = control.options[0].value; // options run newest first
    navigate(hrefWith({ week: value === latest ? null : Number(value) }), { replace: true });
  } else if (control.dataset.control === "odds") {
    store(STORE.odds, value);
    navigate(hrefWith({ odds: value }), { replace: true });
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
  const shownWeeks = weeksUpToLatest(ctx, weeks, date, data.as_of_date);
  const allTeams = data.regions.flatMap((r) => r.teams);
  const projectedAvailable = hasProjectedOdds(allTeams);
  const mode = projectedAvailable ? oddsMode(ctx) : "tossup";

  const head = `<div class="page entry-head">
    <h1 class="title">Class ${clazz}A</h1>
    ${controlsLine(ctx, shownWeeks, { asOf: data.as_of_date, mode, projectedAvailable })}
  </div>`;
  nextContext = contextHtml(`Class ${clazz}A`, controlsSummary, mode);
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
        <th scope="row" class="col-team"><a class="team-link" href="${esc(hrefWith({ region: r.region, team: t.school }))}">${teamMark(t.school, teams[t.school])}<span class="row-toggle__label"><span class="team-name">${esc(t.school)}</span>${statusBadges(t, { regionComplete: complete, clazz })}</span></a></th>
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
  const { results, upcoming } = regionGames(games, data.as_of_date);
  const shownWeeks = weeksUpToLatest(ctx, weeks, date, data.as_of_date);

  const projectedAvailable = hasProjectedOdds(data.teams);
  const mode = projectedAvailable ? oddsMode(ctx) : "tossup";
  const focus = data.teams.some((t) => t.school === ctx.team) ? ctx.team : null;

  // Cards carry the same provenance as plain text, so a cropped screenshot
  // of one still says what it shows.
  const shownWeek = [...shownWeeks].reverse().find((w) => w.firstDate <= data.as_of_date);
  const cardProv = provenance(
    { label: shownWeek?.label, date: shownWeek?.lastDate ?? data.as_of_date, mode },
    shortDate,
  );

  // Home and away come from the schedule when it lists the game; the
  // standings' remaining-games list often doesn't know the site.
  const remaining = (data.remaining_games ?? []).map((g) => {
    const listed = upcoming(g.team_a, g.team_b);
    if (listed && (listed.joiner === "at" || !g.location_a)) return listed;
    return { date: listed?.date ?? null, ...orient(g.team_a, g.team_b, g.location_a) };
  });
  const schedule = { results, remaining };
  const controls = controlsLine(ctx, shownWeeks, { asOf: data.as_of_date, mode, projectedAvailable });
  nextContext = contextHtml(`Region ${region}-${clazz}A`, controlsSummary, mode);
  return `<div class="page">
    <header class="region-head">
      <p class="region-head__links">
        <a href="${esc(hrefWith({ region: null, team: null }))}">All ${clazz}A regions</a>
        <a href="${esc(hrefWith({ page: "bracket", region: null }))}">${clazz}A bracket</a>
      </p>
      <h1 class="title">Region ${region}-${clazz}A</h1>
      ${data.headline ? `<p class="headline">${esc(data.headline)}</p>` : ""}
      ${controls}
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
            ${chevronIcon}${teamMark(t.school, teams[t.school])}<span class="row-toggle__label"><span class="team-name">${esc(t.school)}</span>${statusBadges(t, { regionComplete: complete, clazz })}</span>
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
        <p class="detail__link"><a href="${esc(hrefWith({ page: "bracket", region: null, team: t.school }))}">See ${esc(t.school)}’s path in the bracket</a></p>
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
    // In-app links render in place: a page link adds history, a link that
    // only changes how this page is shown (data-replace) doesn't.
    const link = e.target.closest("a[href^='/standings/'], a[href^='/brackets/'], a[href^='/?'], a[href='/']");
    if (link && !e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) {
      e.preventDefault();
      navigate(link.getAttribute("href"), {
        scroll: !link.hasAttribute("data-keep-scroll"),
        replace: link.hasAttribute("data-replace"),
      });
    }
    return;
  }
  // Picking a row selects that team (its playoff path opens and the
  // scenarios narrow to it); picking it again clears the selection.
  const selected = toggle.getAttribute("aria-expanded") === "true";
  navigate(hrefWith({ team: selected ? null : toggle.dataset.team }), { replace: true });
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
    ? `<p class="focus-note">Showing ${esc(focus)} only. <a href="${esc(hrefWith({ team: null }))}" data-keep-scroll data-replace>Show every team</a></p>`
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

// ------------------------------------------------------------- bracket
// One class's playoff bracket, built for the undetermined state: an open
// side lists who might fill it with reach odds; a locked side is a fact (a
// lock, the seed, no percentage); a played game is a result. Each game
// expands in place to say who might play here and who'd host — from a
// picked team's side when one is picked. Hosting comes from the API.

const LIST_CAP = 5; // occupants shown before "Show all"
const MATCHUP_CAP = 6; // matchups / opponents shown before "Show all"

/** Bracket UI state that isn't in the URL; reset when the class changes. */
const bracketUi = { key: null, open: null, showAll: new Set(), half: "both", focus: null };
let bracketData = null; // what the last bracket render used, for in-place updates

async function bracketView(ctx) {
  const { season, clazz } = ctx;
  const weeks = await playedWeeks(season, clazz);
  const date = dateParam(ctx, weeks);
  const dq = date ? `&date=${date}` : "";
  const [layoutRes, matchupRes, standings, teams] = await Promise.all([
    getJSON(`/bracket?season=${season}&class=${clazz}${dq}`).catch(() => null),
    getJSON(`/bracket/matchups?season=${season}&class=${clazz}${dq}`),
    getJSON(`/standings/${clazz}?season=${season}${dq}`).catch(() => null),
    teamsBySchool(season),
  ]);
  const shownWeeks = weeksUpToLatest(ctx, weeks, date, matchupRes.as_of_date);
  const games = matchupRes.games;
  const projectedAvailable = games.some((g) => g.side_a.occupants.some((o) => o.p_reach_weighted != null));
  const mode = projectedAvailable ? oddsMode(ctx) : "tossup";

  // A locked team's seed, for its "Region 3 champion" label.
  const seeds = {};
  for (const r of standings?.regions ?? []) {
    for (const t of r.teams) {
      const s = [1, 2, 3, 4].find((k) => (t.odds?.[`p${k}`] ?? 0) >= 0.999);
      if (s) seeds[t.school] = { region: r.region, seed: s };
    }
  }

  const key = `${season}:${clazz}`;
  if (bracketUi.key !== key) {
    // Phones show one half at a time; wide screens start with both.
    const half = matchMedia("(max-width: 48em)").matches ? "N" : "both";
    Object.assign(bracketUi, { key, open: null, showAll: new Set(), half, focus: null });
  }
  // One half at a time (phones): show the picked team's half when the pick changes.
  if (ctx.team !== bracketUi.focus) {
    bracketUi.focus = ctx.team;
    const first = ctx.team && bracketUi.half !== "both"
      ? games.find((g) => g.id !== "final" && teamInGame(g, ctx.team, mode)?.p > 0)
      : null;
    if (first) bracketUi.half = first.half;
  }
  bracketData = {
    games, results: layoutResults(layoutRes?.bracket_layout), teams, seeds, mode, focus: ctx.team, clazz,
  };

  const controls = controlsLine(ctx, shownWeeks, { asOf: matchupRes.as_of_date, mode, projectedAvailable });
  nextContext = contextHtml(`${clazz}A bracket`, controlsSummary, mode);
  const focusNote = ctx.team
    ? `<p class="focus-note">Showing ${esc(ctx.team)}’s possible path. <a href="${esc(hrefWith({ team: null }))}" data-keep-scroll data-replace>Show every team</a></p>`
    : `<p class="focus-note muted">Pick a team to see its possible path and opponents.</p>`;
  return `<div class="page">
    <header class="entry-head bracket-head">
      <h1 class="title">Class ${clazz}A bracket</h1>
      ${controls}
      ${focusNote}
    </header>
    <div id="bracket-host">${bracketHtml()}</div>
  </div>`;
}

const HALF_NAMES = { N: "North", S: "South" };
const ROUND_SHORT = { "First Round": "1st Rd", "Second Round": "2nd Rd", Quarterfinals: "Quarters", Semifinals: "Semis", "Championship Game": "Final" };
const shortRound = (name) => ROUND_SHORT[name] ?? name;

/** Render the bracket from bracketData and bracketUi. */
function bracketHtml() {
  const { games, mode, focus } = bracketData;
  const { halves, final } = bracketStructure(games);
  const path = focus ? pathGames(games, focus, mode) : null;
  const halfControl = halves.length > 1
    ? `<div class="half-control" role="group" aria-label="Bracket half">
        ${["both", ...halves.map((h) => h.half)].map((h) => `<button type="button" class="half-control__item${h === "both" ? " half-control__item--both" : ""}" data-half="${h}" aria-pressed="${bracketUi.half === h}">${h === "both" ? "Both halves" : HALF_NAMES[h] ?? h}</button>`).join("")}
      </div>`
    : "";
  const finalCol = final
    ? `<div class="bracket-col bracket-col--final">
        <h3 class="bracket-col__title">${esc(final.round)}</h3>
        <div class="bracket-col__games">${bracketGame(final, path, "inline")}</div>
      </div>`
    : "";
  const halfBlocks = halves.map(({ half, rounds }) => {
    const names = [...rounds.map((r) => r.name), ...(final ? [final.round] : [])];
    return `<section class="bracket-half" data-half="${half}" aria-label="${HALF_NAMES[half] ?? half} half">
      ${halves.length > 1 ? `<h2 class="sub-title bracket-half__title">${HALF_NAMES[half] ?? half}</h2>` : ""}
      <div class="round-tabs" role="group" aria-label="Rounds">
        ${names.map((n, i) => `<button type="button" class="round-tabs__item" data-round-jump="${i}" aria-current="${i === 0}">${esc(shortRound(n))}</button>`).join("")}
      </div>
      <div class="bracket-rounds">
        ${rounds.map((r) => `<div class="bracket-col">
            <h3 class="bracket-col__title">${esc(r.name)}</h3>
            <div class="bracket-col__games">${r.games.map((g) => bracketGame(g, path)).join("")}</div>
          </div>`).join("")}
        ${finalCol}
      </div>
    </section>`;
  });
  const finalBlock = final
    ? `<section class="bracket-final" aria-labelledby="final-title">
        <h2 class="sub-title" id="final-title">${esc(final.round)}</h2>
        ${bracketGame(final, path, "wide")}
      </section>`
    : "";
  return `<div class="bracket" data-half="${bracketUi.half}">${halfControl}${halfBlocks.join("")}${finalBlock}</div>`;
}

/** A team's seed label once it's locked: "Region 3 champion". */
function seedLabel(team) {
  const s = bracketData.seeds[team];
  return s ? positionName(s) : null;
}

const LOCK = '<svg class="lock" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3.5" y="7" width="9" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg>';

/** A team name that picks the team when tapped (shared with the standings via ?team=). */
function pickTeam(team) {
  const { teams, focus } = bracketData;
  const mine = team === focus;
  return `<button type="button" class="bteam__name${mine ? " is-focus" : ""}" data-pick-team="${esc(team)}" aria-pressed="${mine}">${teamMark(team, teams[team])}<span class="team-name">${esc(team)}</span></button>`;
}

/** Which side hosts this game whoever reaches it, if that's settled: "a", "b", "neutral", or null. */
function settledHost(game) {
  if (game.id === "final") return "neutral";
  const ms = gameMatchups(game, bracketData.mode);
  if (!ms.length) return null;
  const hosts = new Set(ms.map((m) => hosting(m.hostA).host));
  return hosts.size === 1 && !hosts.has("split") ? [...hosts][0] : null;
}

/** One side of a game card: a result row, a locked team, or the list of who might fill it. */
function bracketSide(game, sideKey, result, host) {
  const { mode } = bracketData;
  const side = sideKey === "a" ? game.side_a : game.side_b;
  const homeTag = host === sideKey ? '<span class="bteam__home">Home</span>' : "";
  if (result) {
    const team = lockedTeam(side) ?? (sideKey === "a" ? result.winner : result.loser);
    const won = team === result.winner;
    const score = won ? result.winnerScore : result.loserScore;
    return `<div class="bteam bteam--result${won ? " is-winner" : ""}">${pickTeam(team)}${score != null ? `<span class="bteam__score">${esc(score)}</span>` : ""}</div>`;
  }
  const locked = lockedTeam(side);
  if (locked) {
    const label = seedLabel(locked);
    return `<div class="bteam bteam--locked">${pickTeam(locked)}<span class="bteam__fact">${LOCK}<span class="visually-hidden">Locked in: </span>${label ? esc(label) : "Clinched"}</span>${homeTag}</div>`;
  }
  const list = occupants(side, mode);
  const allKey = `${game.id}:${sideKey}`;
  const showAll = bracketUi.showAll.has(allKey);
  const shown = showAll ? list : list.slice(0, LIST_CAP);
  const firstRound = side.feeders.length === 1;
  const label = firstRound || homeTag ? `<p class="bside__label">${firstRound ? esc(sideLabel(side.feeders)) : ""}${homeTag}</p>` : "";
  const more = list.length > LIST_CAP
    ? `<button type="button" class="bside__more" data-show-all="${esc(allKey)}" aria-expanded="${showAll}">${showAll ? "Show fewer" : `Show all ${list.length}`}</button>`
    : "";
  if (!list.length) return `<div class="bside">${label}<p class="bside__empty muted">No team can get here</p></div>`;
  return `<div class="bside">${label}<ul class="bside__list">${shown.map((o) => `<li class="bteam">${pickTeam(o.team)}${oddsCell(o.p)}</li>`).join("")}</ul>${more}</div>`;
}

const STATE_LABEL = { played: "Final", determined: "Matchup set", partial: "One spot set", projected: "" };

/** A game card: two sides, and an in-place expansion with who might play here. */
function bracketGame(game, path, variant = "") {
  const result = bracketData.results[game.id] ?? null;
  const state = gameState(game, result);
  const open = bracketUi.open === game.id;
  const host = result ? null : settledHost(game);
  const onPath = path ? path.has(game.id) : null;
  const cls = ["bgame", `bgame--${state}`, open ? "is-open" : "", onPath === true ? "is-path" : "", onPath === false ? "is-off" : ""]
    .filter(Boolean).join(" ");
  const detailId = `bd-${game.id}${variant ? `-${variant}` : ""}`;
  const stateLabel = STATE_LABEL[state] ? `<p class="bgame__state">${STATE_LABEL[state]}</p>` : "";
  const joiner = host === "a" || host === "b" ? "at" : "vs";
  return `<article class="${cls}" data-game="${esc(game.id)}">
    ${stateLabel}
    ${host === "a" ? bracketSide(game, "b", result, host) : bracketSide(game, "a", result, host)}
    <div class="bgame__vs" aria-hidden="true"><span>${joiner}</span></div>
    ${host === "a" ? bracketSide(game, "a", result, host) : bracketSide(game, "b", result, host)}
    ${host === "neutral" ? '<p class="bgame__site muted">Neutral site</p>' : ""}
    ${result ? "" : `<button type="button" class="bgame__toggle" data-game-toggle="${esc(game.id)}" aria-expanded="${open}" aria-controls="${detailId}">${open ? "Hide" : "Who might play here"}${chevronIcon}</button>
    <div class="bgame__detail" id="${detailId}"${open ? "" : " hidden"}>${open ? gameDetail(game) : ""}</div>`}
  </article>`;
}

/** Host wording from one team's point of view. */
function hostText(team, hosts, pTeamHosts) {
  if (hosts === "neutral") return "Neutral site";
  if (hosts === "team") return `${team} hosts`;
  if (hosts === "opponent") return "Away";
  return `${team} hosts ${formatPct(pTeamHosts)}`;
}

/** Expanded game: a picked team's opponents here, or both sides and the likeliest matchups. */
function gameDetail(game) {
  const { mode, focus, teams } = bracketData;
  if (game.matchups == null) {
    return `<p class="bgame__note muted">${esc(game.notes?.[0] ?? "Matchup odds aren’t available for this game yet.")}</p>`;
  }
  const here = focus ? teamInGame(game, focus, mode) : null;
  if (here && (here.p > 0 || here.locked)) {
    const opp = opponentsFor(game, focus, mode);
    const key = `${game.id}:opp`;
    const showAll = bracketUi.showAll.has(key);
    const shown = showAll ? opp : opp.slice(0, MATCHUP_CAP);
    const intro = here.locked ? `${focus}’s possible opponents here` : `If ${focus} gets here (${formatPct(here.p)} chance)`;
    return `<h4 class="bgame__heading">${esc(intro)}</h4>
      <ol class="opp-list">${shown.map((o) => `<li>${teamLabel(o.opponent, teams)}${oddsCell(o.p)}<span class="opp-list__host">${esc(hostText(focus, o.hosts, o.pTeamHosts))}</span></li>`).join("")}</ol>
      ${opp.length > MATCHUP_CAP ? `<button type="button" class="bside__more" data-show-all="${esc(key)}" aria-expanded="${showAll}">${showAll ? "Show fewer" : `Show all ${opp.length}`}</button>` : ""}`;
  }
  const ms = gameMatchups(game, mode);
  const key = `${game.id}:m`;
  const showAll = bracketUi.showAll.has(key);
  const shown = showAll ? ms : ms.slice(0, MATCHUP_CAP);
  const other = game.other ? (mode === "projected" && game.other.p_matchup_weighted != null ? game.other.p_matchup_weighted : game.other.p_matchup) : 0;
  const sides = [game.side_a, game.side_b].map((side) => {
    const n = occupants(side, mode).length;
    return `<div><h4 class="bgame__heading">${esc(sideLabel(side.feeders))}</h4><p class="muted bgame__count">${n} possible ${n === 1 ? "team" : "teams"}</p></div>`;
  }).join('<p class="bgame__sides-vs muted" aria-hidden="true">vs</p>');
  const rows = shown.map((m) => {
    const h = hosting(m.hostA);
    const where = h.host === "neutral" ? "Neutral site" : h.host === "a" ? `${m.a} hosts` : h.host === "b" ? `${m.b} hosts` : `${m.a} hosts ${formatPct(h.p)}`;
    return `<li><span class="mu__teams">${teamLabel(m.a, teams)}<span class="vs">vs</span>${teamLabel(m.b, teams)}</span>${oddsCell(m.p)}<span class="opp-list__host">${esc(where)}</span></li>`;
  });
  return `<div class="bgame__sides">${sides}</div>
    <h4 class="bgame__heading">Most likely matchups</h4>
    <ol class="opp-list opp-list--matchups">${rows.join("")}</ol>
    ${ms.length > MATCHUP_CAP ? `<button type="button" class="bside__more" data-show-all="${esc(key)}" aria-expanded="${showAll}">${showAll ? "Show fewer" : `Show all ${ms.length}`}</button>` : ""}
    ${other >= 0.0005 ? `<p class="muted bgame__count">Other pairings, each under 0.5%: ${esc(formatPct(other))} combined</p>` : ""}`;
}

/** Re-render the bracket in place (expansion, show-all, half), keeping each round strip's scroll. */
function rerenderBracket() {
  const host = document.getElementById("bracket-host");
  if (!host || !bracketData) return;
  const scrolls = [...host.querySelectorAll(".bracket-rounds")].map((el) => el.scrollLeft);
  host.innerHTML = bracketHtml();
  host.querySelectorAll(".bracket-rounds").forEach((el, i) => { el.scrollLeft = scrolls[i] ?? 0; });
  wireRoundStrips();
}

/** Keep each half's round tabs in step with its horizontal scroll (phones). */
function wireRoundStrips() {
  document.querySelectorAll(".bracket-half").forEach((half) => {
    const strip = half.querySelector(".bracket-rounds");
    const tabs = [...half.querySelectorAll("[data-round-jump]")];
    if (!strip || !tabs.length) return;
    const sync = () => {
      const cols = [...strip.querySelectorAll(".bracket-col")].filter((c) => c.offsetParent !== null);
      const x = strip.scrollLeft;
      let current = 0;
      cols.forEach((c, i) => { if (c.offsetLeft - cols[0].offsetLeft <= x + 8) current = i; });
      // The last round can't scroll to the left edge; at the end of the strip it's the current one.
      if (x + strip.clientWidth >= strip.scrollWidth - 8) current = cols.length - 1;
      tabs.forEach((t, i) => t.setAttribute("aria-current", String(i === current)));
    };
    strip.addEventListener("scroll", sync, { passive: true });
    sync();
  });
}

app.addEventListener("click", (e) => {
  const toggle = e.target.closest("[data-game-toggle]");
  if (toggle) {
    const id = toggle.dataset.gameToggle;
    bracketUi.open = bracketUi.open === id ? null : id;
    rerenderBracket();
    document.querySelector(`[data-game="${CSS.escape(id)}"] [data-game-toggle]`)?.focus({ preventScroll: true });
    return;
  }
  const more = e.target.closest("[data-show-all]");
  if (more) {
    const k = more.dataset.showAll;
    if (bracketUi.showAll.has(k)) bracketUi.showAll.delete(k);
    else bracketUi.showAll.add(k);
    rerenderBracket();
    return;
  }
  const half = e.target.closest(".half-control [data-half]");
  if (half) {
    bracketUi.half = half.dataset.half;
    rerenderBracket();
    return;
  }
  const jump = e.target.closest("[data-round-jump]");
  if (jump) {
    const strip = jump.closest(".bracket-half").querySelector(".bracket-rounds");
    const cols = [...strip.querySelectorAll(".bracket-col")].filter((c) => c.offsetParent !== null);
    const col = cols[Number(jump.dataset.roundJump)];
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (col) strip.scrollTo({ left: col.offsetLeft - cols[0].offsetLeft, behavior: smooth ? "smooth" : "auto" });
    return;
  }
  const pick = e.target.closest("[data-pick-team]");
  if (pick) {
    const team = pick.dataset.pickTeam;
    navigate(hrefWith({ team: bracketData?.focus === team ? null : team }), { replace: true });
  }
});

// --------------------------------------------------------------- boot

if (app) {
  window.addEventListener("popstate", render);
  render();
}
