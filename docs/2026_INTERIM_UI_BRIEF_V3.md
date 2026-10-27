# 2026 Interim UI — Brief v3

Follow-on to `2026_INTERIM_UI_BRIEF.md` (design system, banned patterns,
accessibility floor) and `2026_INTERIM_UI_UPDATE.md` (URL shape, bracket view,
OG images). Both still apply in full. This document assumes that work is
shipped and covers what comes next.

Section 1 explains why these items matter, because three of the five work
items below only make sense in that light.

---

## 1. Why these items

Three things shape this work:

1. **The scenario engine is the differentiator, and the bracket is not.**
   Projected brackets already exist elsewhere. The minimal, margin-verified
   condition set — "Taylorsville clinches with a win Friday, no help needed" —
   does not exist anywhere in this market. Information hierarchy should
   reflect that.
2. **Other sites server-render; we do not.** They have hundreds of indexed
   pages. We currently have one page that says "This page needs
   JavaScript to load the standings." That is the largest structural
   disadvantage we have, and it is fixable with work already underway.
3. **Transparency is our strongest defensible position.** We credit AHSFHS
   by name, cite the MHSAA handbook, and publish our update schedule. That
   advantage is worth extending deliberately rather than leaving implicit.

---

## 2. Pre-render real content into the region shells

**Highest priority. This is an extension of the OG work, not a new system.**

The pipeline already writes a per-region HTML shell with meta tags. Have it
write the **content** into the body as well — real, static HTML that the JS
app replaces on load.

Minimum viable content per region shell:

- An `<h1>` with the region name.
- The headline sentence.
- The standings table as a real `<table>`: position, team, record, playoff
  odds, with the odds as plain text percentages.
- Remaining games as a list.
- The provenance line as text.

The JS app hydrates over it exactly as it does today — no framework, no build
step, no change to the client architecture. The static content is a
server-rendered floor, not a second implementation.

This fixes three things at once:

- **Indexing.** Search engines get the actual race for every region instead of
  an empty shell. For a site people find by searching their school's name,
  this is the difference between being findable and not.
- **The no-JS failure mode.** The page currently renders nothing without
  JavaScript. After this it degrades to a readable standings page.
- **Perceived speed.** Content paints before the JS fetches.

Do the same for class pages. Keep the generic shell as the fallback for any
route without a specific one.

**Constraint:** the static content and the hydrated content must not disagree.
Both come from the same snapshot, so generate them from the same data in the
same pipeline run, and let the provenance line state that snapshot in both.

---

## 3. Keep scenarios ahead of the bracket

The bracket is the newest and most interesting thing to look at, which makes
it tempting to promote. Don't. It is the one feature where something
comparable already exists elsewhere.

- The default landing experience stays standings-and-scenarios. Entering the
  site should put a region race in front of the user, not a bracket.
- The bracket is reachable from the region view and from nav, but is not the
  first thing offered.
- On the region view, the headline sentence and the condition chips stay above
  anything bracket-related.

The bracket differentiates by being **probabilistic with slot-level matchup
expansion** — who you might play and where — not by existing. Make sure the
slot expansion is easy to discover, because that is the part no one else has.

---

## 4. Make the rating visible

Projected odds are driven by an Elo rating that currently appears nowhere in
the UI. That is a transparency gap on exactly the dimension where we are
otherwise strongest: we ask people to trust a number produced by a model they
cannot see any part of.

Two acceptable forms, in order of preference:

1. **In the expanded team row** — the team's current rating, labeled plainly
   ("Elo rating: 1642"), near the odds it produces.
2. **On the methodology page** — a short section showing the current top ten
   or twenty statewide with ratings, as an illustration of what the model
   thinks.

**Do not build a full rankings page.** Ratings density is the other site's
entire product and competing there is both off-mission and a losing fight. The
goal is to make the model legible, not to publish a leaderboard.

Vocabulary rule, applied here and everywhere: **ratings are numbers, rankings
are positions.** An Elo value is a rating. If a position is shown, it is a
ranking. Never use the words interchangeably.

---

## 5. Extend the methodology page

It is already one of the strongest pages on the site.
Three cheap additions make the advantage explicit:

**A "what we don't do" section.** State plainly that the site does not publish
point spreads, predicted scores, or betting lines, and that it produces
probabilities about seeding, hosting, and advancement only. This is a real
product boundary, it is the honest framing of the existing wagering
disclaimer, and it sets the site apart from products whose main output is
spreads and over/unders.

**Explicit limits.** Say what the model does not account for — injuries,
weather, personnel changes, forfeits not yet recorded — and that early-season
ratings are less informative than late-season ones. Stating limitations
increases trust rather than reducing it, and it is the opposite of what the
competing sites do.

**Citation guidance.** One line inviting reuse with attribution: "Using these
numbers in a story? Please credit mshsfootball.com and link the region page."
Local sports coverage in November is the most valuable distribution available
to this site, and the clean per-region URLs now make a citation easy.

---

## 6. Labeling discipline

A standing rule, prompted by a specific failure mode observed on a competing
site, where a list of all-time program win totals is presented under the
heading "Power Rankings" — leading a casual reader to take historical records
as current-season strength.

**Every number on the site must be labeled with exactly what it measures, in
terms a reader cannot misread.**

- "Playoff odds" means probability of making the playoffs — not of winning the
  region, not of hosting.
- A per-round reach number is cumulative, and must say so.
- Anything derived from a past snapshot says which one.
- Never label a historical or all-time figure in a way that implies current
  form.

When a label is ambiguous, lengthen it. Precision costs a few characters and
is the entire basis of the site's credibility relative to its neighbors.

---

## 7. Groundwork for 2027 (verify only, do not build)

Two small verification tasks that cost little now and avoid rework later.

**Calibration data.** The 2027 plan is to publish how often stated odds
actually occur — if we say 70%, it should happen about 70% of the time —
backtested against stored weekly snapshots. Confirm that the snapshots retain
predicted probabilities per team per week in a form that can be joined to
final outcomes. If they do, nothing more is needed now. If they don't,
changing the retention is far cheaper than reconstructing a season.

**Clean export shape.** The 2027 plan includes a "For Media" page. Nothing
needs building, but confirm the region endpoints return everything a reporter
would want — standings, odds, conditions, provenance — without requiring
multiple calls to assemble a single region's picture.

---

## 8. Still out of scope

Unchanged, and worth restating because some are now adjacent to shipped work:

Simulate mode in any form, including tap-to-advance on bracket slots. Violet.
Point spreads, predicted scores, or betting lines — permanently, not just for
the interim. MAIS coverage. A full rankings page. Team pages, game pages,
scoreboard, helmet browser, championships. Accounts, following, favorites.
Submissions. Admin. Maps. The home feed. Email capture. Real helmet artwork.

---

## 9. Definition of done

1. `curl` a region URL with JavaScript disabled and get a readable standings
   page with the headline sentence, the table, and the provenance line.
2. Static and hydrated content agree, because they come from the same snapshot.
3. A search engine fetch of a region page returns its own title, description,
   and race — not the generic shell.
4. Landing on the site puts a region race in front of the user, not a bracket.
5. The Elo rating behind Projected odds is visible somewhere in the UI.
6. The methodology page states what the site does not do.
7. No label on the site could lead a reader to mistake a historical figure for
   a current one.
8. Accessibility pass re-run after the bracket: keyboard path through slot
   expansion, 44px targets on slot taps, reduced-motion on any snap-scroll
   behavior, and 200% zoom on the bracket at 375px.
