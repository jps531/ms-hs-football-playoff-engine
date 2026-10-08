// 2026 interim UI: pick a class, pick a region, read that region's race.
// Two views on one page — the class's region list and a region — addressed
// by query string so every view has a shareable URL.

import { escapeHtml as esc, formatPct, recordText, shortDate } from "./format.js";
import {
  oddsCell, provenance, statusBadge, teamMark, teamLabel, scenarioCard, classScrubber, chevronIcon,
} from "./components.js";
import { outcomeCards, insightCards } from "./scenarios.js";

const API = "/api/v1";
const CLASSES = [1, 2, 3, 4, 5, 6, 7];
const STORAGE_CLASS_KEY = "mshsf.class";

const app = document.getElementById("app");
const scrubberHost = document.getElementById("scrubber");

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

let seasonPromise;
function currentSeason() {
  seasonPromise ??= getJSON("/seasons").then((rows) => {
    const seasons = rows.map((r) => r.season).sort((a, b) => b - a);
    if (!seasons.length) throw new Error("no seasons");
    return seasons[0];
  });
  return seasonPromise;
}

/** school -> team metadata (helmet/logo/colors), for every class. */
async function teamsBySchool(season) {
  try {
    const rows = await getJSON(`/teams?season=${season}`);
    return Object.fromEntries(rows.map((t) => [t.school, t]));
  } catch {
    return {}; // identity is a nicety; initials fall back without colors
  }
}

/** "Week 9" / "First Round" label for the last game date the snapshot covers. */
async function throughLabel(season, clazz, asOf) {
  try {
    const { dates } = await getJSON(`/seasons/${season}/dates?class=${clazz}`);
    const played = dates.filter((d) => d.kind === "games" && d.date <= asOf);
    const last = played[played.length - 1];
    return last ? { label: last.description, date: last.date } : { date: asOf };
  } catch {
    return { date: asOf };
  }
}

// ------------------------------------------------------------- routing

function readRoute() {
  const q = new URLSearchParams(location.search);
  const clazz = Number(q.get("class"));
  const region = Number(q.get("region"));
  return {
    clazz: CLASSES.includes(clazz) ? clazz : null,
    region: Number.isInteger(region) && region > 0 ? region : null,
  };
}

function hrefFor(clazz, region) {
  return region ? `/?class=${clazz}&region=${region}` : `/?class=${clazz}`;
}

function navigate(url) {
  history.pushState(null, "", url);
  render();
}

function rememberClass(clazz) {
  try { localStorage.setItem(STORAGE_CLASS_KEY, String(clazz)); } catch { /* storage unavailable */ }
}
function rememberedClass() {
  try {
    const c = Number(localStorage.getItem(STORAGE_CLASS_KEY));
    return CLASSES.includes(c) ? c : null;
  } catch {
    return null;
  }
}

let renderToken = 0;
async function render() {
  const token = ++renderToken;
  const route = readRoute();
  const clazz = route.clazz ?? rememberedClass() ?? CLASSES[0];
  rememberClass(clazz);
  renderScrubber(clazz);
  app.setAttribute("aria-busy", "true");
  try {
    const html = route.region ? await regionView(clazz, route.region) : await classView(clazz);
    if (token !== renderToken) return;
    app.innerHTML = html;
  } catch (err) {
    if (token !== renderToken) return;
    app.innerHTML = notice(
      err?.status === 404
        ? "There’s nothing published for this yet. Check back once region play is underway."
        : "This page couldn’t load right now. Please try again in a moment.",
    );
  } finally {
    if (token === renderToken) app.removeAttribute("aria-busy");
  }
  document.title = pageTitle(clazz, route.region);
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
  const active = scrubberHost.querySelector('[aria-checked="true"]');
  active?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

scrubberHost.addEventListener("click", (e) => {
  const item = e.target.closest("[data-class]");
  if (item) navigate(hrefFor(Number(item.dataset.class)));
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
  navigate(hrefFor(Number(items[next].dataset.class)));
  scrubberHost.querySelector(`[data-class="${items[next].dataset.class}"]`)?.focus();
});

// ------------------------------------------------------ class view (entry)

async function classView(clazz) {
  const season = await currentSeason();
  const [summary, teams] = await Promise.all([getJSON(`/standings/summary?season=${season}`), teamsBySchool(season)]);
  const cls = summary.classes.find((c) => c.class_ === clazz);

  const head = `<div class="page entry-head">
    <h1 class="title"><span class="title__word">Class</span> <span class="title__num">${clazz}A</span></h1>
  </div>`;
  if (!cls || !cls.regions.length) {
    return head + notice("No standings have been published for this class yet.");
  }

  const rows = cls.regions.map((r) => {
    const leader = r.leader;
    const leaderHtml = leader
      ? `${teamMark(leader.school, teams[leader.school])}<span class="team-name">${esc(leader.school)}</span>
         <span class="muted">${esc(recordText(leader.region_wins, leader.region_losses))}</span>`
      : '<span class="muted">No games yet</span>';
    const alive = `${r.teams_alive} ${r.teams_alive === 1 ? "team" : "teams"} alive`;
    return `<li><a class="region-link" href="${hrefFor(clazz, r.region)}">
      <span class="region-link__name">Region ${r.region}</span>
      <span class="region-link__leader"><span class="visually-hidden">Leader:</span>${leaderHtml}</span>
      <span class="region-link__alive">${esc(alive)}</span>
    </a></li>`;
  });

  return `${head}<div class="page"><ol class="region-list">${rows.join("")}</ol></div>`;
}

// ------------------------------------------------------------ region view

async function regionView(clazz, region) {
  const season = await currentSeason();
  const [data, teams] = await Promise.all([
    getJSON(`/standings/${clazz}/${region}?season=${season}&include_team_scenarios=true`),
    teamsBySchool(season),
  ]);
  const through = await throughLabel(season, clazz, data.as_of_date);
  const prov = provenance(through, shortDate);

  const remaining = data.remaining_games ?? [];
  return `<div class="page">
    <header class="region-head">
      <a class="region-head__back" href="${hrefFor(clazz)}">All ${clazz}A regions</a>
      <h1 class="title"><span class="title__word">Region</span> <span class="title__num">${region}-${clazz}A</span></h1>
      ${data.headline ? `<p class="headline">${esc(data.headline)}</p>` : ""}
      ${prov}
    </header>
    ${standingsTable(data, teams)}
    ${remaining.length ? remainingGames(remaining, teams) : ""}
    ${remaining.length ? scenariosSection(data, teams, prov) : ""}
  </div>`;
}

const ODDS_COLUMNS = [
  { key: "p1", label: "1st", mid: false },
  { key: "p2", label: "2nd", mid: true },
  { key: "p3", label: "3rd", mid: true },
  { key: "p4", label: "4th", mid: true },
  { key: "p_playoffs", label: "Playoffs", mid: false },
];

function standingsTable(data, teams) {
  const rows = data.teams.map((t, i) => {
    const r = t.record;
    const detailId = `detail-${i}`;
    const cells = ODDS_COLUMNS.map(
      (c) => `<td class="col-odds${c.mid ? " col-mid" : ""}">${oddsCell(t.odds[c.key])}</td>`,
    );
    return `<tr class="${t.eliminated ? "is-eliminated" : ""}">
        <td class="col-pos">${i + 1}</td>
        <th scope="row" class="col-team">
          <button type="button" class="row-toggle" aria-expanded="false" aria-controls="${detailId}">
            ${chevronIcon}${teamMark(t.school, teams[t.school])}<span class="row-toggle__label"><span class="team-name">${esc(t.school)}</span>${statusBadge(t)}</span>
          </button>
        </th>
        <td class="col-rec">${esc(recordText(r.region_wins, r.region_losses, r.region_ties))}</td>
        <td class="col-rec col-overall">${esc(recordText(r.wins, r.losses, r.ties))}</td>
        ${cells.join("")}
      </tr>
      <tr class="detail" id="${detailId}" hidden><td colspan="9">${rowDetail(t)}</td></tr>`;
  });

  const oddsHeads = ODDS_COLUMNS.map(
    (c) => `<th scope="col" class="col-odds${c.mid ? " col-mid" : ""}">${c.label}</th>`,
  );
  return `<table class="standings">
    <caption class="visually-hidden">Standings and odds of finishing in each playoff position. Select a team for details.</caption>
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

/** Expanded row: the numbers that don't fit the row itself. */
function rowDetail(t) {
  const r = t.record;
  const stats = ODDS_COLUMNS.map(
    (c) => `<span class="detail__stat">${c.label} ${oddsCell(t.odds[c.key])}</span>`,
  );
  const notes = [`Overall record ${recordText(r.wins, r.losses, r.ties)}.`];
  const host = t.home_game_odds?.first_round;
  const reach = t.odds.p_playoffs;
  if (host != null && reach > 0 && !t.eliminated) {
    notes.push(
      `Hosts a first-round game: ${formatPct(host)} if they get there, ${formatPct(host * reach)} overall.`,
    );
  }
  if (t.coin_flip_needed) notes.push("A coin flip may be needed to settle a tie involving this team.");
  return `<div class="detail__grid">${stats.join("")}</div><p class="detail__note">${esc(notes.join(" "))}</p>`;
}

app.addEventListener("click", (e) => {
  const toggle = e.target.closest(".row-toggle");
  if (!toggle) {
    const link = e.target.closest("a[href^='/?']");
    if (link && !e.metaKey && !e.ctrlKey && !e.shiftKey && e.button === 0) {
      e.preventDefault();
      navigate(link.getAttribute("href"));
      window.scrollTo(0, 0);
    }
    return;
  }
  const open = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!open));
  document.getElementById(toggle.getAttribute("aria-controls")).hidden = open;
});

function remainingGames(games, teams) {
  // location_a is team_a's perspective. Away team listed first.
  const items = games.map((g) => {
    let first = g.team_a;
    let second = g.team_b;
    let joiner = "vs";
    if (g.location_a === "home") { first = g.team_b; second = g.team_a; joiner = "at"; }
    else if (g.location_a === "away") joiner = "at";
    return `<li>${teamLabel(first, teams)}<span class="vs">${joiner}</span>${teamLabel(second, teams)}</li>`;
  });
  return `<section class="section" aria-labelledby="games-title">
    <h2 class="section-title" id="games-title">Remaining games</h2>
    <ul class="games">${items.join("")}</ul>
  </section>`;
}

// ------------------------------------------------------------ scenarios

function scenariosSection(data, teams, prov) {
  const cardHtml = (c) => scenarioCard({ ...c, team: teams[c.team], teams, provenanceHtml: prov });
  const grid = (cards) => `<div class="scenario-grid">${cards.map(cardHtml).join("")}</div>`;
  const remainingCount = data.remaining_games.length;

  let body;
  if (data.scenarios_available && data.teams.some((t) => t.paths?.length)) {
    const g = outcomeCards(data.teams);
    const parts = [
      ["The region title", g.title],
      ["Playoff spots", g.playoffs],
    ].filter(([, cards]) => cards.length).map(([label, cards]) => `<div class="scenario-group">
        <h3 class="sub-title">${label}</h3>${grid(cards)}</div>`);
    // Seeding matters less than who's in, and can run long, so it starts closed.
    if (g.seeding.length) {
      parts.push(`<details class="scenario-group"${parts.length ? "" : " open"}>
        <summary><h3 class="sub-title">Seeding</h3><span class="muted">${g.seeding.length} outcomes</span></summary>
        ${grid(g.seeding)}</details>`);
    }
    body = parts.length
      ? parts.join("")
      : '<p class="prose muted">Every remaining outcome is already settled.</p>';
  } else {
    const cards = insightCards(data.key_insights);
    const intro = `Full scenarios appear once six or fewer region games remain; ${remainingCount} are left.`;
    body = cards.length
      ? `<p class="prose muted">${esc(intro)} Until then, these are results that settle a spot no matter what else happens.</p>
         <div class="scenario-group scenario-group--spaced">${grid(cards)}</div>`
      : `<p class="prose muted">${esc(intro)}</p>`;
  }

  return `<section class="section" aria-labelledby="scen-title">
    <h2 class="section-title" id="scen-title">What has to happen</h2>
    ${body}
  </section>`;
}

// --------------------------------------------------------------- boot

if (app) {
  window.addEventListener("popstate", render);
  render();
}
