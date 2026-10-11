# 2026 Interim UI — Design Brief

Build guidance for the temporary 2026-season UI: region scenarios and odds
only. This is a narrow, shippable slice of a larger product that launches for
the 2027 season. Everything here is written so the interim build is a genuine
subset of the full design — users who come back in 2027 should recognize what
they already learned, and no decision here should have to be unwound.

Read sections 1 and 2 before writing any code. Section 2 is the most
important part of this document.

---

## 1. Scope

**In scope**
- Pick a class, pick a region, see that region's playoff race.
- Per-team odds: make playoffs, win region / finish in each seed position.
- The scenario explorer: what has to happen for a given outcome.
- Remaining games in the region.
- Light and dark themes.

**Explicitly out of scope** — do not build, do not stub, do not leave
navigation entries pointing at them: brackets, scoreboard, game pages, team
pages, rankings, helmet browser, championship history, user accounts,
following teams, submissions, admin tooling, share-image generation,
historical date scrubbing, and simulate/what-if mode.

Simulate mode in particular is the single biggest feature of the 2027 product
and the most tempting thing to half-build. Leave it out entirely. A partial
version would teach users an interaction that then changes.

**One page is the product.** Everything above fits in a region view plus a way
to get to it. Resist adding a dashboard, an "overview," or a landing page full
of summary cards.

---

## 2. The look: what to avoid, and what to do instead

The single biggest risk for this build is that it comes out looking like every
other AI-assisted sports stats site shipped this year. Several already exist.
None of them have scenario analysis — that is the product's actual
differentiator — but they all share a visual signature, and landing in that
signature would make this project look like one of them at a glance.

### 2.1 Banned patterns

Do not produce any of these. They are the tells:

- **The 4-up KPI card grid.** A row of bordered cards at the top of the page,
  each with a tiny uppercase label and a big number. This is the default
  opening move for generated dashboards. There is no "stats overview" section
  in this product.
- **Card-wrapping everything.** Every section in a bordered, rounded,
  drop-shadowed container with a `CardHeader` / `CardTitle` /
  `CardDescription`. Identical border-radius and identical soft grey shadow on
  every block regardless of hierarchy.
- **An icon beside every heading.** Lucide (or any) icons used as heading
  decoration. Icons appear only where they carry meaning: the clinched check,
  the eliminated cross, the coin-flip coin, the odds-mode glyphs.
- **Untouched component-library theming.** If shadcn/ui is used, the default
  slate/zinc palette and default radius must be fully replaced by the tokens
  in section 3 before any component is rendered. A default shadcn surface is
  instantly recognizable.
- **Gradients as decoration.** No gradient text, no blue-to-purple washes, no
  gradient card borders. The only gradient-like thing in this product is the
  odds intensity ramp, which encodes data.
- **Tracked-out uppercase eyebrow labels** above headings ("REGION
  STANDINGS"), and unnecessary labels above content generally.
- **Emoji as section markers.**
- **Zebra-striped tables.** Use a single hairline rule between rows.
- **Uniform spacing everywhere** (`p-6` / `gap-4` on every container) with no
  rhythm or hierarchy.
- **A `max-w-7xl` centered container with the same padding on every section.**
- **Tab shells** named Overview / Analytics / Details.
- **Numbered markers (01 / 02 / 03)** unless the content is genuinely a
  sequence.
- **Monospace for small data labels.** Numerals are handled in section 4.
- **A trailing `→` appended to link and button text.**

### 2.2 The direction instead

**Think editorial, not dashboard.** This is a publication about a playoff
race, not a control panel. A reader should land on a region and feel like
they're reading a well-set page about a story in progress — who's in, who's
out, and exactly what has to happen next. The nearest reference points are a
well-designed sports almanac or a newspaper's standings page, not a SaaS
analytics product.

**Lead with a sentence, not a number.** The product's secret sauce is that it
can say, in English, "Taylorsville clinches the region with a win over Mize —
no help needed." That sentence is the hero of the region page. Set it large,
in the headline style, above the table. Generated stats sites lead with a grid
of numbers because that's all they have; this one can lead with meaning.

**Let the data supply the color.** The chrome — backgrounds, rules, labels,
containers — stays achromatic (see the neutral scale, which is a true grey
with zero chroma, chosen for exactly this reason). The color on screen comes
from the helmets, the team colors, and the odds ramp. That inversion is
unusual and is a large part of what will make this look unlike its neighbors.

**Separate with space and hairlines, not boxes.** The default instinct is to
put a border around every group. Use whitespace, a single hairline rule, and
typographic hierarchy instead. Reserve an actual bordered container for
things that genuinely are discrete objects (a scenario card).

**Spend boldness in one place.** The display typeface, used big, on the region
title and the headline sentence. Everything else stays quiet and disciplined.
Don't add a second bold gesture.

**Asymmetry and real hierarchy.** One thing on each screen should be clearly
the biggest. If everything is 14–16px with headings barely larger, the page
reads as a generated template.

**Density where it's earned.** Tables should be dense and scannable — that's
appropriate for standings. Air goes around them, not inside them.

### 2.3 One deliberate exception

The provenance line (section 5.2) is a short meta string joined with middle
dots. That pattern is normally a generated-page tell, and it is used here on
purpose and only here: it's a tested, load-bearing component that states what
data a reader is looking at, and it survives screenshot cropping. Do not
propagate the middot-chain pattern anywhere else in the UI.

---

## 3. Color tokens

Implement as CSS custom properties with a `.dark` override — not as hardcoded
Tailwind palette values. These are final, sampled from the project's logo and
verified against WCAG.

### 3.1 Primitives

```
brand-50   #F2FBF8      neutral-50   #F7F7F7
brand-100  #E1F7EF      neutral-100  #EFEFEF
brand-200  #C2EFDF      neutral-200  #DFDEDF
brand-300  #9BE6CD      neutral-300  #C7C7C7
brand-400  #66DDB5      neutral-400  #A4A3A4
brand-500  #26C58F      neutral-500  #7B7A7B
brand-600  #198C65      neutral-600  #5C5B5C
brand-700  #137252      neutral-700  #4C4C4C
brand-800  #0F5B41      neutral-800  #393939
brand-900  #0D4632      neutral-900  #272727
brand-950  #07291D      neutral-950  #161616
```

`brand-600` is the logo green. It is **4.22:1 on white** — large text and
icons only, never body-size text. `brand-700` is the interactive color
(5.9:1 with white).

The neutral scale is deliberately a true achromatic grey (no blue cast). Do
not substitute Tailwind's `slate` or `zinc`.

### 3.2 Semantic layer

| Token | Light | Dark |
|---|---|---|
| `--surface-page` | `#FFFFFF` | `neutral-950` |
| `--surface-card` | `#FFFFFF` | `neutral-900` |
| `--surface-raised` | `neutral-50` | `neutral-800` |
| `--surface-inverse` | `neutral-900` | `neutral-50` |
| `--text-primary` | `neutral-900` | `neutral-50` |
| `--text-secondary` | `neutral-600` | `neutral-400` |
| `--text-on-inverse` | `neutral-50` | `neutral-900` |
| `--border` | `neutral-200` | `neutral-800` |
| `--connector` | `neutral-400` | `neutral-500` |
| `--interactive` | `brand-700` | `brand-700` |
| `--interactive-hover` | `brand-800` | `brand-800` |
| `--accent-identity` | `brand-600` | `brand-500` |
| `--state-clinched` | `brand-700` | `brand-700` |
| `--state-eliminated` | `#B91C1C` | `#B91C1C` |
| `--state-coinflip` | `#FBBF24` | `#FBBF24` |
| `--state-live` | `brand-700` | `brand-500` |

`--connector` is specifically for the logical connector lines in scenario
condition groups. It reads as notation, not chrome, and is intentionally
stronger than `--border`.

### 3.3 The odds ramp

Five semantic slots plus a text color, flipping under dark:

| Slot | Light | Dark |
|---|---|---|
| `--odds-1` | `neutral-50` | `neutral-800` |
| `--odds-2` | `brand-100` | `brand-950` |
| `--odds-3` | `brand-200` | `brand-900` |
| `--odds-4` | `brand-300` | `brand-800` |
| `--odds-5` | `brand-400` | `brand-700` |
| `--odds-text` | `neutral-900` | `brand-50` |

**Bucket by the displayed, rounded value**, inclusive-lower:
`[0,20) → 1`, `[20,40) → 2`, `[40,60) → 3`, `[60,80) → 4`, `[80,100] → 5`.
Bucketing on the raw value lets "79%" land in the 80s color, which looks like
a bug.

### 3.4 Color semantics (do not violate)

- **Green** = real, brand, good outcomes.
- **Red (`#B91C1C`)** = elimination only. Never for errors, never for "down"
  deltas, never decorative.
- **Amber (`#FBBF24`)** = coin-flip only. Pairs with `neutral-900` text, never
  white.
- **Violet** is reserved for simulate mode in the 2027 product. Do not use it
  anywhere in this build.
- Odds mode (Projected vs Toss-up, if implemented) is never differentiated by
  color — only by glyph and type style.

---

## 4. Typography

Two families, clearly distinct:

- **Nippo** (Fontshare, free, includes web license) — display only.
  Heaviest weight is Bold; there is no SemiBold.
- **Inter** — everything else, and **all numerals without exception**.

| Style | Font | Size / line-height | Use |
|---|---|---|---|
| `display-32` | Nippo Bold | 32 / 36 | Region title, page hero |
| `display-28` | Nippo Bold | 28 / 32 | Mobile page title |
| `h1` | Inter SemiBold | 24 / 30 | Section titles |
| `h2` | Inter SemiBold | 20 / 26 | Sub-sections, card titles |
| `headline-sentence` | Inter SemiBold | 22 / 32 | The scenario sentence that leads the page |
| `body` | Inter Regular | 16 / 24 | Prose |
| `table` | Inter Regular | 14 / 20 | Table cells — **tabular figures** |
| `table-emphasis` | Inter Medium | 14 / 20 | Team names in tables — **tabular figures** |
| `caption` | Inter Regular | 12 / 16 | Captions, footnotes |
| `caption-provenance` | Inter Medium | 12 / 16, +2% tracking | The provenance line |
| `stat-sm` | Inter Medium | 14 / 20 | Odds cells — **tabular figures** |
| `stat-md` | Inter SemiBold | 16 / 20 | Card stats — **tabular figures** |
| `stat-lg` | Inter Bold | 24 / 28 | Featured numbers — **tabular figures** |

**Tabular figures are mandatory** on every style marked above
(`font-variant-numeric: tabular-nums`). Without them, odds columns don't align
and any future count-up animation jitters.

The rule to internalize: **Nippo announces, Inter explains.** Nippo never
renders a number and never renders a full sentence.

Body line length under 80 characters.

---

## 5. Components

Build these as real, reusable components. They are the pieces that carry
forward unchanged into 2027.

### 5.1 Odds cell

A fixed-width cell with an `--odds-N` background and the percentage in
`--odds-text`, `stat-sm`, centered or right-aligned.

**Honest rounding is required:**
- A value below 0.5% that is not actually zero renders `<1%`.
- A value above 99.5% that is not actually certain renders `>99%`.
- Literal `0%` and `100%` are reserved for mathematical certainty.

Fixed width sized to `>99%` so columns never ragged-edge.

### 5.2 Provenance line

One small line stating what the reader is looking at. Three segments joined by
middle dots, each segment owning its own leading separator so omitted segments
leave no orphaned dot:

- **Time** — `Through Week 9 · Oct 24` is the default and most common state.
  If games are in progress, `● LIVE · Week 9` with the dot and text in
  `--state-live`.
- **Mode** — `· Projected` with a trend glyph, or `· Toss-up` with a dice
  glyph in italic. Omit entirely if odds mode isn't implemented.
- Sim segment: not in this build.

Place it above the standings table and on any scenario card. Style
`caption-provenance`.

**LIVE pulse**: 8px dot, static, with a ring expanding 8→20px while fading
60%→0%, 1200ms ease-out, infinite. Under `prefers-reduced-motion`, hide the
ring entirely — the word "LIVE" carries the meaning, the pulse is emphasis.

### 5.3 Status badges

Icon + text, never color alone. Pill shape, `radius: 6px`.

- **Clinched** — `--state-clinched` fill, white text, check icon. Label
  specificity comes from the text, not a second color: `Clinched`,
  `Clinched #1`, `Clinched host`. Show only the highest; never stack two
  badges on one row.
- **Eliminated** — `--state-eliminated` fill, white text, ✕ icon.
- **Coin-flip** — `--state-coinflip` fill, `neutral-900` text, coin icon.

### 5.4 Condition chips and the AND/OR grammar

A chip is one condition: a 24px helmet, the subject team's name, and the
condition. `Raleigh beats Magee by 8-10`. Surface `--surface-raised`,
radius 6px, `table` type size.

Margin conditions support both forms — a threshold (`by 11+`) and a bounded
range (`by 8-10`). Ranges are real; three-way tiebreak math produces them.

**The grammar is explicit, not positional:**
- Chips joined by **AND** are connected by a short vertical `--connector` line
  with a small `AND` label centered on it.
- Alternative groups are separated by a full-width horizontal `--connector`
  rule with an **inverted `OR` pill** centered on it (`--surface-inverse`
  background, `--text-on-inverse` text).

The inverted OR pill is the visual anchor that makes nesting readable. Chips
are center-aligned within their group.

Never rely on line position alone to express AND vs OR — chips wrap on narrow
screens and the grammar would break exactly where it matters most.

### 5.5 Team identity

- **Always helmet + team name.** Never helmet alone as identification; a
  reader who doesn't recognize a helmet design is stuck. At 24px a helmet is
  an identity *hint*, not identification.
- Helmet assets carry a baked-in white keyline, so they need no container.
- Logo assets get a container (`--surface-raised` fill, 1px `--border`,
  rounded) at 48px and up, for footprint normalization — logos vary wildly in
  aspect ratio and would otherwise misalign table columns. No container below
  48px.
- Fallback when no logo exists: initials on the team's primary color. Initials
  are the first letters of significant words, dropping County / High / School
  / Academy — Wilkinson County → `W`, Oak Grove → `OG`, Enterprise Clarke →
  `EC`. Two letters maximum.
- **Team colors need contrast clamping** against the surface they sit on.
  Measured examples: a royal blue `#2A3EAD` is 8.78:1 on white but **1.70:1**
  on a dark card. Clamp lightness only (preserving hue and saturation) until
  the text variant hits 4.5:1 and the UI-element variant hits 3:1, against
  white in light mode and `neutral-900` in dark. If the backend already
  provides clamped variants, use them; if not, compute once at load, not per
  render. **Never clamp images** — helmets and logos are artwork and are
  exempt.

### 5.6 Class scrubber

Segmented control, not a dropdown: `1A 2A 3A 4A 5A 6A 7A`. The values form an
ordered scale and a dropdown destroys that. Track `--surface-raised`, selected
pill `brand-700` fill with white text in light mode and `brand-400` fill with
dark text in dark mode. Unselected labels `--text-secondary` (verify
`neutral-400` in dark, not `neutral-500`).

Sticky at the top of the region view, inside an opaque wrapper with a bottom
`--border` so scrolling content terminates cleanly beneath it.

Horizontally scrollable on mobile with the active item scrolled into view.
Arrow keys move between items; the group is a single tab stop.

### 5.7 Tug-of-war / win-probability bars

If any two-sided probability bar appears: **always `#2563EB` blue for home and
`#EA580C` orange for away.** Never team colors — two red schools produce an
unreadable bar, and a mapping that sometimes uses team colors and sometimes
doesn't teaches the reader nothing reliable. American football convention: the
away team is listed first and rendered left.

---

## 6. Pages

### 6.1 Entry — choosing a region

The minimum that works: the class scrubber, then that class's regions as a
simple list or grid. Each region shows its name, the current leader (helmet +
name + record), and the number of teams still alive.

Do not build this as a dashboard of summary cards. A list is correct here.

### 6.2 Region view — the product

Order on the page:

1. **Region title** in `display-32` (Nippo Bold).
2. **The headline sentence** in `headline-sentence` — the single most
   interesting fact about this race right now. This is the hero.
3. **Provenance line.**
4. **Standings table.** Columns: position, helmet + team name (with any status
   badge inline), record, and odds. Keep odds to **two columns maximum on
   mobile** — playoff odds and region-title odds are the two that matter.
   Real `<table>` semantics with `<th scope>`.
5. **Remaining games** in the region — a plain list, each game linking
   nowhere (no game pages in this build).
6. **Scenarios.** For each meaningful outcome: a title ("Mize wins the
   region"), then the condition group using the chip grammar from 5.4.

Rows may expand to show more detail. If they do, expansion is where any
additional numbers live — including the conditional hosting figure if hosting
odds are shown at all ("63% to reach · hosts 28% overall, 82% if they get
there").

### 6.3 Methodology

One short page explaining in plain English how the odds are produced. Write
real copy. This page is a credibility asset and takes ten minutes.

---

## 7. Accessibility floor

Non-negotiable, and all of it is cheap if done while building:

- Every text/background pair meets WCAG AA (4.5:1 body, 3:1 large text and
  non-text elements). The tokens above are pre-verified; don't introduce new
  colors without checking.
- Color is never the sole carrier of meaning. Badges have icons and text; the
  odds ramp always prints its number.
- Visible keyboard focus on every interactive element, including inside the
  segmented control and on expandable rows.
- Touch targets 44px minimum.
- `prefers-reduced-motion` respected on every animation.
- Real table semantics; `aria-expanded` on expandable rows.
- The page is usable at 200% text zoom — tables reflow to fewer columns rather
  than overflowing.
- No tooltip-only information. Hover doesn't exist on touch.

---

## 8. Definition of done

Before calling it finished, check:

1. Screenshot the region page and ask honestly: does this look like the other
   AI-built high school stats sites, or does it look like someone designed it?
   If it's the former, the fix is almost always in section 2.1.
2. Every number in the UI is Inter with tabular figures.
3. Dark mode has been looked at directly — not assumed to work. Check the
   odds ramp, team colors, and helmet silhouettes specifically.
4. 375px wide, with the longest real team name in the data. Nothing overflows,
   the provenance line survives, the chip grammar still reads.
5. No violet anywhere.
6. No element exists that the 2027 design would have to contradict.
