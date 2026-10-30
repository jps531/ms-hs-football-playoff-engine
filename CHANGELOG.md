# Changelog

What changed in each version of [mshsfootball.com](https://mshsfootball.com). The version live on the
site is in every page's footer. Versions are MAJOR.MINOR.PATCH: MAJOR for a change in what the site is,
MINOR for a new feature or a change in how the numbers are worked out, PATCH for a fix
([CONTRIBUTING.md](CONTRIBUTING.md#releases)).

## 1.1.0

- **Report a game's final score.** A region game from today or earlier that has no score yet has a
  “Report score” button, next to the “Wrong score?” one on finished games. A moderator checks the
  score, and once it's approved, the next update of the standings, odds and scenarios counts the game
  as played for both teams.
- **Corrections reach past weeks, and quickly.** Once moderators have stopped approving corrections
  for 10 minutes, the standings, odds and scenarios are worked out again from the earliest date the
  corrections change, past weeks included. Before, a correction waited for the next morning's update,
  and past weeks kept the old numbers.
- **Report a game's right date.** Every region game with a date has a “Wrong date?” button. Once a
  moderator approves the report, the game moves to that date for both teams.

## 1.0.2

- **Scenarios a tie's margins decide are listed one by one.** When one set of results in a region's
  last games leaves a tie the winning margins can order nine to twelve different ways, each of
  which can be put in margins, its card said only that the tiebreaker decides it. Now each order is its own card with the margins that
  give it: a range ("by 1–3") or, where it needs one, a comparison of two games' margins ("McAdams
  wins by at least 3 more points than Sebastopol"). Region 5-1A's last week is one. A card that
  named the tiebreaker steps behind its order also says the margins instead, where that's short.

## 1.0.1

- **A game the two schools' schedules date a day apart now counts once.** Some games are dated a day
  apart on the two schools' schedules (Falkner–H. W. Byers, for one). Such a game counted twice in the
  Elo ratings behind the Projected odds, and twice in the point differential and points allowed that
  the tiebreakers use. On a past week dated between the two days, it counted for one of the two
  teams and not the other. Each game now has one date, the later of the two, everywhere a date
  decides what has been played. A rematch, like a playoff game between region opponents, is still a
  game of its own.

## 1.0.0

The first public release: standings, playoff odds and scenarios for every MHSAA region in classes 1A–7A.

- **Standings and seeding odds** for every region, updated each morning from the previous night's
  scores, in two kinds: Toss-up (every remaining game a coin flip) and Projected (weighted by the
  teams' Elo ratings).
- **Scenarios** once a region has five or fewer games left: every way it can finish, what makes each
  happen, margins included, and why the tiebreaker orders each tie as it does, step by step.
- **Team paths** with ten or fewer games left: for each team, the results that give it each seed, a
  playoff spot, or elimination.
- **Key insights** with six to ten games left, where the full scenario list isn't shown: the results
  that clinch a seed or eliminate a team.
- **Playoff brackets** with each team's odds of reaching each round and of hosting.
- **Past weeks**: any game date's standings and odds as they stood then, for the 2025 and 2026 seasons.
- **Ties in finished standings** explained with the actual results.
- **Feedback and reader submissions** (score corrections, logos, helmets, colors and locations),
  reviewed before they're used.
