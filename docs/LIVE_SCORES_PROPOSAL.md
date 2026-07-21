# Plan: X/Twitter Live Score Ingestion Pipeline

> **STATUS: Not implemented.** This is a design proposal, not a description of
> shipped functionality. None of the files, tables, env vars, or Docker
> services described below exist in the codebase yet. See the project roadmap
> for when this is planned to be picked up.

## Context

MHSAA football games are played on various days — primarily Thursdays and Fridays during regular season and playoffs, with weather-delay makeups possible any day, and State Championship games played throughout the day (not just evenings). Score data currently enters the DB only via AHSFHS scheduled scrapers. This pipeline adds near-real-time ingestion from X/Twitter using the Filtered Stream API, activated dynamically based on whether the DB has games scheduled for today.

**Approach: X API v2 Filtered Stream** (not polling)

| | Filtered Stream | Polling |
|---|---|---|
| Cost | ~$4/month | ~$54/Friday |
| Latency | 5–6 seconds | ~2 minutes |
| Reliability | Backfill recovery on disconnect | Gaps guaranteed |

**X API cost model:** $0.005 per tweet delivered. ~200 tweets/Friday × 4 Fridays/month = ~$4/month. 2M tweet cap/month; we use <0.04%.

---

## Tooling Choice

- **Stream listener**: **Dedicated Docker service** (plain Python script, `restart: unless-stopped`). Prefect flows are designed for short discrete tasks — a 4–8 hour persistent connection doesn't fit that model. Docker's native restart semantics handle reconnection lifecycle cleanly.
- **Rule management** (add/delete stream rules before/after game windows): **Prefect flows** — these are exactly the short-lived setup/teardown tasks Prefect excels at.

---

## Architecture Overview

```
Docker service: twitter-stream-listener (runs continuously)
  └─ Main loop:
       ├─ Query DB: any games today?
       │    ├─ No → sleep 30min, retry
       │    └─ Yes → determine game_window (see below)
       ├─ Outside game window → sleep until window opens
       └─ Inside game window → connect to filtered stream
              ├─ On tweet: parse_score() → upsert_game() → audit_record()
              ├─ On disconnect: exponential backoff → reconnect(backfill_minutes=5)
              └─ On window end: close stream, sleep until next check

Prefect flow: setup_game_rules_flow (run before each game day)
  └─ Load today's schedule from DB → build rules → POST to X stream rules API

Prefect flow: teardown_game_rules_flow (run morning after each game day)
  └─ Fetch game-tagged rules → DELETE from X stream rules API
```

**Game window logic** (queried from DB, not hardcoded by weekday):
- If any games today with `round IN ('State Championship', 'State Finals', ...)`: window = 10am–11pm CT
- Otherwise (regular season / non-championship playoffs): window = 4pm–11pm CT
- Weather makeup games: covered automatically since they appear in the DB

---

## Stream Rule Strategy

X tags each delivered tweet with the matching rule ID(s), so the rule tag tells us the game without parsing team names out of the tweet text. Rules are case-insensitive by default.

**Tiered rules per game matchup** (~225 rules on a busy Friday, well under 1,000):

**Rule 1 — Both teams (every game, highest confidence ~0.9):**
```
"Team A" "Team B" (score OR final OR halftime OR points OR leads)
```
Requires both team names to appear in the tweet — strongest signal, handles ambiguous school names naturally without needing mascots.

**Rule 2 — Single-team (non-ambiguous schools, confidence ~0.7):**
```
("Team A" OR "Team A alias") (score OR final OR halftime OR points OR leads)
```
Catches tweets mentioning only one team + score keywords.

**Rule 2 variant — Mascot rule (ambiguous schools only, confidence ~0.65):**
```
"Team A Mascot Name" (score OR final OR halftime OR points OR leads)
```
Used instead of bare single-team rule for schools like "Brandon" or "Clinton" where the school name alone has too many non-football matches. Mascot is optional coverage on top of the both-teams rule, not the primary signal.

Rule tag format (all rules for a game share the same school/opponent/date):
`"school=Madison Central|opponent=Brandon|date=2025-10-03|rule=both_teams"`

Rule count: 75 games × (1 both-teams + ~2 single-team) ≈ 225 rules/night.

---

## School Alias Config

New file: `backend/data/school_twitter_aliases.json`

Defines per-school search terms and ambiguity flags for stream rule generation.

```json
{
  "South Panola": {
    "aliases": ["South Panola"],
    "ambiguous": false
  },
  "Madison Central": {
    "aliases": ["Madison Central", "MC Jaguars"],
    "ambiguous": false,
    "note": "MC is common abbreviation"
  },
  "Brandon": {
    "aliases": ["Brandon"],
    "mascot_aliases": ["Brandon Bulldogs"],
    "ambiguous": true,
    "note": "bare 'Brandon' matches too many non-football tweets"
  },
  "Clinton": {
    "aliases": ["Clinton"],
    "mascot_aliases": ["Clinton Arrows"],
    "ambiguous": true
  }
}
```

**Rule generation logic (runs inside `setup_game_rules_flow` each game day):**

1. **Load tonight's schedule** → get all active `(school_a, school_b)` pairs
2. **Build alias map** for every active team from the config: `{school: [alias1, alias2, ...]}`
3. **Detect alias collisions**: any alias string that appears in two or more active teams tonight
   - Example: if both South Panola and South Pontotoc are playing, "SP" is a collision
   - If only South Panola is playing, "SP" is unambiguous tonight and safe to use
4. **Generate rules per game:**
   - **Both-teams AND rule** (always): `"primary_alias_A" "primary_alias_B" (score OR final OR halftime OR points OR leads)` — ambiguity doesn't matter here since both teams must appear
   - **Single-team rule**: include all aliases for this school *except* those flagged `ambiguous: true` in config AND those that are runtime-collisions tonight
   - **Mascot rule**: for `ambiguous: true` schools, add `"Mascot Name" (score OR ...)` as supplemental coverage

**Result**: "SP" is treated as unambiguous on nights when only one SP-abbreviated team plays (used in single-team rule), and promoted to both-teams-only on nights when both play. Same logic handles "WL" (West Lincoln / West Lowndes), "EC" (East Central / Enterprise Clarke), and any other abbreviation pair automatically — no manual maintenance needed.

The both-teams rule is the primary signal for all games. The single-team / mascot rules provide incremental coverage at lower confidence.

---

## School Name Reference Tables

These inform the initial `school_twitter_aliases.json` population.

### Ambiguous Names
Schools where the name alone generates high non-football Twitter noise. Use `ambiguous: true`; do NOT use bare name in single-team rules.

| School | Why Ambiguous | Single-Team Rule Approach |
|---|---|---|
| Brandon | Very common first name | "Brandon Bulldogs" only |
| Clinton | Political surname (Bill, Hillary, DeWitt) | "Clinton Arrows" only |
| West Point | US Military Academy | "West Point Green Wave" or "West Point MS" |
| Oxford | Oxford University; "Oxford comma" | "Oxford Chargers" only |
| Hamilton | Broadway musical; Founding Father | "Hamilton Lions" only |
| Houston | Major US city; Whitney Houston | "Houston Hilltoppers" only |
| Lafayette | General; many cities | "Lafayette Commodores" only |
| Columbus | Christopher Columbus; Columbus OH | "Columbus Falcons" only |
| Charleston | Charleston SC (major city); Charleston dance | "Charleston Tigers" only |
| Florence | Italian city; Florence Nightingale | "Florence Eagles" only |
| Philadelphia | Major US city; Eagles/Phillies/76ers | "Philadelphia Tornadoes MS" only |
| Meridian | Geographic/navigation term | "Meridian Wildcats" only |
| Columbia | University; country; many cities | "Columbia Wildcats MS" only |
| Corinth | Ancient Greek city; biblical | "Corinth Warriors" only |
| Salem | Witch trials; Salem OR; many cities | "Salem Wildcats MS" only |
| Newton | Isaac Newton; many cities | "Newton Tigers" or "Newton County MS" |
| Pearl | Gemstone; Pearl MS is major suburb | "Pearl Pirates" only |
| Grenada | Caribbean nation | "Grenada Chargers" — note: "Granada" (Spanish) is a common typo |
| Union | Generic word; labor union | "Union Yellow Jackets" only |
| Forest | Generic word | "Forest Bearcats" only |
| Lake | Generic word | "Lake Hornets MS" only |
| Bay | Generic word | "Bay Tigers MS" only |
| Winona | Winona Ryder; Winona MN | "Winona Tigers MS" only |
| Shannon | Common first name | "Shannon Red Raiders" only |
| Terry | Common first name | "Terry Bulldogs MS" only |
| Bruce | Common first name | "Bruce Trojans MS" only |
| Raymond | Common first name | "Raymond Rangers MS" only |
| Magee | Common surname | "Magee Trojans" only |
| Myrtle | First name; Myrtle Beach | "Myrtle Hawks MS" only |
| Long Beach | Long Beach CA (major city) | "Long Beach Bearcats MS" only |

### Common Abbreviations
Add as extra entries in `aliases` array.

| School | Abbreviation(s) | Notes |
|---|---|---|
| Madison Central | MC, "MC Jaguars" | Very commonly used |
| South Panola | SP, "South Pan" | Regional usage |
| Northwest Rankin | NWR, "Northwest" | Common in coverage |
| Northeast Jones | NEJ, "NE Jones" | Regional usage |
| Harrison Central | HC, "Harrison" | Local shorthand |
| East Central | EC | Generic; lower value alone |
| Holmes County Central | HCC, "Holmes County" | |
| Neshoba Central | "Neshoba" | School name drops "Central" in speech |
| Southeast Lauderdale | SEL | |
| Northeast Lauderdale | NEL | |
| Forrest County Agricultural | FCA, "Forrest County" | "Ag" also common |
| Itawamba Agricultural | "Itawamba Ag", "Itawamba AHS" | "Ag" is the colloquial short form |
| South Jones | SJ | |
| West Jones | WJ | |
| West Lincoln | WL | ⚠️ Collides with West Lowndes — runtime collision detection handles this |
| West Lowndes | WL | ⚠️ Collides with West Lincoln |
| South Pontotoc | "South Pont" | Note: "SP" collides with South Panola — use "South Pont" instead |
| Enterprise Clarke | "E Clarke" | Avoids EC collision with East Central; use "Enterprise Clarke" as full alias |
| St. Stanislaus | "St. Stan's", "Stanislaus" | |
| D'Iberville | "D'Ib", "Diberville" | |
| J Z George | "JZ George", "J.Z. George" | Apostrophe/period variants |
| H. W. Byers | "Byers", "HW Byers" | |
| M. S. Palmer | "Palmer", "MS Palmer" | |
| Tupelo Christian | "TC", "Tupelo Christian Prep" | |
| North Pontotoc | "North Pont" | |
| Desoto Central | "DeSoto", "DeSoto Central" | |

### Frequently Misspelled
Add misspellings as extra entries in `extra_aliases` array.

| School | Common Misspellings | Notes |
|---|---|---|
| Kosciusko | Koscuisko, Kosciuski, Kosciosko | Very frequently misspelled — highest priority |
| Baldwyn | Baldwin | Standard spelling; most fans write "Baldwin" |
| Eupora | Euporia | Extra "i" inserted — extremely common |
| Pascagoula | Pascagula, Pascagoulla | Native American origin |
| Bogue Chitto | Bogue Chito, Bogey Chitto | Choctaw origin |
| Nanih Waiya | Nani Waiya, Naneh Waya, Nanith Waiya | Choctaw origin; highly variable |
| Noxapater | Noxpater, Noxipater | Choctaw origin |
| D'Iberville | Diberville, D'iberville | Apostrophe dropped |
| Pelahatchie | Pelahachie, Pelahatchee | |
| Tishomingo County | Tishimingo, Tishominga | Chickasaw origin |
| Okolona | Ockolona, Ocolona | |
| Senatobia | Sennatobia, Senetobia | |
| Heidelberg | Heidelburg, Heidleberg | German origin |
| Grenada | Granada | Spanish-style spelling; very common |
| Coffeeville | Coffeyville | Famous Coffeyville KS/OK causes confusion |
| Coahoma County | Coohama, Coahomma | Choctaw origin |
| Itawamba | Ittawamba, Itawambe | |
| Vardaman | Vardamann, Vardman | |
| Sumrall | Summerall | |
| Loyd Star | Lloyd Star | "Lloyd" is the standard spelling |
| Amite County | Ameite (pronounced "Ah-MEET") | Pronunciation surprises spellers |
| O'Bannon | Obannon, O'bannon | Apostrophe dropped; capitalization |

---

## Files to Create

### `backend/data/school_twitter_aliases.json`
Initial alias config for all MHSAA schools. Start with all schools using the school name as the primary alias; flag known-ambiguous schools with `ambiguous: true` and add mascot aliases.

### `backend/helpers/twitter_parser.py`
Pure Python — no API calls, fully unit-testable.

```python
@dataclass
class ParsedScore:
    score_a: int
    score_b: int
    game_status: GameStatus | None
    confidence: float  # 0.0–1.0; threshold to apply: 0.60
```

**`parse_score_from_text(text: str) -> ParsedScore | None`**
Tiered regex patterns (confidence decreases with tier):
1. `#MHSAAScore TeamA 21 TeamB 14 Final` → confidence ≥ 0.9
2. `TeamA 21, TeamB 14 – Final` → confidence ≥ 0.75
3. `TeamA leads TeamB 21-14 end Q3` → confidence ≥ 0.65
4. `21-14` or `21 to 14` (score-only, no team names) → confidence ~0.5 (requires rule-tag context)

Note: with rule-tag match, team identity is already known — parser only needs to extract score numbers + status keyword.

**`normalize_game_status(text: str) -> GameStatus | None`**
Maps tweet keywords → `GameStatus` enum:
- "final" / "FINAL" / "game over" → `GameStatus.FINAL`
- "halftime" / "half" / "HT" → `GameStatus.HALFTIME`
- "end Q1" / "end of 1st" / "1Q" → `GameStatus.END_1Q`
- "end Q3" / "end of 3rd" / "3Q" → `GameStatus.END_3Q`
- "OT final" / "overtime final" → `GameStatus.END_OT`
- else → `GameStatus.IN_PROGRESS`

### `backend/services/twitter_stream_listener.py`
Long-running service (not a Prefect flow). Entrypoint for the Docker service.

Key logic:
- `should_run_today(today: date) -> tuple[bool, tuple[int, int]]`: Queries DB for games today; returns `(has_games, (start_hour_ct, end_hour_ct))`
- `connect_and_stream(backfill_minutes: int = 0)`: Opens `GET /2/tweets/search/stream`, yields tweet dicts
- Main loop: check schedule → sleep if no games / outside window → stream → reconnect with backoff on disconnect
- Dedup guard: relies on `game_score_updates.tweet_id` UNIQUE constraint (insert fails silently on duplicate)

### `backend/prefect/twitter_rules_pipeline.py`
Two short Prefect flows for rule lifecycle management.

**`setup_game_rules_flow(game_date: date | None = None) -> int`**
- `fetch_todays_games_task()`: SELECT from `games_effective` where date = today
- `build_rules_task(games, alias_config)`: Generate rule text + tag per matchup from alias config
- `create_stream_rules_task(rules)`: POST `/2/tweets/search/stream/rules`

**`teardown_game_rules_flow() -> int`**
- `fetch_game_rule_ids_task()`: GET rules, filter those tagged with `school=|date=` pattern
- `delete_stream_rules_task(ids)`: DELETE from rules API

---

## Files to Modify

### `sql/init.sql`
Add after the `games` table definition:

```sql
CREATE TABLE IF NOT EXISTS game_score_updates (
    id              SERIAL PRIMARY KEY,
    tweet_id        TEXT NOT NULL UNIQUE,
    school          TEXT,
    game_date       DATE,
    raw_text        TEXT NOT NULL,
    parsed_score    JSONB,
    rule_tag        TEXT,
    applied         BOOLEAN NOT NULL DEFAULT FALSE,
    confidence      FLOAT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_game_score_updates_tweet_id ON game_score_updates (tweet_id);
CREATE INDEX IF NOT EXISTS idx_game_score_updates_game_date ON game_score_updates (game_date);
```

### `backend/prefect/flows.py`
Register rule management flows (run daily — they self-check whether games exist today):

```python
from backend.prefect.twitter_rules_pipeline import setup_game_rules_flow, teardown_game_rules_flow
# inside serve():
await setup_game_rules_flow.to_deployment(
    "twitter-rules-setup",
    cron="0 15 * * *",   # 3pm CT daily (runs, checks if games today, exits if not)
),
await teardown_game_rules_flow.to_deployment(
    "twitter-rules-teardown",
    cron="0 8 * * *",    # 8am CT daily (cleans up previous day's rules)
),
```

### `docker-compose.yml`
Add new service for the stream listener:

```yaml
twitter-stream:
  build:
    context: .
    dockerfile: backend/Dockerfile
  command: python -m backend.services.twitter_stream_listener
  env_file: .env.local
  restart: unless-stopped
  depends_on:
    - db
```

---

## Environment Variables

Add to `.env.local` and Docker env:
```
X_BEARER_TOKEN=<X API v2 app-only Bearer token>
X_SCORE_HASHTAG=#MHSAAScore
SCORE_CONFIDENCE_THRESHOLD=0.60
TWITTER_CHAMPIONSHIP_ROUNDS=State Championship,State Finals,State Semifinals
```

---

## Upsert Rules

1. **Never overwrite `final=TRUE`** — finals are authoritative; no tweet can downgrade them
2. **Apply only if `confidence >= SCORE_CONFIDENCE_THRESHOLD`**
3. **Upsert both school-perspective rows**: update `(school_a, date)` and `(school_b, date)` rows
4. **Derive `result`** from score comparison (only when `game_status=FINAL`)

---

## Files to Create (Tests)

### `backend/tests/twitter_parser_test.py`
All offline — no API access needed.

- `"#MHSAAScore Madison Central 24 Clinton 17 Final"` → confidence ≥ 0.9, status=FINAL
- `"Madison Central leads Clinton 24-17 end Q3"` → confidence ≥ 0.65, status=END_3Q
- `"Great game tonight! Go Eagles!"` → None
- `"21-17"` (score only) → confidence ~0.5, status=IN_PROGRESS
- `"OT FINAL: Madison Central 31 Clinton 28"` → status=END_OT
- All `normalize_game_status()` keyword variants
- Alias config: verify ambiguous schools have `ambiguous: true`; verify no ambiguous-named school's rule includes the bare ambiguous name

---

## Verification

1. **Unit tests**: `source .venv/bin/activate && cd backend && pytest tests/twitter_parser_test.py -vv`
2. **Rule setup dry-run**: Run `setup_game_rules_flow(game_date=<known past game date>)` → verify rules created via `GET /2/tweets/search/stream/rules`; run teardown → verify deleted
3. **Alias config sanity**: Script that prints generated rule text for each school — manual review of ambiguous schools
4. **Stream smoke test**: Create a test rule matching a hashtag you control; start the Docker service; post a tweet; confirm it arrives in `game_score_updates` with correct parsed score
5. **Dedup**: Send duplicate tweet payloads; confirm second insert fails silently on UNIQUE constraint
6. **Non-game-day**: Start service on a day with no DB games; confirm it sleeps and doesn't connect
