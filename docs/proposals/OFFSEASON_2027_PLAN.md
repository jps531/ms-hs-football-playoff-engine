# Plan: the 2026–27 offseason

> **STATUS: Not implemented.** Decisions and a plan for after the 2026 season, written down so the
> work can start from them. Nothing below exists yet except where it says so. Two nearer items from
> the same discussion are being built now and aren't in this doc: the daily update's speed-ups
> (reusing unchanged regions, redrawing only changed cards, step timings, the playoff update's Elo)
> and an always-reachable class picker.

Four parts, in the order they were discussed:

1. [Historical seasons](#1-historical-seasons)
2. [Moving the front end to Next.js and Tailwind](#2-nextjs-and-tailwind)
3. [The site's layout: class hubs, team pages, scores](#3-the-sites-layout)
4. [Time on the page: the provenance line and a timeline](#4-time-on-the-page)

Parts 2–4 ship together: the layout changes the URLs, which only makes sense once, in the new
front end, and the timeline is designed with it. Part 1 runs alongside.

---

## 1. Historical seasons

**Goal:** results back to the early 1990s at least, ideally the early 1980s, with standings,
brackets and champions for every season, and (kept on the table) the scenarios and odds a reader
would have seen during each old season, worked out once.

### Decisions

| Question | Decision |
|---|---|
| Classes | Stay integers 1–7 shown as "{n}A". Eras with fewer classes (1A–5A, 1A–6A) fit as is. The A/AA/B/BB era waits until we get there (it needs a per-season class label). |
| Seeds and rounds | At most 4 seeds per region and 5 playoff rounds, ever. The schema's fixed columns (`odds_1st..odds_4th`, second round … champion) stay. |
| "1A–4A have a second round" | Must come from the season's playoff format, not `class <= 4`. |
| Point-differential cap (tiebreaker steps 3–4, ±12 today) | Configurable per season. |
| Home-team rules | Configurable per season. |
| School lineage | Many predecessors per school, chains (A→B→C) followed, and an Elo merge on consolidation. |
| Scenarios for old seasons | Wanted; computed once per season, offline. Revisit only if it proves far harder than expected. |
| Data | AHSFHS has results back that far. Which schools merged into which comes from the site's owner, by hand. |

### What's hard-coded today (and what isn't)

Already general:

- Each season's bracket is data (`playoff_formats`, `playoff_format_slots`), per season and class.
- Region counts are found from each season's schools; region games are worked out from the
  alignment (`school_seasons`).
- The AHSFHS scraper takes any year (`gamesbyyear.asp?…&Year=`).
- `backfill-historical-snapshots` runs any season with games.
- The database has no CHECK constraints on class or region.

Needs work, smallest first:

| Area | Where | Change |
|---|---|---|
| Region loader | `region_files.py`: every class 1–7 must have schools; cycles start in odd years | Accept the classes a season has; let a cycle start any year (or one file per season for old eras). |
| Second round | `class <= 4` / `class >= 5` in ~75 lines (`home_game_scenarios.py`, `api_helpers.py`, `bracket_home_odds.py`, `region_scenarios_pipeline.py`, `share_cards.py`, `team_image.py`, `standings.js`, AHSFHS round names) | One helper, "does this season and class have a second round", from `playoff_formats.num_rounds`; every caller uses it. |
| Seeds per region | `playoff_formats.seeds_per_region` exists but nothing reads it | Read it where a season could have fewer than 4 (or assert 4 until one does). |
| Point-differential cap | literal 12 in `tiebreakers.py` and the margin enumeration | A per-season rules row (below), passed through the resolver and the enumeration. |
| Home-team rules | odd/even-year region rule (`season % 2`), "fewer home games" quarterfinal rule, the same-region rule, which half hosts the final, hard-coded in `bracket_home_odds.py` and `home_game_scenarios.py` | Named rule sets chosen per season (below); today's rules become the 2025– set. |
| Lineage | `SCHOOL_RENAMES`, `SCHOOL_SUCCESSORS`, `SCHOOL_STOPPED_PLAYING` in `data_helpers.py`; mirrored by hand in `FORMER_SLUGS` (`routes.js`); one predecessor; chains don't chain | A table (below); the front end gets the old links from the API instead of a hand-kept copy. |
| Elo across a consolidation | `with_predecessor_ratings` copies one predecessor's rating | A merge rule (below). |
| Elo class priors | a fixed 7-entry list (`win_probability.py`) | Fine for eras of ≤7 classes; index by class. |
| Old-era names | `OFFICIAL_TO_AHSFHS` (~17 current names) | Grows as old seasons are loaded. |
| Past brackets in the daily run | `_write_past_brackets` redraws every past season one image at a time when the drawing code changes | Being fixed now (fingerprinted, parallel). |

### Proposed shape

**Season rules** — one row per season (or per range of seasons):

```
season_rules(season, pd_cap, home_rules, tiebreak_rules, notes)
```

`pd_cap` is the tiebreaker's point-differential cap (12 today). `home_rules` and `tiebreak_rules`
name a rule set in code (`"mhsaa-2025"`, `"mhsaa-1998"`, …): code, because rules are logic, not
numbers, and each set gets its own tests against that era's real brackets. The engine takes the
season's rules everywhere it now uses constants.

**Lineage** — replaces the three lists and `FORMER_SLUGS`:

```
school_lineage(predecessor, successor, first_season, kind, weight, notes)
-- kind: renamed | consolidated | absorbed | stopped
```

Several rows may share a successor (a consolidation); a predecessor may itself be a successor
(chains). The API answers "what was this school before" and "what did it become", for team pages,
old links, and the region loader's checks.

**Elo merge** — a consolidated school starts from its predecessors' final ratings, averaged with
`weight` (default: equal; enrollment if we ever have it), then regressed toward the class prior as
any school's rating is between seasons.

**Historical scenarios** — `backfill-historical-snapshots` already rebuilds a season's snapshots
date by date. For an old season it runs once (oldest season first, so Elo carries forward), with
that season's rules, and its results are stored like any season's. Cost is bounded: it's the same
work a live season does, once, off the daily run.

### Order of work

1. Data survey: for a few sample years per era, confirm AHSFHS coverage, collect alignments (which
   schools were in which class and region), playoff formats, and merges.
2. Season rules and the second-round helper (no behavior change for 2025–26; tests prove it).
3. Lineage table and Elo merge; move today's renames and successors into it.
4. Load one old season end to end (alignment, formats, schools, scores, backfill), check it against
   the real champions and brackets, then the rest of its era.
5. Earlier eras, each with its own rule set where the rules differ.

### Open questions

- What were the tiebreaker and home rules in each era? (MHSAA handbooks; the owner may have them.)
- What should a team page show for a school that closed — its own page, or its successor's history?
- Old schools have no location, mascot or colors (the NCES and MHSAA sources cover current schools
  only): enter by hand, or leave out?

---

## 2. Next.js and Tailwind

**Decision:** move the front end to Next.js with Tailwind during the offseason, for the 2027 season.

### Why

Every page is drawn twice today: in the browser (`nginx/html/static/js/`, ~6,800 lines; views are
~60% of `app.js`) and in Python for search engines and link previews (`static_pages.py`,
`region_pages.py`, ~2,300 lines), kept identical by 265 parity tests and spliced into the page by
nginx's server-side includes. Next.js renders on the server once, so the second copy, its tests and
the include machinery go away. New pages (team pages, scores, history, simulate mode) would each
otherwise be written twice; drawing them once is also the surest way to keep the two from ever
disagreeing.

### Shape

- **Next.js (App Router), server components** fetching the existing API (`/api/v1`). Pages
  pre-rendered and refreshed after the daily update (on-demand revalidation from the pipeline), so
  readers get server-rendered HTML for every page, any week or season, not only the latest.
- **Tailwind** configured with the site's own color tokens (CSS custom properties with a `.dark`
  override), as the design brief requires — not Tailwind's default palette.
- **Carried over almost as is:** the pure modules (`bracket.js`, `standings.js`, `scenarios.js`,
  `format.js`, `routes.js`, `search.js`, `regions.js`'s markup helpers), which already run under
  Node and have tests. TypeScript as they move.
- **Rewritten:** the views and sheets, the focus and screen-reader handling, the CSS.
- **Stays in Python:** the images to share (Pillow, ~4,200 lines) and the link-preview cards, drawn
  by the share-assets step as now; Next.js only links them.
- **Removed:** `static_pages.py` and `region_pages.py` page bodies, the parity tests, the nginx
  `$share_page` / `$share_body` maps and includes. Link-preview tags come from Next.js's metadata.
- **Deployed** as one more container behind nginx. nginx keeps TLS, the API proxy, the static
  share files and security headers.

### Rolling it out

Path by path: nginx sends a path to Next.js once its page is ready, everything else to today's app.
Team pages (new) go first; then the class hub; then the rest; then today's app is removed. Every
current URL keeps working (redirects where the layout changes, part 3).

### Risks

- The production server is small (2 CPUs, a 2 GB worker): Next.js's memory needs checking before
  launch.
- Rewrites lose small behaviors; the current pages' tests and the parity cases are the checklist.

---

## 3. The site's layout

**Decision:** organize by class and team, not by tool. Lands with the Next.js move.

### Today

Standings, Bracket and Regions are top-level tools, each per class; a team is a `?team=` on a
region page. Breadcrumbs: Home › Class 5A › Region 2-5A (and › Class 5A Bracket, › Class 5A
Regions).

### Proposed

| Page | Address (proposed) | What it is |
|---|---|---|
| Class hub | `/5a` with tabs: Standings · Bracket · Map · Scores | Everything about a class; the tab is part of the address. |
| Region | `/5a/region-2` | The region's standings, games, scenarios (today's region page). |
| Team | `/teams/greenwood` | Schedule and results, standing and odds, playoff path ("what has to happen"), region and map, history and lineage (part 1). Search lands here. |
| Scores | `/scores?date=…` (filter by class) | Statewide scoreboard by date; each game links to its game page. |
| Game | `/games/{id}` | Score, line score where we have it, what it meant for each team. |
| Home | `/` | A feed: today's biggest races, clinches, upsets (the "home feed" in the 2027 plans). |

Breadcrumbs follow it: Home › 5A › Region 2-5A › Greenwood. Simulate mode ("play this out"), the
calibration page and the media page hang off these pages rather than adding top-level tabs. The
class picker (being made always reachable now) becomes the class hub's switcher.

Old addresses redirect: `/standings/5a` → `/5a`, `/standings/5a/2` → `/5a/region-2`, `/brackets/5a`
→ `/5a/bracket`, `/regions/5a` → `/5a/map`, `?team=` on a region page → the team page.

### Open questions

- Tab order and which tab a class opens on (Standings, or Bracket once the playoffs start?).
- What the home feed shows in the offseason.

---

## 4. Time on the page

**Decision:** revisit during the Next.js move. The direction below came out of the discussion.

Today the provenance line doubles as the controls ("2026 season · Through Week 9 · Oct 24 ·
Projected"); the 2026 briefs accepted that for the interim and listed a "timeline scrubber" for
later (`/seasons/{season}/dates` is documented as "notable game dates for a timeline scrubber").
The data supports either: a snapshot per game date for the whole season (playoffs included), and
labeled dates (Week 7, First Round).

| | Provenance line with menus (today) | Timeline scrubber |
|---|---|---|
| For | Compact, precise, accessible; says exactly what a screenshot shows | Shows that the season moves; invites exploring; can mark clinches and upsets |
| Against | Hides the time dimension; easy to miss | Imprecise on touch; harder to make accessible; takes room |

**Direction: both, each doing what it's good at.**

- The provenance line becomes a plain statement of what's on screen ("Through Week 9 · Oct 24 ·
  Projected") with one "change" control.
- The timeline becomes content, not a control: each team's odds over the season as a chart on
  region and team pages, with marks for clinches and big results. Tapping a week moves the page to
  that week (`?week=`/`?date=`).
- With server rendering (part 2), any week's page is a real page that search engines and link
  previews can read, which the current pre-rendering (latest week only) can't do.
