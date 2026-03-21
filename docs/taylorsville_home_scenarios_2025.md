# Taylorsville — 2025 Playoff Home-Game Scenarios

**Class:** 1A
**Region:** 8
**Seed:** #1
**Bracket half:** South

> Snapshot: bracket set, no games played yet.  All odds assume equal (50/50)
> win probability for every game.

---

## Odds summary

| Round | Reach round | Host \| reach (conditional) | Host AND reach (marginal) |
|---|---|---|---|
| First Round | 100.0% | 100.0% | 100.0% |
| Second Round | 50.0% | 100.0% | 50.0% |
| Quarterfinals | 25.0% | 37.5% | 9.4% |
| Semifinals | 12.5% | 75.0% | 9.4% |

**Stored in DB:** the "Reach" and "Host \| reach" columns.
**Derivable on the fly:** Marginal = Reach × (Host \| reach).

---

## Human-readable scenarios

The percentages shown inline are the **marginal** odds (reach AND host).

```
Taylorsville

Will Host First Round (100.0%):  [Designated home team in bracket]

Will Host Second Round (50.0%):
1. Taylorsville advances to Second Round
   [Higher seed (#1) hosts]

Will Host Quarterfinals (9.4%):
1. Taylorsville advances to Quarterfinals
2. Richton advances to Quarterfinals
   [Same-region game — higher seed (#1) hosts]

1. Taylorsville advances to Quarterfinals
2. Richton advances to Second Round
3. Leake County advances to Quarterfinals
   [Higher seed (#1) hosts]

Will Not Host Quarterfinals (90.6%):
1. Taylorsville advances to Quarterfinals
2. Bogue Chitto advances to Quarterfinals
   [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 7)]

1. Taylorsville advances to Quarterfinals
2. Bogue Chitto advances to Second Round
3. Leake County advances to Quarterfinals
   [Fewer home games played (1 vs 2) — opponent hosts]

1. Taylorsville advances to Quarterfinals
2. Shaw advances to Quarterfinals
   [Fewer home games played (0 vs 2) — opponent hosts]

Will Host Semifinals (9.4%):
1. Taylorsville advances to Semifinals
2. West Bolivar advances to Semifinals
   [Higher seed (#1) hosts]

1. Taylorsville advances to Semifinals
2. Salem advances to Semifinals
   [Higher seed (#1) hosts]

1. Taylorsville advances to Semifinals
2. Lumberton advances to Semifinals
   [Same-region game — higher seed (#1) hosts]

1. Taylorsville advances to Semifinals
2. Noxapater advances to Semifinals
   [Higher seed (#1) hosts]

1. Taylorsville advances to Semifinals
2. Stringer advances to Semifinals
   [Same-region game — higher seed (#1) hosts]

1. Taylorsville advances to Semifinals
2. Mount Olive advances to Semifinals
   [Higher seed (#1) hosts]

Will Not Host Semifinals (90.6%):
1. Taylorsville advances to Semifinals
2. Nanih Waiya advances to Semifinals
   [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 5)]

1. Taylorsville advances to Semifinals
2. Simmons advances to Semifinals
   [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 6)]
```

---

## Matchup list (opponent-centric view)

`enumerate_team_matchups` / `render_team_matchups` / `team_matchups_as_dict`
produce an opponent-centric view: one line (or dict entry) per possible
`(opponent, home/away)` combination.  The percentage on each line is the
**per-matchup conditional probability** — given Taylorsville reaches that
round, the chance of facing that specific opponent in that home/away
configuration.

> Note: Leake County appears **twice** in the Quarterfinals — once as home
> (16.7%) and once as away (16.7%).  This reflects the R2-path ambiguity:
> if Richton won R1 then Leake County hosted R2 (2 home games entering QF →
> Taylorsville's equal home-game count wins the seed tiebreak and hosts);
> if Bogue Chitto won R1 then Leake County was away in R2 (1 home game →
> Leake County has fewer and hosts).  Shaw (R6 #3) has 2 paths that both
> lead to the same away outcome, giving it a 33.3% (2/6) share.

### Text rendering

```
Taylorsville

First Round (100.0%):
  Region 7 #4 West Lincoln at Taylorsville (100.0%)  [Designated home team in bracket]

Second Round (50.0%):
  Region 5 #3 Ethel at Taylorsville (50.0%)  [Higher seed (#1) hosts]
  Region 6 #2 South Delta at Taylorsville (50.0%)  [Higher seed (#1) hosts]

Quarterfinals (25.0%):
  Region 5 #2 Leake County at Taylorsville (16.7%)  [Higher seed (#1) hosts]
  Region 8 #4 Richton at Taylorsville (16.7%)  [Same-region game — higher seed (#1) hosts]
  Taylorsville at Region 5 #2 Leake County (16.7%)  [Fewer home games played (1 vs 2) — opponent hosts]
  Taylorsville at Region 6 #3 Shaw (33.3%)  [Fewer home games played (1 vs 2) — opponent hosts]
  Taylorsville at Region 7 #1 Bogue Chitto (16.7%)  [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 7)]

Semifinals (12.5%):
  Region 5 #4 Noxapater at Taylorsville (12.5%)  [Higher seed (#1) hosts]
  Region 6 #4 West Bolivar at Taylorsville (12.5%)  [Higher seed (#1) hosts]
  Region 7 #2 Salem at Taylorsville (12.5%)  [Higher seed (#1) hosts]
  Region 7 #3 Mount Olive at Taylorsville (12.5%)  [Higher seed (#1) hosts]
  Region 8 #2 Stringer at Taylorsville (12.5%)  [Same-region game — higher seed (#1) hosts]
  Region 8 #3 Lumberton at Taylorsville (12.5%)  [Same-region game — higher seed (#1) hosts]
  Taylorsville at Region 5 #1 Nanih Waiya (12.5%)  [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 5)]
  Taylorsville at Region 6 #1 Simmons (12.5%)  [Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 6)]
```

### Dict rendering (JSON)

```json
{
  "first_round": {
    "p_reach": 1.0,
    "p_host_conditional": 1.0,
    "p_host_marginal": 1.0,
    "p_reach_weighted": null,
    "p_host_conditional_weighted": null,
    "p_host_marginal_weighted": null,
    "matchups": [
      {
        "opponent": "West Lincoln",
        "opponent_region": 7,
        "opponent_seed": 4,
        "home": true,
        "p_conditional": 1.0,
        "p_conditional_weighted": null,
        "p_marginal": 1.0,
        "p_marginal_weighted": null,
        "explanation": "Designated home team in bracket"
      }
    ]
  },
  "second_round": {
    "p_reach": 0.5,
    "p_host_conditional": 1.0,
    "p_host_marginal": 0.5,
    "p_reach_weighted": null,
    "p_host_conditional_weighted": null,
    "p_host_marginal_weighted": null,
    "matchups": [
      {
        "opponent": "Ethel",
        "opponent_region": 5,
        "opponent_seed": 3,
        "home": true,
        "p_conditional": 0.5,
        "p_conditional_weighted": null,
        "p_marginal": 0.25,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "South Delta",
        "opponent_region": 6,
        "opponent_seed": 2,
        "home": true,
        "p_conditional": 0.5,
        "p_conditional_weighted": null,
        "p_marginal": 0.25,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      }
    ]
  },
  "quarterfinals": {
    "p_reach": 0.25,
    "p_host_conditional": 0.375,
    "p_host_marginal": 0.09375,
    "p_reach_weighted": null,
    "p_host_conditional_weighted": null,
    "p_host_marginal_weighted": null,
    "matchups": [
      {
        "opponent": "Leake County",
        "opponent_region": 5,
        "opponent_seed": 2,
        "home": true,
        "p_conditional": 0.16666666666666666,
        "p_conditional_weighted": null,
        "p_marginal": 0.041666666666666664,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "Richton",
        "opponent_region": 8,
        "opponent_seed": 4,
        "home": true,
        "p_conditional": 0.16666666666666666,
        "p_conditional_weighted": null,
        "p_marginal": 0.041666666666666664,
        "p_marginal_weighted": null,
        "explanation": "Same-region game — higher seed (#1) hosts"
      },
      {
        "opponent": "Leake County",
        "opponent_region": 5,
        "opponent_seed": 2,
        "home": false,
        "p_conditional": 0.16666666666666666,
        "p_conditional_weighted": null,
        "p_marginal": 0.041666666666666664,
        "p_marginal_weighted": null,
        "explanation": "Fewer home games played (1 vs 2) — opponent hosts"
      },
      {
        "opponent": "Shaw",
        "opponent_region": 6,
        "opponent_seed": 3,
        "home": false,
        "p_conditional": 0.3333333333333333,
        "p_conditional_weighted": null,
        "p_marginal": 0.08333333333333333,
        "p_marginal_weighted": null,
        "explanation": "Fewer home games played (1 vs 2) — opponent hosts"
      },
      {
        "opponent": "Bogue Chitto",
        "opponent_region": 7,
        "opponent_seed": 1,
        "home": false,
        "p_conditional": 0.16666666666666666,
        "p_conditional_weighted": null,
        "p_marginal": 0.041666666666666664,
        "p_marginal_weighted": null,
        "explanation": "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 7)"
      }
    ]
  },
  "semifinals": {
    "p_reach": 0.125,
    "p_host_conditional": 0.75,
    "p_host_marginal": 0.09375,
    "p_reach_weighted": null,
    "p_host_conditional_weighted": null,
    "p_host_marginal_weighted": null,
    "matchups": [
      {
        "opponent": "Noxapater",
        "opponent_region": 5,
        "opponent_seed": 4,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "West Bolivar",
        "opponent_region": 6,
        "opponent_seed": 4,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "Salem",
        "opponent_region": 7,
        "opponent_seed": 2,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "Mount Olive",
        "opponent_region": 7,
        "opponent_seed": 3,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Higher seed (#1) hosts"
      },
      {
        "opponent": "Stringer",
        "opponent_region": 8,
        "opponent_seed": 2,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Same-region game — higher seed (#1) hosts"
      },
      {
        "opponent": "Lumberton",
        "opponent_region": 8,
        "opponent_seed": 3,
        "home": true,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Same-region game — higher seed (#1) hosts"
      },
      {
        "opponent": "Nanih Waiya",
        "opponent_region": 5,
        "opponent_seed": 1,
        "home": false,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 5)"
      },
      {
        "opponent": "Simmons",
        "opponent_region": 6,
        "opponent_seed": 1,
        "home": false,
        "p_conditional": 0.125,
        "p_conditional_weighted": null,
        "p_marginal": 0.015625,
        "p_marginal_weighted": null,
        "explanation": "Equal seed (#1) — region tiebreak: odd year, lower region# hosts (Region 6)"
      }
    ]
  }
}
```

---

## Notes

### Reading the output

- **Numbered lists** within a section use AND logic — all listed conditions must
  hold for that outcome to apply.
- **Blank lines** between numbered groups represent OR paths — any one group
  being true is sufficient.
- **Bracketed text** `[…]` is the rule explanation for that path.
- **"X advances to Second Round"** inside a QF scenario is an intermediate
  condition indicating which team won the First Round in a neighboring bracket
  slot, which determines the QF opponent's home-game history.

### First Round

Taylorsville is the designated home team by bracket assignment; no conditions
apply.  Conditional = 100% (always home if they made the playoffs).

### Second Round

As the #1 seed Taylorsville always hosts whoever advances from the adjacent
slot (South Delta or Ethel), so conditional = 100%.  Marginal = 50% because
they must first win R1.

### Quarterfinals

The QF opponent pool is four teams — two seeds each from Regions 5–6 and
Regions 7–8 (the other South quarter).  The home-game count rule means the
result can depend on which path a QF opponent took through the Second Round:

| Opponent | R2 path | Taylorsville games | Opponent games | Outcome |
|---|---|---|---|---|
| Richton (R8 #4) | — | 2 | 0 | **Taylorsville hosts** (same-region, higher seed) |
| Leake County (R5 #2) | **Richton wins R1** → LC hosts R2 | 2 | 2 | **Taylorsville hosts** (#1 seed tiebreak) |
| Leake County (R5 #2) | **Bogue Chitto wins R1** → LC away in R2 | 2 | 1 | **Leake County hosts** (fewer home games) |
| Bogue Chitto (R7 #1) | — | 2 | 2 | **Bogue Chitto hosts** (equal seeds — odd year, Region 7 < Region 8) |
| Shaw (R6 #3) | either path | 2 | 0–1 | **Shaw hosts** (fewer home games either way) |

Taylorsville hosts 2 of the 4 possible QF opponents (in 3 of 8 equally-likely
bracket paths) → conditional = 3/8 = 37.5%.  Marginal = 25% × 37.5% = 9.4%.

**2025 actual result:** Bogue Chitto beat Richton in R1; Leake County beat
Bogue Chitto in R2 (1 home game entering QF vs Taylorsville's 2).  Leake
County hosted — consistent with the "Will Not Host" path above.

### Semifinals (North/South Championship)

The SF is an intra-half game.  All 8 South-half teams from the opposing quarter
(Regions 5–6, seeds 1–4) are possible opponents.  Taylorsville hosts 6 of the 8
(75% conditional).  It is away against Nanih Waiya (R5 #1) and Simmons (R6 #1)
because those are equal #1 seeds and the odd-year tiebreak gives home to the
lower region number.

Marginal = 12.5% × 75% = 9.4%.

**2025 actual result:** Simmons (Region 6 #1) hosted Taylorsville —
consistent with the "Will Not Host" grouping above.
