// 2026 interim UI: pick a class, pick a region, read that region's race.
// The path says what you're looking at and the query how (see routes.js):
//   /standings/7a           every region in 7A
//   /standings/7a/2         Region 2-7A
//   /brackets/7a            the 7A playoff bracket
//   ?season=2025&week=9&odds=tossup&team=oxford
// Defaults stay out of the URL, so a link to "now" is just the path.
// Moving between pages pushes history; changing the season, week, odds
// mode, or picked team replaces it, so Back goes to the previous page.

import { escapeHtml as esc, formatPct, isCertain, recordText, shortDate, gameDate, calculatedSpan } from "./format.js";
import {
  oddsCell, provenance, statusBadges, teamMark, teamLabel, scenarioCard, classScrubber, chevronIcon,
  ODDS_MODES, modeLabel, tableMode, infoButton, gameCard, outcomeScenarioCard, whyTies, breadcrumbs,
} from "./components.js";
import { matchTeams } from "./search.js";
import { FRONT_PAGE_URL, LANDING_FALLBACK, isFrontPage } from "./landing.js";
import { mountTurnstile, removeTurnstile, resetTurnstile, turnstileToken } from "./turnstile.js";
import { CLASSES, FORMER_SLUGS, slugify, parseLocation, buildPath } from "./routes.js";
import { startAnalytics, track, keepCampaignTags, campaignTags } from "./analytics.js";
import {
  CATEGORIES, MESSAGE_MAX, NOTE_MAX, MIN_FILL_MS, feedbackProblem, feedbackBody, scoreProblem, scoreBody, submissionError,
} from "./feedback.js";
import {
  sideLabel, layoutResults, occupants, lockedTeam, gameState, hosting, matchups as gameMatchups,
  teamInGame, opponentsFor, pathGames, bracketStructure, positionName, treeColumns, treeLayout, roundPicks,
} from "./bracket.js";
import {
  outcomeCards, insightCards, oddsFor, hasProjectedOdds, completeScenarioCards,
} from "./scenarios.js";
import {
  standingPositions, positionLabels, playoffPath, regionGames, displayOrder, regionComplete, snapshotDate,
  orient, byDay, teamSchedule, tieHeading,
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
  const key = focusKey(document.activeElement);
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  const token = renderToken + 1;
  await render();
  if (token !== renderToken) return;
  // Go to the top once the new page is in (not while the old one is still showing).
  if (scroll) window.scrollTo(0, 0);
  settleFocus(replace ? key : null);
}

// ------------------------------------------------------------- focus
// Rendering replaces the page's markup, and with it whatever had focus,
// which would drop a keyboard or screen reader user back at the top of the
// document. So after a change to how this page is shown, focus returns to
// the same control (its replacement) and the change is announced; after
// moving to another page, focus goes to the new page's heading.

/** A selector that finds an element's replacement after a re-render, or null. */
function focusKey(el) {
  if (!el || el === document.body || !el.isConnected) return null;
  const attr = (name) => `[${name}="${CSS.escape(el.getAttribute(name))}"]`;
  if (el.matches("[data-control]")) return attr("data-control");
  if (el.matches(".row-toggle[data-team]")) return `.row-toggle${attr("data-team")}`;
  if (el.matches("[data-class]")) return `.scrubber ${attr("data-class")}`;
  if (el.matches("[data-nav]")) return `${el.closest(".tab-bar") ? ".tab-bar" : ".site-nav"} ${attr("data-nav")}`;
  return el.id ? `#${CSS.escape(el.id)}` : null;
}

/**
 * Put focus where it belongs once a render is in: the replacement of the
 * control `key` names (a view change), else the page's heading (a new page).
 * Focus a render already placed (the team row the search jumped to), and
 * focus inside an open sheet, stay where they are.
 */
function settleFocus(key) {
  const active = document.activeElement;
  if (document.querySelector("dialog[open]")) return;
  if (active && active !== document.body && active !== app && app.contains(active)) return;
  const same = key && document.querySelector(key);
  if (same) {
    same.focus({ preventScroll: true });
    if (key.startsWith("[data-control")) announce(contextText());
    return;
  }
  const heading = app.querySelector("h1");
  if (heading) {
    heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  } else {
    app.focus({ preventScroll: true });
  }
  if (key) announce(contextText());
}

/** What's on screen in a sentence for screen readers: the context bar's words. */
function contextText() {
  return contextBar.querySelector(".context-bar__inner").textContent.replace(/\s*·\s*/g, ", ").replace(/\s+/g, " ").trim();
}

/** Say something through the page's status region (index.html's #app-status). */
function announce(text) {
  const region = document.getElementById("app-status");
  if (!region || !text) return;
  region.textContent = "";
  // A fresh node a moment later, so the same words twice are still read.
  setTimeout(() => { region.textContent = text; }, 50);
}

/** The school a `team` value names: its slug, or the name itself (old links). */
function resolveTeam(value, index) {
  if (!value) return null;
  const schools = Object.keys(index);
  const found = schools.find((s) => slugify(s) === value) ?? (value in index ? value : null);
  // A link from before a school's new name: the same school, under the name it goes by this season.
  return found ?? (FORMER_SLUGS[value] in index ? FORMER_SLUGS[value] : null);
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
  // An arrival link's campaign tags stay until analytics has counted them (analytics.js).
  const tags = keepCampaignTags() ? campaignTags(location.search) : [];
  const withTags = tags.length
    ? `${canonical}${canonical.includes("?") ? "&" : "?"}${new URLSearchParams(tags)}`
    : canonical;
  if (withTags !== location.pathname + location.search) history.replaceState(null, "", withTags);
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

/**
 * Tell search engines not to index what's on screen (a page that doesn't
 * exist, or has nothing published): nginx can only 404 addresses that are
 * malformed, so one for a region a class doesn't have is caught here.
 */
function setNoindex(on) {
  let tag = document.head.querySelector('meta[name="robots"][data-app]');
  if (!on) {
    tag?.remove();
    return;
  }
  if (!tag) {
    tag = document.createElement("meta");
    tag.name = "robots";
    tag.dataset.app = "";
    document.head.append(tag);
  }
  tag.content = "noindex";
}

let renderToken = 0;
// Set when the team search jumps to a team, so the page scrolls to its row;
// picking a row in place leaves the scroll position alone.
let scrollToFocus = false;
async function render() {
  const token = ++renderToken;
  nextComputedAt = null;
  showComputedAt(null);
  route = readRoute();
  setNoindex(route.page === "notfound");
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
  // The front page has no class (and no class picker); every other page marks its class.
  renderScrubber(route.page === "landing" ? null : route.clazz);
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
    renderScrubber(route.page === "landing" ? null : route.clazz); // again, now that the picked team is known (the view links carry it)
    loadTeamSearch(season);
    const html = route.page === "landing" ? await landingView()
      : route.page === "bracket" ? await bracketView(ctx)
      : route.region ? await regionView(ctx) : await classView(ctx);
    if (token !== renderToken) return;
    // Re-rendering the same bracket (a team picked, odds changed) keeps each round strip where it was.
    const strip = route.page === "bracket" ? app.querySelector(".tree")?.scrollLeft ?? 0 : 0;
    if (html !== null) app.innerHTML = html;
    document.body.classList.toggle("is-wide", route.page === "bracket");
    if (route.page === "bracket") {
      const tree = app.querySelector(".tree");
      if (tree) tree.scrollLeft = strip;
      wireBracket();
    } else {
      sheet?.close();
    }
    showContext(nextContext);
    markLineStarts();
    // The front page carries its own calculation times, whether just fetched or already on screen.
    if (route.page === "landing") {
      const d = app.querySelector(":scope > .landing")?.dataset ?? {};
      nextComputedAt = d.computedFrom ? { from: d.computedFrom, to: d.computedTo } : null;
    }
    showComputedAt(nextComputedAt);
    canonicalize(route.season);
    if (scrollToFocus && route.teamName && route.region) focusTeamRow();
    scrollToFocus = false;
  } catch (err) {
    if (token !== renderToken) return;
    showContext(null);
    setNoindex(true);
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
let nextComputedAt = null; // when the shown numbers were calculated: { from, to }, set by the view
let headObserver = null;

function contextHtml(title, summary, mode) {
  const sep = '<span class="sep" aria-hidden="true">·</span>';
  const parts = [`<span class="context-bar__title">${esc(title)}</span>`];
  if (summary?.week) parts.push(`<span>${esc(summary.week)}</span>`);
  if (summary?.date) parts.push(`<span>${esc(summary.date)}</span>`);
  if (mode) parts.push(modeLabel(mode));
  return parts.join(sep);
}

// The footer says when the numbers on screen were calculated: the real time
// the pipeline wrote them, not the time it's scheduled to start. A class's
// regions are written minutes apart, so pages showing several give a span.
function showComputedAt(span) {
  const slot = document.querySelector("[data-computed-at]");
  if (!slot) return;
  const when = calculatedSpan(span?.from, span?.to);
  slot.textContent = when ? ` These numbers were calculated ${when}.` : "";
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
  if (page === "landing") return "Mississippi High School Football Playoff Races"; // as index.html's own <title>
  if (page === "bracket") return `Class ${clazz}A playoff bracket — ${SITE}`;
  return region ? `Region ${region}-${clazz}A playoff race — ${SITE}` : `Class ${clazz}A playoff races — ${SITE}`;
}

function notice(text) {
  return `<div class="page"><p class="notice">${esc(text)}</p></div>`;
}

// ------------------------------------------------------------ scrubber

function renderScrubber(clazz) {
  // The front page has no class of its own, and its own grid of links instead.
  scrubberHost.parentElement.hidden = route.page === "landing";
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
  const onStandings = ["class", "region"].includes(route.page); // not the front page: it's neither
  const known = route.page !== "notfound";
  const targets = {
    standings: known ? hrefWith({ page: route.region ? "region" : "class" }) : "/standings/1a",
    bracket: known ? hrefWith({ page: "bracket", region: null }) : "/brackets/1a",
  };
  for (const a of document.querySelectorAll("[data-nav]")) {
    const key = a.dataset.nav;
    if (key in targets) a.setAttribute("href", targets[key]);
    const current = known && (key === "bracket" ? onBracket : key === "standings" ? onStandings : key === "home" && route.page === "landing");
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
  track("team_search_used", { team: team.school });
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
  // never ends on a dangling dot; one that starts a line is hidden
  // (markLineStarts), so none starts on one either.
  const segs = parts.map((part, i) => (i === 0 ? part : `<span class="seg">${sep}${part}</span>`));
  return `<p class="provenance provenance--controls">${segs.join("")}</p>${help}`;
}

/** Hide the separator of each controls-line segment that wrapped onto a new line. */
function markLineStarts() {
  for (const line of document.querySelectorAll(".provenance--controls")) {
    let prev = null;
    for (const seg of line.children) {
      if (seg.classList.contains("seg")) {
        seg.classList.remove("is-line-start");
        if (prev && seg.offsetTop > prev.offsetTop + prev.offsetHeight / 2) seg.classList.add("is-line-start");
      }
      prev = seg;
    }
  }
}
let lineFrame = 0;
window.addEventListener("resize", () => {
  if (!lineFrame) lineFrame = requestAnimationFrame(() => { lineFrame = 0; markLineStarts(); });
});

const MODE_HELP = `<div class="mode-help" id="mode-help" hidden>
  <p><strong>Projected</strong> weighs every way the season can finish by how likely it is, using each team’s Elo rating and home-field advantage to set its chance of winning each game.</p>
  <p><strong>Toss-up</strong> counts every way the season can finish equally, as if each remaining game were a coin flip.</p>
  <p><a href="/about">More on how the odds work</a></p>
</div>`;

app.addEventListener("change", (e) => {
  const control = e.target.closest("[data-control]");
  if (!control) return;
  const value = control.value;
  track(`${control.dataset.control}_changed`, { value });
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

// ------------------------------------------------------------ front page
// The pipeline draws it (landing.js says how it reaches the page); the app
// only shows it.

/**
 * The front page's HTML, or null when it's already on screen (a first visit:
 * nginx put the pipeline's copy there), so it's left exactly as it is.
 */
async function landingView() {
  nextContext = null;
  if (app.querySelector(":scope > .landing")) return null;
  try {
    const res = await fetch(FRONT_PAGE_URL, { headers: { Accept: "text/html" } });
    const html = res.ok ? await res.text() : null;
    if (isFrontPage(html)) return html;
  } catch {
    /* fall through to the fallback */
  }
  return LANDING_FALLBACK;
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
    ${breadcrumbs([["Home", "/"], [`Class ${clazz}A`, null]])}
    <h1 class="title">Class ${clazz}A</h1>
    ${controlsLine(ctx, shownWeeks, { asOf: data.as_of_date, mode, projectedAvailable })}
  </div>`;
  nextContext = contextHtml(`Class ${clazz}A`, controlsSummary, mode);
  nextComputedAt = data.computed_from ? { from: data.computed_from, to: data.computed_to } : null;
  if (!data.regions.length) return head + notice("No standings have been published for this class yet.");

  const blocks = data.regions.map((r) => {
    const ordered = displayOrder(r.teams);
    const positions = positionLabels(standingPositions(ordered));
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
        <caption><span class="visually-hidden">Region ${r.region}-${clazz}A standings and ${mode === "projected" ? "projected" : "toss-up"} odds</span>${tableMode(mode)}</caption>
        <thead><tr>
          <th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>
          <th scope="col" class="col-team">Team</th>
          <th scope="col" class="col-rec">Region</th>
          ${oddsHead(ODDS_BY_KEY.p1)}
          ${oddsHead(ODDS_BY_KEY.p_playoffs)}
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
  const at = data.computation_state?.computed_at ?? null;
  nextComputedAt = at ? { from: at, to: at } : null;

  // Cards carry the same provenance as plain text, so a cropped screenshot
  // of one still says what it shows. The odds mode only where the card has
  // odds: a "settles a spot" card has none, so it would say nothing there.
  const shownWeek = [...shownWeeks].reverse().find((w) => w.firstDate <= data.as_of_date);
  const provFor = (withMode) => provenance(
    { label: shownWeek?.label, date: shownWeek?.lastDate ?? data.as_of_date, mode: withMode ? mode : null },
    shortDate,
  );
  const cardProv = { odds: provFor(true), plain: provFor(false) };

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
      ${breadcrumbs([["Home", "/"], [`Class ${clazz}A`, hrefWith({ region: null, team: null })], [`Region ${region}-${clazz}A`, null]])}
      <h1 class="title">Region ${region}-${clazz}A</h1>
      ${data.headline ? `<p class="headline">${esc(data.headline)}</p>` : ""}
      ${controls}
    </header>
    ${standingsTable(data, teams, mode, focus, clazz, schedule)}
    ${data.tiebreaks?.length ? tiebreaksSection(data.tiebreaks) : ""}
    ${remaining.length ? gamesSection("remaining", "Remaining games", remaining, teams, focus) : ""}
    ${remaining.length ? scenariosSection(data, teams, cardProv, mode, focus, !data.scenarios?.length) : ""}
    ${data.scenarios?.length ? allScenariosSection(data.scenarios, teams, focus, mode, cardProv.odds, `Region ${region}-${clazz}A`) + scenarioReport(focus) : ""}
    ${results.length ? gamesSection("results", "Completed games", results, teams, focus) : ""}
  </div>`;
}

// label: the column header; seed: the same odds in the expanded row; full:
// what the number measures, for screen readers and as the header's tooltip.
const ODDS_COLUMNS = [
  { key: "p1", label: "1st", seed: "#1 Seed", full: "Chance of finishing 1st (the #1 seed)", mid: false },
  { key: "p2", label: "2nd", seed: "#2 Seed", full: "Chance of finishing 2nd (the #2 seed)", mid: true },
  { key: "p3", label: "3rd", seed: "#3 Seed", full: "Chance of finishing 3rd (the #3 seed)", mid: true },
  { key: "p4", label: "4th", seed: "#4 Seed", full: "Chance of finishing 4th (the #4 seed)", mid: true },
  { key: "p_playoffs", label: "Makes playoffs", seed: "Makes playoffs", full: "Chance of making the playoffs as any seed", mid: false },
];
const ODDS_BY_KEY = Object.fromEntries(ODDS_COLUMNS.map((c) => [c.key, c]));
// Under the region table on narrow screens, which leave out the mid columns (and the
// headers' tooltips never show on a phone): where the rest of the odds are.
const TABLE_HINT = "Select a team to see its odds of every seed.";

/** An odds column header: the short label on screen, what it measures for screen readers and on hover. */
function oddsHead(c, extra = "") {
  return `<th scope="col" class="col-odds${extra}" title="${c.full}"><span aria-hidden="true">${c.label}</span><span class="visually-hidden">${c.full}</span></th>`;
}

function standingsTable(data, teams, mode, focus, clazz, games) {
  const ordered = displayOrder(data.teams);
  const positions = positionLabels(standingPositions(ordered));
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

  const oddsHeads = ODDS_COLUMNS.map((c) => oddsHead(c, c.mid ? " col-mid" : ""));
  return `<table class="standings">
    <caption><span class="visually-hidden">Standings and ${mode === "projected" ? "projected" : "toss-up"} odds of finishing in each playoff position. Select a team to see its playoff path and scenarios.</span>${tableMode(mode)}</caption>
    <thead><tr>
      <th scope="col" class="col-pos"><span class="visually-hidden">Position</span></th>
      <th scope="col" class="col-team">Team</th>
      <th scope="col" class="col-rec">Region</th>
      <th scope="col" class="col-rec col-overall">Overall</th>
      ${oddsHeads.join("")}
    </tr></thead>
    <tbody>${rows.join("")}</tbody>
  </table>
  <p class="table-hint muted">${TABLE_HINT}</p>`;
}

/**
 * The team's Elo rating, the number Projected odds are built on (brief: make
 * the model legible). Ratings are numbers, not positions, so it's never called
 * a ranking. Nothing for a team without one.
 */
function eloLine(elo) {
  if (elo == null) return "";
  return `<p class="detail__elo"><span class="detail__elo-label">Elo rating</span> <strong>${Math.round(elo)}</strong></p>
    <p class="detail__note muted">The rating behind Projected odds, built from game results.
      <a href="/about#elo">How the ratings work</a></p>`;
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
    ? `<h3 class="detail__sub">${title}</h3><ul class="sched">${rows.join("")}</ul>`
    : "");
  const playedRows = completed.map((g) => `<li>${opponent(g)}`
    + `<span class="sched__result">${esc(`${g.scoreFor}–${g.scoreAgainst}`)} <span class="sched__wl sched__wl--${g.result}">${g.result}</span></span></li>`);
  const upcomingRows = upcoming.map((g) => `<li>${opponent(g)}${g.date ? `<span class="sched__date">${esc(gameDate(g.date))}</span>` : ""}</li>`);
  const coinFlip = complete && t.coin_flip_needed
    ? '<p class="detail__note">A coin flip is needed to settle a tie involving this team.</p>'
    : "";
  const record = `<section class="detail__panel" aria-label="Record">
      <h2 class="detail__title">Record</h2>
      <p class="detail__records">
        <span><strong>${esc(recordText(r.region_wins, r.region_losses, r.region_ties))}</strong> Region</span>
        <span><strong>${esc(recordText(r.wins, r.losses, r.ties))}</strong> Overall</span>
      </p>
      ${coinFlip}
      ${schedList("Completed region games", playedRows)}
      ${schedList("Remaining region games", upcomingRows)}
    </section>`;

  const seeding = `<section class="detail__panel" aria-label="Seeding odds">
      <h2 class="detail__title">Seeding odds</h2>
      <dl class="detail__odds">${ODDS_COLUMNS.map((c) => `<div><dt>${c.seed}</dt><dd>${oddsCell(o[c.key])}</dd></div>`).join("")}</dl>
      ${eloLine(t.elo)}
    </section>`;

  // Teams that made the playoffs keep their path after elimination: it
  // records how far they got.
  const path = t.eliminated && !t.clinched ? [] : playoffPath(t, mode, clazz);
  const pathPanel = path.length
    ? `<section class="detail__panel detail__panel--path" aria-label="Playoff path">
        <h2 class="detail__title">Playoff path</h2>
        <table class="path">
          <caption class="visually-hidden">${esc(t.school)}’s chance of reaching and hosting each playoff round</caption>
          <thead><tr><th scope="col">Round</th><th scope="col">Reaches round</th><th scope="col">Hosts, if it gets there</th><th scope="col">Hosts, overall</th></tr></thead>
          <tbody>${path.map((p) => `<tr>
            <th scope="row">${esc(p.round)}</th>
            <td>${oddsCell(p.reach)}</td>
            <td>${p.neutral ? '<span class="muted">Neutral</span>' : p.hostIfReach == null ? "" : esc(formatPct(p.hostIfReach))}</td>
            <td>${p.hostOverall == null ? "" : esc(formatPct(p.hostOverall))}</td>
          </tr>`).join("")}</tbody>
        </table>
        <p class="detail__note muted"><strong>Reaches round</strong> is the chance of playing in that round at all.
          <strong>Hosts, if it gets there</strong> is the chance the team hosts, if it reaches that round.
          <strong>Hosts, overall</strong> is the chance the team both reaches that round and hosts it.</p>
        <p class="detail__link"><a href="${esc(hrefWith({ page: "bracket", region: null, team: t.school }))}">See ${esc(t.school)}’s path in the bracket</a></p>
      </section>`
    : "";
  return `<div class="detail__panels">${record}${seeding}${pathPanel}</div>
    <p class="report-line"><button type="button" class="link-button" data-feedback="odds" data-team="${esc(t.school)}">Does something look wrong for ${esc(t.school)}? Let us know.</button></p>`;
}

function focusTeamRow() {
  const row = document.getElementById("focus-row");
  row?.scrollIntoView({ block: "center" });
  row?.querySelector(".row-toggle")?.focus({ preventScroll: true });
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
  if (!selected) track("team_picked", { from: "standings", team: toggle.dataset.team });
  navigate(hrefWith({ team: selected ? null : toggle.dataset.team }), { replace: true });
});

/** Region games as a card grid under a heading for each game day. */
function gamesSection(id, title, games, teams, focus) {
  // A finished game can be reported as a wrong score, and one from today or
  // earlier that has no score yet can have its final score reported.
  const now = today();
  const days = byDay(games).map(({ date, items }) => `<div class="game-day">
      <h3 class="game-day__title">${date ? esc(gameDate(date)) : "Date to be announced"}</h3>
      <ul class="game-grid">${items.map((g) => gameCard(g, teams, { focus, report: true, today: now })).join("")}</ul>
    </div>`);
  return `<section class="section" aria-labelledby="${id}-title">
    <h2 class="section-title" id="${id}-title">${title}</h2>
    ${days.join("")}
  </section>`;
}

/**
 * How each tie in a finished region's standings was broken: the API's
 * sentences, one per tiebreaker step, in the order the steps were applied.
 */
function tiebreaksSection(ties) {
  const blocks = ties.map((tie) => {
    const { title, teams } = tieHeading(tie);
    return `<div class="tiebreak">
      <h3 class="tiebreak__title">${esc(title)}</h3>
      <p class="tiebreak__teams">${esc(teams)}</p>
      <ol class="tiebreak__steps">${tie.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    </div>`;
  });
  return `<section class="section" aria-labelledby="tiebreaks-title">
    <h2 class="section-title" id="tiebreaks-title">How the ties were broken</h2>
    <p class="section-lead">The MHSAA region tiebreakers, step by step, with the actual results. <a href="/about#tiebreakers">How the tiebreakers work</a></p>
    ${blocks.join("")}
  </section>`;
}

// ------------------------------------------------------------ scenarios

/** The "report a scenario" link: under the Scenarios section when there is one, else under What has to happen. */
function scenarioReport(focus) {
  return `<p class="report-line"><button type="button" class="link-button" data-feedback="odds"${focus ? ` data-team="${esc(focus)}"` : ""}>See a scenario that can’t be right? Let us know.</button></p>`;
}

function scenariosSection(data, teams, prov, mode, focus, report = true) {
  // Cards sit under a group's h3, or (the insight cards) straight under the section's h2.
  const cardHtml = (level) => (c) => scenarioCard({
    ...c, team: teams[c.team], teams, provenanceHtml: c.p == null ? prov.plain : prov.odds, level,
  });
  const grid = (cards, level = 4) => `<div class="scenario-grid">${cards.map(cardHtml(level)).join("")}</div>`;
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
    const intro = `Full scenarios appear once five or fewer region games remain; ${remainingCount} are left.`;
    body = cards.length
      ? `<p class="prose muted">${esc(intro)} Until then, these are results that settle a spot no matter what else happens.</p>
         <div class="scenario-group scenario-group--spaced">${grid(cards, 3)}</div>`
      : `<p class="prose muted">${esc(intro)}</p>`;
  }

  return `<section class="section" aria-labelledby="scen-title">
    <h2 class="section-title" id="scen-title">What has to happen</h2>
    ${focusNote}
    ${body}
    ${report ? scenarioReport(focus) : ""}
  </section>`;
}

/** A foldable group of cards with a count beside its heading. */
function collapsible(label, count, body, open) {
  return `<details class="scenario-group"${open ? " open" : ""}>
    <summary><h3 class="sub-title">${label}</h3><span class="muted">${count} ${count === 1 ? "outcome" : "outcomes"}</span></summary>
    ${body}</details>`;
}

/**
 * Every distinct way the region can finish, one box each, with its chance in
 * the chosen odds mode. Long lists start folded so they don't bury the
 * completed games below. A card whose seeding goes to the tiebreakers opens
 * its explanation in a sheet.
 */
function allScenariosSection(scenarios, teams, focus, mode, provenanceHtml, place) {
  const cards = completeScenarioCards(scenarios);
  const open = cards.length <= 12;
  explainData = { cards, teams, focus, mode, provenanceHtml, place };
  return `<section class="section" aria-labelledby="all-scen-title">
    <details class="scenario-group scenario-group--section"${open ? " open" : ""}>
      <summary><h2 class="section-title" id="all-scen-title">Scenarios</h2><span class="muted">${cards.length} ${cards.length === 1 ? "way" : "ways"} the region can finish</span></summary>
      <div class="scenario-grid">${cards.map((c, i) => outcomeScenarioCard(c, teams, {
        focus, p: mode === "projected" ? c.pWeighted : c.p, provenanceHtml, explainId: i, level: 3,
      })).join("")}</div>
    </details>
  </section>`;
}

// ---------------------------------------------------- explanation sheet
// A scenario card's "Explanation" opens a sheet (the game sheet's look) with
// the whole scenario again and, under it, how the tiebreakers order each tie.

let explainData = null; // the region's scenario cards, from the last render
let explainSheet = null;
let explainOpen = null; // the open card's index, to refocus its button on close

function openExplanation(i) {
  const card = explainData?.cards[i];
  if (!card) return;
  if (!explainSheet) {
    explainSheet = document.createElement("dialog");
    explainSheet.className = "game-sheet";
    explainSheet.setAttribute("aria-labelledby", "explain-sheet-title");
    document.body.append(explainSheet);
    explainSheet.addEventListener("click", (e) => {
      if (e.target === explainSheet || e.target.closest("[data-sheet-close]")) explainSheet.close();
    });
    explainSheet.addEventListener("close", () => {
      const at = explainOpen;
      explainOpen = null;
      if (at != null) document.querySelector(`[data-explain-open="${at}"]`)?.focus({ preventScroll: true });
    });
  }
  explainOpen = i;
  explainSheet.innerHTML = explanationHtml(card);
  if (!explainSheet.open) explainSheet.showModal();
  explainSheet.scrollTop = 0;
  explainSheet.querySelector(".game-sheet__body").scrollTop = 0;
}

function explanationHtml(card) {
  const { teams, focus, mode, provenanceHtml, place } = explainData;
  return `<div class="game-sheet__head">
      <div>
        <p class="game-sheet__kicker">${esc(place)} · Explanation</p>
        <h2 class="game-sheet__title" id="explain-sheet-title" tabindex="-1" autofocus>${esc(card.label)}</h2>
        ${provenanceHtml}
      </div>
      <button type="button" class="game-sheet__close" data-sheet-close>${CLOSE}<span class="visually-hidden">Close</span></button>
    </div>
    <div class="game-sheet__body">
      ${outcomeScenarioCard({ ...card, label: "The scenario" }, teams, { focus, p: mode === "projected" ? card.pWeighted : card.p, level: 3 })}
      <section class="why" aria-label="Why this order">
        <h3 class="sub-title">Why this order</h3>
        ${whyTies(card.why)}
      </section>
    </div>`;
}

// ------------------------------------------------------------- bracket
// One class's playoff bracket, built for the undetermined state: an open
// side lists who might fill it with reach odds; a locked side is a fact (a
// lock, the seed, no percentage); a played game is a result. Each game
// expands in place to say who might play here and who'd host — from a
// picked team's side when one is picked. Hosting comes from the API.

const LIST_CAP = 5; // occupants shown before "Show all"

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
      // Certain, not merely likely.
      const s = [1, 2, 3, 4].find((k) => isCertain(t.odds?.[`p${k}`]));
      if (s) seeds[t.school] = { region: r.region, seed: s };
    }
  }
  // Without standings, a locked team's first-round spot still says its seed.
  for (const g of games) {
    for (const side of [g.side_a, g.side_b]) {
      const team = side.feeders.length === 1 ? lockedTeam(side) : null;
      if (team && !seeds[team]) seeds[team] = side.feeders[0];
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
  nextContext = contextHtml(`Class ${clazz}A Bracket`, controlsSummary, mode);
  // The bracket's odds are worked out from these same region rows.
  nextComputedAt = standings?.computed_from ? { from: standings.computed_from, to: standings.computed_to } : null;
  const focusNote = ctx.team
    ? `<p class="focus-note">Showing ${esc(ctx.team)}’s possible path. <a href="${esc(hrefWith({ team: null }))}" data-keep-scroll data-replace>Show every team</a></p>`
    : `<p class="focus-note muted">Select a game to see all possible matchups and locations, and pick a team to follow its path.</p>`;
  return `<div class="page">
    <header class="entry-head bracket-head">
      ${breadcrumbs([["Home", "/"], [`Class ${clazz}A`, hrefWith({ page: "class", region: null, team: null })], [`Class ${clazz}A Bracket`, null]])}
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
  // Each open slot's team, so no team shows in two slots of one round.
  bracketData.picks = new Map(cols.flatMap((c) => [...roundPicks(c, mode, bracketData.results)]));
  const halfControl = halves.length > 1
    ? `<div class="half-control" role="group" aria-label="Bracket half">
        ${["both", ...halves].map((h) => `<button type="button" class="half-control__item${h === "both" ? " half-control__item--both" : ""}" data-half="${h}" aria-pressed="${bracketUi.half === h}">${h === "both" ? "Both halves" : HALF_NAMES[h] ?? h}</button>`).join("")}
      </div>`
    : "";
  const tabs = `<div class="round-tabs" role="group" aria-label="Jump to a round">
      ${cols.map((c, i) => `<button type="button" class="round-tabs__item" data-round-jump="${i}" aria-current="${i === 0}" aria-label="${esc(c.name)}" title="${esc(c.name)}">${esc(shortRound(c.name))}</button>`).join("")}
    </div>`;
  const columns = cols.map((c) => `<section class="tcol" aria-label="${esc(c.name)}">
      <h2 class="tcol__title">${esc(c.name)}</h2>
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
  // The column heading isn't part of the button's name, so screen readers tabbing through hear the round here.
  const where = `<span class="visually-hidden">${esc([game.round, STATE_LABEL[state]].filter(Boolean).join(", "))}: </span>`;
  return `<button type="button" class="${cls}" data-game-open="${esc(game.id)}" aria-haspopup="dialog">${where}${rows}</button>`;
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
  const teamRow = (gutter) => treeLine(gutter, focus, focus, teams, teamSub, oddsCell(here.p) + spoken(" chance to play here"), " is-focus");
  // Every pairing here is under the API's 0.5% listing floor: too many long shots to name one.
  if (!top) return `${teamRow("")}${treeLine("vs", null, "Many opponents", teams, "Each under 0.5%", "", " trow--empty")}`;
  const oppRow = (gutter) => treeLine(gutter, top.opponent, top.opponent, teams, oppSub, oddsCell(top.p) + spoken(` chance of facing them if ${focus} gets here`), "");
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
    return row(" trow--locked", locked, locked, `${LOCK}<span class="visually-hidden">Locked in: </span>${esc(seedLabel(locked) ?? "Clinched a playoff spot")}`, "");
  }
  const list = occupants(side, mode);
  const firstRound = side.feeders.length === 1;
  if (!list.length) return row(" trow--empty", null, "No team can get here", "", "");
  const pick = bracketData.picks?.get(`${game.id}:${sideKey}`);
  const shown = (focus && list.find((o) => o.team === focus)) || list.find((o) => o.team === pick) || list[0];
  // First round: the region/seed this slot is for. Later: how many others could be here instead.
  const sub = firstRound ? esc(positionName(side.feeders[0])) : list.length > 1 ? `+${list.length - 1} more` : "";
  return row("", shown.team, shown.team, sub, oddsCell(shown.p) + spoken(" chance to play here"));
}

/** Words for screen readers only. */
const spoken = (text) => `<span class="visually-hidden">${esc(text)}</span>`;

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
let sheetFocus = null; // a selector to focus once the sheet re-renders (the team just picked)

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
  s.scrollTop = 0; // the whole sheet scrolls when the screen is small (or zoomed in), else just its body
  s.querySelector(".game-sheet__body").scrollTop = 0;
}

/** After a re-render (a team picked in the sheet, odds changed), show the open game's new numbers. */
function refreshSheet() {
  if (!sheet?.open || !bracketUi.open) return;
  const body = sheet.querySelector(".game-sheet__body");
  const top = body?.scrollTop ?? 0;
  const outer = sheet.scrollTop;
  sheet.innerHTML = sheetHtml(bracketUi.open);
  sheet.querySelector(".game-sheet__body").scrollTop = top;
  sheet.scrollTop = outer;
  // The control that was focused was just replaced; keep focus in the sheet,
  // on the same team if one was just picked.
  const want = sheetFocus && sheet.querySelector(sheetFocus);
  sheetFocus = null;
  if (!sheet.contains(document.activeElement)) (want ?? sheet.querySelector(".game-sheet__title"))?.focus({ preventScroll: true });
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
      <p class="report-line"><button type="button" class="link-button" data-feedback="odds" data-about="${esc(game.round)}">Does something look wrong in this game? Let us know.</button></p>
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
    if (bracketData?.focus !== team) track("team_picked", { from: "bracket", team });
    sheetFocus = `[data-pick-team="${CSS.escape(team)}"]`;
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
  const homeTag = host === sideKey ? '<span class="bteam__home"><span class="visually-hidden">, </span>Home</span>' : "";
  if (result) {
    const team = lockedTeam(side) ?? (sideKey === "a" ? result.winner : result.loser);
    const won = team === result.winner;
    const score = won ? result.winnerScore : result.loserScore;
    return `<div class="bteam bteam--result${won ? " is-winner" : ""}">${pickTeam(team)}${score != null ? `<span class="bteam__score">${esc(score)}</span>` : ""}</div>`;
  }
  const locked = lockedTeam(side);
  if (locked) {
    const label = seedLabel(locked);
    return `<div class="bteam bteam--locked">${pickTeam(locked)}<span class="bteam__fact">${LOCK}<span class="visually-hidden">Locked in: </span>${label ? esc(label) : "Clinched a playoff spot"}</span>${homeTag}</div>`;
  }
  const list = occupants(side, mode);
  const allKey = `${game.id}:${sideKey}`;
  const showAll = bracketUi.showAll.has(allKey);
  const shown = showAll ? list : list.slice(0, LIST_CAP);
  // Where the side comes from ("Region 2 #4 Seed", "Region 1 or 2 (Any Seed)"), over who might fill it.
  const label = `<p class="bside__label">${esc(sideLabel(side.feeders))}${homeTag}</p>`;
  const more = list.length > LIST_CAP
    ? `<button type="button" class="bside__more" data-show-all="${esc(allKey)}" aria-expanded="${showAll}">${showAll ? "Show fewer" : `Show all ${list.length}`}</button>`
    : "";
  if (!list.length) return `<div class="bside">${label}<p class="bside__empty muted">No team can get here</p></div>`;
  return `<div class="bside">${label}<ul class="bside__list">${shown.map((o) => `<li class="bteam">${pickTeam(o.team)}${oddsCell(o.p)}</li>`).join("")}</ul>${more}</div>`;
}

/** Host wording for a pairing, from whichever team is likelier to host: "60% chance Raleigh hosts". */
function hostText(team, opponent, hosts, pTeamHosts) {
  if (hosts === "neutral") return "Neutral site";
  if (hosts !== "split") return "";
  return pTeamHosts >= 0.5
    ? `${formatPct(pTeamHosts)} chance ${team} hosts`
    : `${formatPct(1 - pTeamHosts)} chance ${opponent} hosts`;
}

/** "at" when the opponent would host; "vs" otherwise (the picked team hosts, either could, or a neutral site). */
const oppJoiner = (hosts) => (hosts === "opponent" ? "at" : "vs");

/** Expanded game: a picked team's opponents here, or both sides and their possible matchups. */
function gameDetail(game) {
  const { mode, focus, teams } = bracketData;
  if (game.matchups == null) {
    return '<p class="bgame__note muted">Matchup odds aren’t available for this game yet.</p>';
  }
  const here = focus ? teamInGame(game, focus, mode) : null;
  if (here && (here.p > 0 || here.locked)) {
    const opp = opponentsFor(game, focus, mode);
    const intro = here.locked ? `${focus}’s possible opponents here` : `If ${focus} gets here (${formatPct(here.p)} chance)`;
    // These are conditional odds; say so, so they aren't read as the chance the game happens.
    const measure = here.locked ? "Chance of facing each one" : `Chance of facing each one, if ${focus} gets here`;
    return `<h3 class="bgame__heading">${esc(intro)}</h3>
      <p class="muted bgame__count">${esc(measure)}</p>
      <ol class="opp-list">${opp.map((o) => {
        const note = hostText(focus, o.opponent, o.hosts, o.pTeamHosts);
        return `<li><span class="mu__teams"><span class="mu__line"><span class="vs">${oppJoiner(o.hosts)}</span>${teamLabel(o.opponent, teams)}</span></span>${oddsCell(o.p)}${note ? `<span class="opp-list__host">${esc(note)}</span>` : ""}</li>`;
      }).join("")}</ol>`;
  }
  const ms = gameMatchups(game, mode);
  const hidden = game.other?.count ?? 0; // possible pairings under 0.5% in both modes, not listed
  const rows = ms.map((m) => {
    // Home team last ("Clinton at Booneville"); "vs" when the host isn't settled or the site is neutral.
    const h = hosting(m.hostA);
    const [away, home] = h.host === "a" ? [m.b, m.a] : [m.a, m.b];
    const joiner = h.host === "a" || h.host === "b" ? "at" : "vs";
    const note = hostText(m.a, m.b, h.host === "a" ? "team" : h.host === "b" ? "opponent" : h.host, h.p);
    return `<li><span class="mu__teams"><span class="mu__line"><span class="vs"></span>${teamLabel(away, teams)}</span><span class="mu__line"><span class="vs">${joiner}</span>${teamLabel(home, teams)}</span></span>${oddsCell(m.p)}${note ? `<span class="opp-list__host">${esc(note)}</span>` : ""}</li>`;
  });
  if (!ms.length) {
    return `<p class="muted bgame__count">So many teams could still meet here that ${hidden ? `none of the ${hidden} possible pairings has` : "no single matchup has"} even a 0.5% chance yet.</p>`;
  }
  // Each side's teams are listed above it, so the matchups follow directly.
  return `<h3 class="bgame__heading">Possible matchups</h3>
    <ol class="opp-list opp-list--matchups">${rows.join("")}</ol>
    ${hidden ? `<p class="muted bgame__count">Not showing ${hidden} other possible ${hidden === 1 ? "pairing" : "pairings"}, each under 0.5%</p>` : ""}`;
}

app.addEventListener("click", (e) => {
  const explain = e.target.closest("[data-explain-open]");
  if (explain) {
    const i = Number(explain.dataset.explainOpen);
    track("scenario_explanation_opened", { place: explainData?.place, scenario: explainData?.cards[i]?.label });
    openExplanation(i);
    return;
  }
  const card = e.target.closest("[data-game-open]");
  if (card) {
    const game = bracketData?.games.find((g) => g.id === card.dataset.gameOpen);
    track("bracket_game_opened", { class: bracketData?.clazz, round: game?.round, game: card.dataset.gameOpen });
    openSheet(card.dataset.gameOpen);
    return;
  }
  const half = e.target.closest(".half-control [data-half]");
  if (half) {
    track("bracket_half_changed", { half: half.dataset.half });
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
  else if (route.page === "bracket") parts.push(`Class ${route.clazz}A Bracket`);
  if (about) parts.push(about);
  if (team) parts.push(team);
  return parts.join(" · ") || null;
}

/**
 * The form. `game` (a region game) makes it a score report: a correction for
 * a finished game, or the final score for one with none yet. Otherwise it's
 * a general report starting on `category`, about `context`.
 */
function feedbackForm({ game = null, category = "other", context = null, page = "/" } = {}) {
  const honeypot = `<div class="fb-hp" aria-hidden="true"><label>Leave this empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>`;
  const opened = Date.now();
  // The fields a problem is about point at this line (sendFeedback), so it's read with them.
  const status = `<p class="fb-status" id="fb-status-${opened}" role="status" aria-live="polite"></p>`;
  if (game) {
    const scoreInput = (name, team, value) => `<label class="fb-score">
        <span class="fb-score__team">${esc(team)}</span>
        <input type="text" name="${name}" inputmode="numeric" pattern="[0-9]*" maxlength="3" value="${esc(value)}" autocomplete="off" required>
      </label>`;
    const played = game.awayScore != null && game.homeScore != null;
    const about = played
      ? `${game.away} ${game.awayScore}, ${game.home} ${game.homeScore}`
      : `${game.away} ${game.joiner} ${game.home}`;
    return `<form class="fb-form" novalidate data-fb-form data-mode="score" data-opened="${opened}" data-page="${esc(page)}" data-game="${esc(JSON.stringify(game))}">
      <p class="fb-about">${esc(about)} · ${esc(gameDate(game.date))}</p>
      <fieldset class="fb-scores">
        <legend>${played ? "The correct final score" : "The final score"}</legend>
        ${scoreInput("away", game.away, game.awayScore)}
        ${scoreInput("home", game.home, game.homeScore)}
      </fieldset>
      <label class="fb-field"><span>Where did you see it? <span class="muted">(optional)</span></span>
        <textarea name="note" rows="2" maxlength="${NOTE_MAX}" placeholder="A link to the box score, a school’s post, etc."></textarea>
      </label>
      ${honeypot}
      <div class="fb-turnstile"></div>
      ${status}
      <div class="fb-actions"><button type="submit" class="fb-submit">${played ? "Send correction" : "Send score"}</button></div>
      <p class="fb-fine muted">A moderator checks every ${played ? "correction" : "score"} before it changes the standings.</p>
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
      <p class="prose">Spotted a wrong score, see odds or a scenario that can’t be right, or have an idea? Let us know.
        To correct a region game’s score, open its region and select “Wrong score?” on the game, or “Report score” on one that has no score yet. For any other game, choose “A score” below.</p>
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
  track("feedback_opened", { kind: game ? "score" : category });
  const page = location.pathname + location.search;
  removeTurnstile(feedbackSheet.querySelector("[data-fb-form]"));
  feedbackSheet.innerHTML = `<div class="game-sheet__head">
      <div>
        <p class="game-sheet__kicker">Feedback</p>
        <h2 class="game-sheet__title" id="feedback-title" tabindex="-1" autofocus>${!game ? "Send feedback" : game.awayScore == null ? "Report a final score" : "Report a wrong score"}</h2>
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
  markProblem(form, problem ? problemFields(form, data) : [], status.id);
  if (problem) return;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Sending…";
  // Sent within moments of opening the form: wait out the rest of the minimum, then send.
  // A quick real correction still goes through; the honeypot, Turnstile and the API's limits
  // handle scripts.
  const wait = MIN_FILL_MS - (Date.now() - Number(form.dataset.opened));
  if (wait > 0) await new Promise((resolve) => { setTimeout(resolve, wait); });
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

/**
 * The fields a form problem is about: both scores for a score correction
 * (they're checked as a pair); else the message, or the email when the
 * message is fine.
 */
function problemFields(form, data) {
  if (form.dataset.mode === "score") return [form.elements.away, form.elements.home];
  const messageOk = !feedbackProblem({ message: String(data.get("message") || ""), email: "" });
  return [messageOk ? form.elements.email : form.elements.message];
}

/** Mark `fields` invalid, tie them to the problem's sentence, and put the cursor in the first. */
function markProblem(form, fields, statusId) {
  for (const el of form.querySelectorAll("[aria-invalid]")) {
    el.removeAttribute("aria-invalid");
    el.removeAttribute("aria-describedby");
  }
  for (const el of fields) {
    el.setAttribute("aria-invalid", "true");
    el.setAttribute("aria-describedby", statusId);
  }
  fields[0]?.focus();
}

function feedbackSent(form) {
  const score = form.dataset.mode === "score";
  track("feedback_sent", { kind: score ? "score" : "feedback" });
  const inSheet = Boolean(form.closest("dialog"));
  const done = document.createElement("div");
  done.className = "fb-sent";
  done.setAttribute("role", "status");
  done.innerHTML = `<p class="fb-sent__title">Thanks, we’ve got it.</p>
    <p class="muted">${score
      ? "A moderator will check the score. Once it’s approved, the standings and odds pick it up at the next update."
      : "A moderator will read it. If you left an email, we may follow up."}</p>
    ${inSheet ? '<button type="button" class="fb-submit" data-sheet-close>Done</button>' : '<a href="/feedback" class="fb-again">Send something else</a>'}`;
  removeTurnstile(form);
  form.replaceWith(done);
  done.querySelector("button, a")?.focus({ preventScroll: true });
}

// The message's hint follows the category: a score report needs the game and the score.
const MESSAGE_HINTS = {
  score: "Which game, and what was the final score?",
  odds: "What looks wrong?",
  other: "The more specific, the faster we can fix it!",
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
    const score = (v) => (v == null ? null : Number(v)); // no score yet: reporting the final
    openFeedback({
      game: { date: d.date, away: d.away, home: d.home, joiner: d.joiner, awayScore: score(d.awayScore), homeScore: score(d.homeScore) },
    });
    return;
  }
  const trigger = e.target.closest("[data-feedback]");
  if (!trigger || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  openFeedback({ category: trigger.dataset.feedback, team: trigger.dataset.team || null, about: trigger.dataset.about || null });
});

// --------------------------------------------------------------- boot

// Following a link on the front page: where it goes, and which part of the page it was in
// (a section's heading id, or "classes" for the class buttons at the top).
app?.addEventListener("click", (e) => {
  const link = e.target.closest(".page.landing a[href]");
  if (!link || e.button !== 0) return;
  const to = new URL(link.href, location.href);
  if (to.origin !== location.origin) return;
  const section = link.closest(".landing-classes")
    ? "classes"
    : link.closest("section[aria-labelledby]")?.getAttribute("aria-labelledby").replace(/^landing-/, "") ?? null;
  track("home_link_clicked", { to: to.pathname, section }, { leaving: true });
});

// Opening a folded group of scenarios (a click on its heading; groups that start open don't count).
app?.addEventListener("click", (e) => {
  const summary = e.target.closest("details.scenario-group > summary");
  if (summary && !summary.parentElement.open) {
    track("scenarios_opened", { section: summary.querySelector("h2, h3")?.textContent.trim() ?? null });
  }
});

if (app) {
  // Back and Forward move between pages, so focus goes to the page's heading.
  window.addEventListener("popstate", async () => {
    const token = renderToken + 1;
    await render();
    if (token === renderToken) settleFocus(null);
  });
  startAnalytics(API);
  render();
}
