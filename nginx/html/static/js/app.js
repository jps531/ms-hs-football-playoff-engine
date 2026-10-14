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
import { mountTurnstile, removeTurnstile, resetTurnstile, turnstileToken } from "./turnstile.js";
import { CLASSES, slugify, parseLocation, buildPath } from "./routes.js";
import {
  CATEGORIES, MESSAGE_MAX, NOTE_MAX, MIN_FILL_MS, feedbackProblem, feedbackBody, scoreProblem, scoreBody, submissionError,
} from "./feedback.js";
import {
  sideLabel, layoutResults, occupants, lockedTeam, gameState, hosting, matchups as gameMatchups,
  teamInGame, opponentsFor, pathGames, bracketStructure, positionName, treeColumns, treeLayout,
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
async function navigate(url, { scroll = false, replace = false } = {}) {
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  const token = renderToken + 1;
  await render();
  // Go to the top once the new page is in (not while the old one is still showing).
  if (scroll && token === renderToken) window.scrollTo(0, 0);
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
    document.body.classList.remove("is-wide");
    showContext(null);
    app.innerHTML = notice("There’s no page at this address. Pick a class above to find a region.");
    document.title = `Page not found — ${SITE}`;
    return;
  }
  const saved = Number(stored(STORE.clazz, (v) => CLASSES.includes(Number(v))));
  route.clazz ??= CLASSES.includes(saved) ? saved : CLASSES[0];
  store(STORE.clazz, route.clazz);
  renderScrubber(route.clazz);
  if (route.page === "feedback") {
    document.body.classList.remove("is-wide");
    showContext(null);
    app.innerHTML = feedbackPage();
    document.title = `Send feedback — ${SITE}`;
    mountTurnstile(app.querySelector("[data-fb-form]"), API);
    return;
  }
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
    // Re-rendering the same bracket (a team picked, odds changed) keeps each round strip where it was.
    const strip = route.page === "bracket" ? app.querySelector(".tree")?.scrollLeft ?? 0 : 0;
    app.innerHTML = html;
    document.body.classList.toggle("is-wide", route.page === "bracket");
    if (route.page === "bracket") {
      const tree = app.querySelector(".tree");
      if (tree) tree.scrollLeft = strip;
      wireBracket();
    } else {
      sheet?.close();
    }
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
  if (page === "bracket") return `Class ${clazz}A Playoff Bracket — ${SITE}`;
  return region ? `Region ${region}-${clazz}A playoff race — ${SITE}` : `Class ${clazz}A playoff races — ${SITE}`;
}

function notice(text) {
  return `<div class="page"><p class="notice">${esc(text)}</p></div>`;
}

// ------------------------------------------------------------ scrubber

function renderScrubber(clazz) {
  scrubberHost.innerHTML = classScrubber(CLASSES, clazz, classHref);
  syncNav();
  // Keep the selected class in view sideways; never scroll the page itself.
  const strip = scrubberHost.querySelector(".scrubber");
  const on = strip?.querySelector('[aria-current="page"]');
  if (on && (on.offsetLeft < strip.scrollLeft || on.offsetLeft + on.offsetWidth > strip.scrollLeft + strip.clientWidth)) {
    strip.scrollLeft = on.offsetLeft - (strip.clientWidth - on.offsetWidth) / 2;
  }
}

/**
 * Main nav (header links and the phone tab bar): Standings and Bracket are
 * the two views of the current class, and switching keeps the class,
 * season, week, odds mode, and picked team.
 */
function syncNav() {
  const onBracket = route.page === "bracket";
  const onStandings = ["landing", "class", "region"].includes(route.page);
  const known = route.page !== "notfound";
  const targets = {
    standings: known ? hrefWith({ page: route.region ? "region" : "class" }) : "/",
    bracket: known ? hrefWith({ page: "bracket", region: null }) : "/brackets/1a",
  };
  for (const a of document.querySelectorAll("[data-nav]")) {
    const key = a.dataset.nav;
    if (key in targets) a.setAttribute("href", targets[key]);
    const current = known && (key === "bracket" ? onBracket : key === "standings" ? onStandings : false);
    if (current) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

// Standings and Bracket links render in place, like any in-app link.
document.addEventListener("click", (e) => {
  const link = e.target.closest('[data-nav="standings"], [data-nav="bracket"]');
  if (!link || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  navigate(link.getAttribute("href"), { scroll: true });
});

const classHref = (clazz) => hrefWith({ clazz, region: null, team: null, week: null });

scrubberHost.addEventListener("click", (e) => {
  const item = e.target.closest("[data-class]");
  if (!item || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  navigate(item.getAttribute("href"), { scroll: true });
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
        <a href="${esc(hrefWith({ page: "bracket", region: null }))}">${clazz}A Bracket</a>
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
  return `<div class="detail__panels">${record}${seeding}${pathPanel}</div>
    <p class="report-line"><button type="button" class="link-button" data-feedback="odds" data-team="${esc(t.school)}">Something look wrong for ${esc(t.school)}? Tell us</button></p>`;
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
  const report = id === "results"; // played games can be reported as a wrong score
  const days = byDay(games).map(({ date, items }) => `<div class="game-day">
      <h3 class="game-day__title">${date ? esc(gameDate(date)) : "Date to be announced"}</h3>
      <ul class="game-grid">${items.map((g) => gameCard(g, teams, { focus, report })).join("")}</ul>
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
    <p class="report-line"><button type="button" class="link-button" data-feedback="odds"${focus ? ` data-team="${esc(focus)}"` : ""}>See a scenario that can’t be right? Tell us</button></p>
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
const bracketUi = { key: null, open: null, showAll: new Set(), half: "both", focus: null }; // open: the game in the sheet
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

  // A locked team's seed, for its "Region 3 #1 Seed" label.
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
  bracketData.summary = controlsSummary; // for the game sheet's provenance line
  nextContext = contextHtml(`${clazz}A Bracket`, controlsSummary, mode);
  const focusNote = ctx.team
    ? `<p class="focus-note">Showing ${esc(ctx.team)}’s possible path. <a href="${esc(hrefWith({ team: null }))}" data-keep-scroll data-replace>Show every team</a></p>`
    : `<p class="focus-note muted">Tap a game to see who might play there, and pick a team to follow its path.</p>`;
  return `<div class="page">
    <header class="entry-head bracket-head">
      <h1 class="title">Class ${clazz}A Bracket</h1>
      ${controls}
      ${focusNote}
    </header>
    <div id="bracket-host">${bracketHtml()}</div>
  </div>`;
}

const HALF_NAMES = { N: "North", S: "South" };
const ROUND_SHORT = { "First Round": "R1", "Second Round": "R2", Quarterfinals: "QF", Semifinals: "SF", "Championship Game": "CG" };
const shortRound = (name) => ROUND_SHORT[name] ?? name;

// The bracket is a tree of columns (rounds, then the final). Cards have a
// fixed height so each game can sit exactly between the two that feed it,
// with lines joining them. On phones the columns scroll sideways one round
// at a time, and the layout condenses as you go: the round in front of you
// is a plain list, and later rounds space out to line up with it.
const CARD_H = 98; // px, a game card (two team rows)
const PITCH = CARD_H + 14; // card plus the gap below it
const narrow = () => matchMedia("(max-width: 48em)").matches;

/** Render the bracket from bracketData and bracketUi. */
function bracketHtml() {
  const { games, mode, focus } = bracketData;
  const structure = bracketStructure(games);
  const halves = structure.halves.map((h) => h.half);
  const cols = treeColumns(structure, bracketUi.half === "both" ? halves : [bracketUi.half]);
  const path = focus ? pathGames(games, focus, mode) : null;
  bracketData.cols = cols;
  bracketData.path = path;
  const halfControl = halves.length > 1
    ? `<div class="half-control" role="group" aria-label="Bracket half">
        ${["both", ...halves].map((h) => `<button type="button" class="half-control__item${h === "both" ? " half-control__item--both" : ""}" data-half="${h}" aria-pressed="${bracketUi.half === h}">${h === "both" ? "Both halves" : HALF_NAMES[h] ?? h}</button>`).join("")}
      </div>`
    : "";
  const tabs = `<div class="round-tabs" role="group" aria-label="Jump to a round">
      ${cols.map((c, i) => `<button type="button" class="round-tabs__item" data-round-jump="${i}" aria-current="${i === 0}" aria-label="${esc(c.name)}" title="${esc(c.name)}">${esc(shortRound(c.name))}</button>`).join("")}
    </div>`;
  const columns = cols.map((c) => `<section class="tcol" aria-label="${esc(c.name)}">
      <h3 class="tcol__title">${esc(c.name)}</h3>
      <ol class="tcol__body">${c.games.map(({ game }) => `<li class="tslot">${treeCard(game, path)}</li>`).join("")}</ol>
    </section>`).join("");
  return `${halfControl}${tabs}
    <div class="tree" style="--card-h:${CARD_H}px">
      <div class="tree__cols">${columns}<svg class="tree__lines" aria-hidden="true"></svg></div>
    </div>`;
}

/** A team's seed label once it's locked: "Region 3 #1 Seed". */
function seedLabel(team) {
  const s = bracketData.seeds[team];
  return s ? positionName(s) : null;
}

const LOCK = '<svg class="lock" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3.5" y="7" width="9" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg>';
const CLOSE = '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>';

/** Which side hosts this game whoever reaches it, if that's settled: "a", "b", "neutral", or null. */
function settledHost(game) {
  if (game.id === "final") return "neutral";
  const ms = gameMatchups(game, bracketData.mode);
  if (!ms.length) return null;
  const hosts = new Set(ms.map((m) => hosting(m.hostA).host));
  return hosts.size === 1 && !hosts.has("split") ? [...hosts][0] : null;
}

/** Sides top to bottom (home team last) and the word between them. */
function sideOrder(host) {
  return {
    order: host === "a" ? ["b", "a"] : ["a", "b"],
    joiner: host === "a" || host === "b" ? "at" : "vs",
  };
}

const STATE_LABEL = { played: "Final", determined: "Matchup set", partial: "One spot set", projected: "" };

/** A compact game card in the tree: one row per side. Tapping it opens the game sheet. */
function treeCard(game, path) {
  const { results, focus, mode } = bracketData;
  const result = results[game.id] ?? null;
  const state = gameState(game, result);
  const { order, joiner } = sideOrder(settledHost(game));
  const onPath = path ? path.has(game.id) : null;
  const cls = ["tgame", `tgame--${state}`, onPath === true ? "is-path" : "", onPath === false ? "is-off" : ""].filter(Boolean).join(" ");
  const here = focus && !result ? teamInGame(game, focus, mode) : null;
  const rows = here && here.p > 0 && !here.locked
    ? focusRows(game, here)
    : `${treeRow(game, order[0], result, "")}${treeRow(game, order[1], result, joiner)}`;
  return `<button type="button" class="${cls}" data-game-open="${esc(game.id)}" aria-haspopup="dialog">${rows}</button>`;
}

/**
 * A game the picked team might reach, from its point of view: the team with
 * its chance of playing here (from either side), and its likeliest opponent
 * with the chance of that exact game. The home team still goes last.
 */
function focusRows(game, here) {
  const { focus, teams } = bracketData;
  const opp = opponentsFor(game, focus, bracketData.mode);
  const top = opp[0];
  // First round: each side is one region/seed, so say which finish puts the
  // team (and its opponent) here.
  const firstRound = game.side_a.feeders.length === 1 && game.side_b.feeders.length === 1;
  const mySide = here.sides[0] === "a" ? game.side_a : game.side_b;
  const theirSide = here.sides[0] === "a" ? game.side_b : game.side_a;
  const teamSub = firstRound ? esc(positionName(mySide.feeders[0])) : "Chance to play here";
  const oppSub = firstRound ? esc(positionName(theirSide.feeders[0])) : "Likeliest opponent";
  const teamRow = (gutter) => treeLine(gutter, focus, focus, teams, teamSub, oddsCell(here.p), " is-focus");
  // Every pairing here is under the API's 0.5% listing floor: too many long shots to name one.
  if (!top) return `${teamRow("")}${treeLine("vs", null, "Many opponents", teams, "Each under 0.5%", "", " trow--empty")}`;
  const oppRow = (gutter) => treeLine(gutter, top.opponent, top.opponent, teams, oppSub, oddsCell(top.pMatchup), "");
  if (top.hosts === "team") return `${oppRow("")}${teamRow("at")}`;
  if (top.hosts === "opponent") return `${teamRow("")}${oppRow("at")}`;
  return `${teamRow("")}${oppRow("vs")}`;
}

/** One row of a compact card. */
function treeLine(gutter, team, name, teams, sub, value, cls) {
  return `<span class="trow${cls}">
      <span class="trow__gutter">${gutter}</span>${team ? teamMark(team, teams[team], { size: 22 }) : '<span class="mark"></span>'}
      <span class="trow__text"><span class="trow__name">${esc(name)}</span>${sub ? `<span class="trow__sub">${sub}</span>` : ""}</span>
      <span class="trow__value">${value}</span>
    </span>`;
}

/** One side of a compact card: the result, the locked team, or the likeliest (or picked) team with its odds. */
function treeRow(game, sideKey, result, gutter) {
  const { mode, focus, teams } = bracketData;
  const side = sideKey === "a" ? game.side_a : game.side_b;
  const row = (cls, team, name, sub, value) => treeLine(gutter, team, name, teams, sub, value, `${cls}${team && team === focus ? " is-focus" : ""}`);
  if (result) {
    const team = lockedTeam(side) ?? (sideKey === "a" ? result.winner : result.loser);
    const won = team === result.winner;
    const score = won ? result.winnerScore : result.loserScore;
    return row(` trow--result${won ? " is-winner" : ""}`, team, team, "", score != null ? esc(score) : "");
  }
  const locked = lockedTeam(side);
  if (locked) {
    return row(" trow--locked", locked, locked, `${LOCK}<span class="visually-hidden">Locked in: </span>${esc(seedLabel(locked) ?? "Clinched")}`, "");
  }
  const list = occupants(side, mode);
  const firstRound = side.feeders.length === 1;
  if (!list.length) return row(" trow--empty", null, "No team can get here", "", "");
  const shown = (focus && list.find((o) => o.team === focus)) || list[0];
  // First round: the region/seed this slot is for. Later: how many others could be here instead.
  const sub = firstRound ? esc(positionName(side.feeders[0])) : list.length > 1 ? `+${list.length - 1} more` : "";
  return row("", shown.team, shown.team, sub, oddsCell(shown.p));
}

// ---------------------------------------------------- tree layout + lines

let tree = null; // the rendered tree: elements and measurements
let treeFrame = 0;

/** Hook up the tree after it's in the page (and the open game sheet, if any). */
function wireBracket() {
  const host = document.getElementById("bracket-host");
  if (!host) {
    tree = null;
    return;
  }
  const strip = host.querySelector(".tree");
  tree = {
    strip,
    colsEl: host.querySelector(".tree__cols"),
    cols: [...host.querySelectorAll(".tcol")],
    bodies: [...host.querySelectorAll(".tcol__body")],
    slots: [...host.querySelectorAll(".tcol")].map((c) => [...c.querySelectorAll(".tslot")]),
    svg: host.querySelector(".tree__lines"),
    tabs: [...host.querySelectorAll("[data-round-jump]")],
  };
  measureTree();
  layoutTree();
  strip.addEventListener("scroll", scheduleTree, { passive: true });
  refreshSheet();
}

function scheduleTree() {
  if (!treeFrame) treeFrame = requestAnimationFrame(() => { treeFrame = 0; layoutTree(); });
}

window.addEventListener("resize", () => {
  if (!tree?.strip.isConnected) return;
  measureTree();
  layoutTree();
});

/** Column positions, and on phones room after the final so it can scroll to the front. */
function measureTree() {
  const { strip, colsEl, cols } = tree;
  colsEl.style.paddingRight = "";
  tree.x = cols.map((c) => ({ left: c.offsetLeft, right: c.offsetLeft + c.offsetWidth }));
  tree.step = cols.length > 1 ? cols[1].offsetLeft - cols[0].offsetLeft : 1;
  tree.narrow = narrow();
  if (tree.narrow && cols.length) {
    const room = strip.clientWidth - cols[cols.length - 1].offsetWidth - 32;
    colsEl.style.paddingRight = `${Math.max(0, room)}px`;
  }
}

/** Place every card for the current scroll position, and redraw the lines. */
function layoutTree() {
  if (!tree?.strip.isConnected) return;
  const { strip, bodies, slots, svg, tabs, x } = tree;
  const cols = bracketData.cols;
  const focus = tree.narrow ? strip.scrollLeft / tree.step : 0;
  const { centers, height } = treeLayout(cols, focus, PITCH, CARD_H);
  slots.forEach((col, r) => col.forEach((el, i) => { el.style.transform = `translateY(${centers[r][i] - CARD_H / 2}px)`; }));
  for (const b of bodies) b.style.height = `${height}px`;

  const path = bracketData.path;
  const plain = [];
  const lit = [];
  const firstShown = Math.floor(focus); // rounds left of this have scrolled away, and so have their lines
  cols.forEach((col, r) => {
    if (r - 1 < firstShown) return;
    col.games.forEach(({ game, feeders }, i) => {
      for (const j of feeders) {
        const x1 = x[r - 1].right;
        const x2 = x[r].left;
        const xm = (x1 + x2) / 2;
        const y1 = centers[r - 1][j];
        const y2 = centers[r][i];
        const d = `M${x1} ${y1.toFixed(1)}H${xm}V${y2.toFixed(1)}H${x2}`;
        const onPath = path && path.has(game.id) && path.has(cols[r - 1].games[j].game.id);
        (onPath ? lit : plain).push(d);
      }
    });
  });
  svg.style.top = `${bodies[0]?.offsetTop ?? 0}px`;
  svg.setAttribute("width", tree.colsEl.scrollWidth);
  svg.setAttribute("height", Math.max(height, 1));
  svg.innerHTML = `<path d="${plain.join("")}"/>${lit.length ? `<path class="is-path" d="${lit.join("")}"/>` : ""}`;

  const current = Math.round(focus);
  tabs.forEach((t, i) => t.setAttribute("aria-current", String(i === current)));
}

/** Re-render the bracket in place (half control). */
function rerenderBracket() {
  const host = document.getElementById("bracket-host");
  if (!host || !bracketData) return;
  host.innerHTML = bracketHtml();
  wireBracket();
}

// ------------------------------------------------------------ game sheet
// Tapping a game opens a sheet (a bottom sheet on phones, a dialog on wide
// screens) with every team that could fill each side and the likeliest
// matchups, or a picked team's possible opponents there.

let sheet = null;

function gameSheet() {
  if (sheet) return sheet;
  sheet = document.createElement("dialog");
  sheet.className = "game-sheet";
  sheet.setAttribute("aria-labelledby", "game-sheet-title");
  document.body.append(sheet);
  sheet.addEventListener("click", onSheetClick);
  sheet.addEventListener("close", () => {
    const id = bracketUi.open;
    bracketUi.open = null;
    if (id) document.querySelector(`[data-game-open="${CSS.escape(id)}"]`)?.focus({ preventScroll: true });
  });
  return sheet;
}

function openSheet(id) {
  bracketUi.open = id;
  const s = gameSheet();
  s.innerHTML = sheetHtml(id);
  if (!s.open) s.showModal();
  s.querySelector(".game-sheet__body").scrollTop = 0;
}

/** After a re-render (a team picked in the sheet, odds changed), show the open game's new numbers. */
function refreshSheet() {
  if (!sheet?.open || !bracketUi.open) return;
  const body = sheet.querySelector(".game-sheet__body");
  const top = body?.scrollTop ?? 0;
  sheet.innerHTML = sheetHtml(bracketUi.open);
  sheet.querySelector(".game-sheet__body").scrollTop = top;
  // The control that was focused was just replaced; keep focus in the sheet.
  if (!sheet.contains(document.activeElement)) sheet.querySelector(".game-sheet__title")?.focus({ preventScroll: true });
}

function sheetHtml(id) {
  const game = bracketData.games.find((g) => g.id === id);
  if (!game) return "";
  const result = bracketData.results[game.id] ?? null;
  const state = gameState(game, result);
  const host = settledHost(game);
  const { order, joiner } = sideOrder(host);
  const sideOf = (k) => (k === "a" ? game.side_a : game.side_b);
  const known = order.map((k) => lockedTeam(sideOf(k)) ?? (result ? (k === "a" ? result.winner : result.loser) : null));
  const title = known[0] && known[1] ? `${known[0]} ${joiner} ${known[1]}` : "Who might play here";
  const kicker = [game.round, game.id !== "final" ? HALF_NAMES[game.half] : null, STATE_LABEL[state] || null].filter(Boolean).join(" · ");
  return `<div class="game-sheet__head">
      <div>
        <p class="game-sheet__kicker">${esc(kicker)}</p>
        <h2 class="game-sheet__title" id="game-sheet-title" tabindex="-1" autofocus>${esc(title)}</h2>
        <p class="game-sheet__prov provenance">${contextHtml(`Class ${bracketData.clazz}A`, bracketData.summary, bracketData.mode)}</p>
      </div>
      <button type="button" class="game-sheet__close" data-sheet-close>${CLOSE}<span class="visually-hidden">Close</span></button>
    </div>
    <div class="game-sheet__body">
      <div class="bgame bgame--sheet">
        ${bracketSide(game, order[0], result, host)}
        <div class="bgame__vs" aria-hidden="true"><span>${joiner}</span></div>
        ${bracketSide(game, order[1], result, host)}
        ${host === "neutral" ? '<p class="bgame__site muted">Neutral site</p>' : ""}
      </div>
      ${result ? "" : `<div class="bgame__detail">${gameDetail(game)}</div>`}
      <p class="game-sheet__hint muted">Pick a team to follow its path through the bracket.</p>
      <p class="report-line"><button type="button" class="link-button" data-feedback="odds" data-about="${esc(game.round)}">Something look wrong in this game? Tell us</button></p>
    </div>`;
}

function onSheetClick(e) {
  if (e.target === sheet || e.target.closest("[data-sheet-close]")) {
    sheet.close();
    return;
  }
  const more = e.target.closest("[data-show-all]");
  if (more) {
    const k = more.dataset.showAll;
    if (bracketUi.showAll.has(k)) bracketUi.showAll.delete(k);
    else bracketUi.showAll.add(k);
    refreshSheet();
    sheet.querySelector(`[data-show-all="${CSS.escape(k)}"]`)?.focus({ preventScroll: true });
    return;
  }
  const pick = e.target.closest("[data-pick-team]");
  if (pick) {
    const team = pick.dataset.pickTeam;
    navigate(hrefWith({ team: bracketData?.focus === team ? null : team }), { replace: true });
  }
}

/** A team name that picks the team when tapped (shared with the standings via ?team=). */
function pickTeam(team) {
  const { teams, focus } = bracketData;
  const mine = team === focus;
  return `<button type="button" class="bteam__name${mine ? " is-focus" : ""}" data-pick-team="${esc(team)}" aria-pressed="${mine}">${teamMark(team, teams[team])}<span class="team-name">${esc(team)}</span></button>`;
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

/** Host wording from one team's point of view. */
function hostText(team, hosts, pTeamHosts) {
  if (hosts === "neutral") return "Neutral site";
  if (hosts === "split") return `${formatPct(pTeamHosts)} chance ${team} hosts`;
  return "";
}

/** "vs" when the picked team would host, "at" when the opponent would. */
const oppJoiner = (hosts) => (hosts === "opponent" ? "at" : "vs");

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
      <ol class="opp-list">${shown.map((o) => {
        const note = hostText(focus, o.hosts, o.pTeamHosts);
        return `<li><span class="mu__teams"><span class="mu__line"><span class="vs">${oppJoiner(o.hosts)}</span>${teamLabel(o.opponent, teams)}</span></span>${oddsCell(o.p)}${note ? `<span class="opp-list__host">${esc(note)}</span>` : ""}</li>`;
      }).join("")}</ol>
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
    // Home team last ("Clinton at Booneville"); "vs" when the host isn't settled or the site is neutral.
    const h = hosting(m.hostA);
    const [away, home] = h.host === "a" ? [m.b, m.a] : [m.a, m.b];
    const joiner = h.host === "a" || h.host === "b" ? "at" : "vs";
    const note = h.host === "neutral" ? "Neutral site" : h.host === "split" ? `${formatPct(h.p)} chance ${m.a} hosts` : "";
    return `<li><span class="mu__teams"><span class="mu__line"><span class="vs"></span>${teamLabel(away, teams)}</span><span class="mu__line"><span class="vs">${joiner}</span>${teamLabel(home, teams)}</span></span>${oddsCell(m.p)}${note ? `<span class="opp-list__host">${esc(note)}</span>` : ""}</li>`;
  });
  if (!ms.length) {
    return `<div class="bgame__sides">${sides}</div>
      <p class="muted bgame__count">So many teams could still meet here that no single matchup has even a 0.5% chance yet.</p>`;
  }
  return `<div class="bgame__sides">${sides}</div>
    <h4 class="bgame__heading">Most likely matchups</h4>
    <ol class="opp-list opp-list--matchups">${rows.join("")}</ol>
    ${ms.length > MATCHUP_CAP ? `<button type="button" class="bside__more" data-show-all="${esc(key)}" aria-expanded="${showAll}">${showAll ? "Show fewer" : `Show all ${ms.length}`}</button>` : ""}
    ${other >= 0.0005 ? `<p class="muted bgame__count">Other pairings, each under 0.5%: ${esc(formatPct(other))} combined</p>` : ""}`;
}

app.addEventListener("click", (e) => {
  const card = e.target.closest("[data-game-open]");
  if (card) {
    openSheet(card.dataset.gameOpen);
    return;
  }
  const half = e.target.closest(".half-control [data-half]");
  if (half) {
    bracketUi.half = half.dataset.half;
    rerenderBracket();
    return;
  }
  const jump = e.target.closest("[data-round-jump]");
  if (jump && tree) {
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    tree.strip.scrollTo({ left: Number(jump.dataset.roundJump) * tree.step, behavior: smooth ? "smooth" : "auto" });
  }
});

// ------------------------------------------------------------- feedback
// One form for every kind of report, in a sheet over the page it's about
// (or on its own at /feedback). A score correction for a specific game goes
// to /submissions/scores with the corrected score; everything else to
// /submissions/feedback with a category and what it's about. Both land in
// the moderation queue. Flood guards: the API's per-visitor and daily
// limits, duplicate suppression and circuit breaker, nginx's request rate
// limit, a honeypot field people never see, and a minimum time to fill in.

let feedbackSheet = null;

/** "Region 6-3A · Raleigh": what a report from this page is about. */
function feedbackContext({ team = null, about = null } = {}) {
  const parts = [];
  if (route.page === "region") parts.push(`Region ${route.region}-${route.clazz}A`);
  else if (route.page === "class") parts.push(`Class ${route.clazz}A`);
  else if (route.page === "bracket") parts.push(`${route.clazz}A bracket`);
  if (about) parts.push(about);
  if (team) parts.push(team);
  return parts.join(" · ") || null;
}

/**
 * The form. `game` (a completed region game) makes it a score correction;
 * otherwise it's a general report starting on `category`, about `context`.
 */
function feedbackForm({ game = null, category = "other", context = null, page = "/" } = {}) {
  const honeypot = `<div class="fb-hp" aria-hidden="true"><label>Leave this empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>`;
  const status = '<p class="fb-status" role="status" aria-live="polite"></p>';
  const opened = Date.now();
  if (game) {
    const scoreInput = (name, team, value) => `<label class="fb-score">
        <span class="fb-score__team">${esc(team)}</span>
        <input type="text" name="${name}" inputmode="numeric" pattern="[0-9]*" maxlength="3" value="${esc(value)}" autocomplete="off" required>
      </label>`;
    return `<form class="fb-form" novalidate data-fb-form data-mode="score" data-opened="${opened}" data-page="${esc(page)}" data-game="${esc(JSON.stringify(game))}">
      <p class="fb-about">${esc(game.away)} ${esc(game.awayScore)}, ${esc(game.home)} ${esc(game.homeScore)} · ${esc(gameDate(game.date))}</p>
      <fieldset class="fb-scores">
        <legend>The correct final score</legend>
        ${scoreInput("away", game.away, game.awayScore)}
        ${scoreInput("home", game.home, game.homeScore)}
      </fieldset>
      <label class="fb-field"><span>Where did you see it? <span class="muted">(optional)</span></span>
        <textarea name="note" rows="2" maxlength="${NOTE_MAX}" placeholder="A link to a box score, the school’s post…"></textarea>
      </label>
      ${honeypot}
      <div class="fb-turnstile"></div>
      ${status}
      <div class="fb-actions"><button type="submit" class="fb-submit">Send correction</button></div>
      <p class="fb-fine muted">A moderator checks every correction before it changes the standings.</p>
    </form>`;
  }
  const cats = CATEGORIES.map((c) => `<label class="fb-cat"><input type="radio" name="category" value="${c.value}"${c.value === category ? " checked" : ""}><span>${esc(c.label)}</span></label>`).join("");
  return `<form class="fb-form" novalidate data-fb-form data-mode="feedback" data-opened="${opened}" data-page="${esc(page)}"${context ? ` data-context="${esc(context)}"` : ""}>
    ${context ? `<p class="fb-about">About: ${esc(context)}</p>` : ""}
    <fieldset class="fb-cats"><legend>What’s it about?</legend>${cats}</fieldset>
    <label class="fb-field"><span>What’s wrong, or what would you like to tell us?</span>
      <textarea name="message" rows="5" maxlength="${MESSAGE_MAX}" required placeholder="${esc(MESSAGE_HINTS[category] ?? MESSAGE_HINTS.other)}"></textarea>
    </label>
    <label class="fb-field"><span>Email <span class="muted">(optional, only if you’d like a reply)</span></span>
      <input type="email" name="email" maxlength="254" autocomplete="email" inputmode="email">
    </label>
    ${honeypot}
    <div class="fb-turnstile"></div>
    ${status}
    <div class="fb-actions"><button type="submit" class="fb-submit">Send</button></div>
  </form>`;
}

function feedbackPage() {
  return `<div class="page">
    <header class="entry-head">
      <h1 class="title">Send feedback</h1>
      <p class="prose">Spotted a wrong score, odds or a scenario that can’t be right, or have an idea? Tell us here.
        To correct a specific game’s score, open its region and use “Wrong score?” on the game.</p>
    </header>
    <div class="fb-page">${feedbackForm({ page: "/feedback" })}</div>
  </div>`;
}

function openFeedback({ game = null, category = "other", team = null, about = null } = {}) {
  if (sheet?.open) sheet.close(); // from the bracket's game sheet: one sheet at a time
  if (!feedbackSheet) {
    feedbackSheet = document.createElement("dialog");
    feedbackSheet.className = "game-sheet feedback-sheet";
    feedbackSheet.setAttribute("aria-labelledby", "feedback-title");
    document.body.append(feedbackSheet);
    feedbackSheet.addEventListener("click", (e) => {
      if (e.target === feedbackSheet || e.target.closest("[data-sheet-close]")) feedbackSheet.close();
    });
  }
  const context = game ? null : feedbackContext({ team, about });
  const page = location.pathname + location.search;
  removeTurnstile(feedbackSheet.querySelector("[data-fb-form]"));
  feedbackSheet.innerHTML = `<div class="game-sheet__head">
      <div>
        <p class="game-sheet__kicker">Feedback</p>
        <h2 class="game-sheet__title" id="feedback-title" tabindex="-1" autofocus>${game ? "Report a wrong score" : "Tell us what’s wrong"}</h2>
      </div>
      <button type="button" class="game-sheet__close" data-sheet-close>${CLOSE}<span class="visually-hidden">Close</span></button>
    </div>
    <div class="game-sheet__body">${feedbackForm({ game, category, context, page })}</div>`;
  feedbackSheet.showModal();
  mountTurnstile(feedbackSheet.querySelector("[data-fb-form]"), API);
}

/** Check, send, and report back. Nothing is sent until the form is valid. */
async function sendFeedback(form) {
  const status = form.querySelector(".fb-status");
  const button = form.querySelector(".fb-submit");
  const data = new FormData(form);
  const page = form.dataset.page || "/";
  const website = String(data.get("website") || "");
  let path;
  let body;
  let problem;
  if (form.dataset.mode === "score") {
    const game = JSON.parse(form.dataset.game);
    const values = { awayScore: data.get("away"), homeScore: data.get("home"), note: String(data.get("note") || "") };
    problem = scoreProblem(game, values);
    body = scoreBody(game, { ...values, page, website });
    path = "/submissions/scores";
  } else {
    const values = {
      category: String(data.get("category") || "other"),
      context: form.dataset.context || null,
      message: String(data.get("message") || ""),
      email: String(data.get("email") || ""),
    };
    problem = feedbackProblem(values);
    body = feedbackBody({ ...values, page, website });
    path = "/submissions/feedback";
  }
  status.classList.toggle("is-error", Boolean(problem));
  status.textContent = problem ?? "";
  if (problem) return;
  // Filled in faster than a person could: treat it as sent without sending.
  if (Date.now() - Number(form.dataset.opened) < MIN_FILL_MS) {
    feedbackSent(form);
    return;
  }
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Sending…";
  const check = await turnstileToken(form);
  if (check.problem) {
    status.classList.add("is-error");
    status.textContent = check.problem;
    button.disabled = false;
    button.textContent = label;
    return;
  }
  if (check.token) body.turnstile_token = check.token;
  try {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      feedbackSent(form);
      return;
    }
    const detail = (await res.json().catch(() => null))?.detail;
    status.classList.add("is-error");
    status.textContent = submissionError(res.status, detail);
  } catch {
    status.classList.add("is-error");
    status.textContent = submissionError(0);
  }
  resetTurnstile(form); // the token was used up
  button.disabled = false;
  button.textContent = label;
}

function feedbackSent(form) {
  const score = form.dataset.mode === "score";
  const inSheet = Boolean(form.closest("dialog"));
  const done = document.createElement("div");
  done.className = "fb-sent";
  done.setAttribute("role", "status");
  done.innerHTML = `<p class="fb-sent__title">Thanks, we’ve got it.</p>
    <p class="muted">${score
      ? "A moderator will check the score. Once it’s approved, the standings and odds pick it up at the next morning’s update."
      : "A moderator will read it. If you left an email, we may follow up."}</p>
    ${inSheet ? '<button type="button" class="fb-submit" data-sheet-close>Done</button>' : '<a href="/feedback" class="fb-again">Send something else</a>'}`;
  removeTurnstile(form);
  form.replaceWith(done);
  done.querySelector("button, a")?.focus({ preventScroll: true });
}

// The message's hint follows the category: a score report needs the game and the score.
const MESSAGE_HINTS = {
  score: "Which game, and what was the final score?",
  odds: "Which team, and what looks wrong?",
  other: "The more specific, the faster we can fix it.",
};

document.addEventListener("change", (e) => {
  if (e.target.name !== "category" || !e.target.closest("[data-fb-form]")) return;
  const message = e.target.form.querySelector('textarea[name="message"]');
  if (message) message.placeholder = MESSAGE_HINTS[e.target.value] ?? MESSAGE_HINTS.other;
});

document.addEventListener("submit", (e) => {
  const form = e.target.closest("[data-fb-form]");
  if (!form) return;
  e.preventDefault();
  sendFeedback(form);
});

document.addEventListener("click", (e) => {
  const report = e.target.closest("[data-score-report]");
  if (report) {
    const d = report.dataset;
    openFeedback({
      game: { date: d.date, away: d.away, home: d.home, awayScore: Number(d.awayScore), homeScore: Number(d.homeScore) },
    });
    return;
  }
  const trigger = e.target.closest("[data-feedback]");
  if (!trigger || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  openFeedback({ category: trigger.dataset.feedback, team: trigger.dataset.team || null, about: trigger.dataset.about || null });
});

// --------------------------------------------------------------- boot

if (app) {
  window.addEventListener("popstate", render);
  render();
}
