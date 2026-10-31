# Changelog

What changed in each version of [mshsfootball.com](https://mshsfootball.com). The version live on the
site is in every page's footer. Versions are MAJOR.MINOR.PATCH: MAJOR for a change in what the site is,
MINOR for a new feature or a change in how the numbers are worked out, PATCH for a fix
([CONTRIBUTING.md](CONTRIBUTING.md#releases)).

## 1.4.0

- **A playoff path reads in order.** A team's “How?” for a later playoff game now lists the
  regular-season results its seed needs first, then the playoff games it has to win. Before, the
  playoff games could come first.
- **What it takes for a later playoff matchup, and who hosts it.** Each possible matchup in a
  second-round or later game now has a “How?” too: the seeds that lead both teams there, with what
  each takes, then each playoff game they have to win. When either team could host, it's split into
  “Noxubee County hosts IF” and “Thomas E. Edwards hosts IF”, following the MHSAA's hosting rules;
  in a quarterfinal that can come down to whom a team beat in the second round, which it then names.

## 1.3.0

- **What it takes to reach any playoff game.** Every team listed in a later playoff game on a bracket
  now has a “How?” too: the seed or seeds that lead there, with what each one takes, and each playoff
  game it has to win on the way, naming the opponent once it's known. Games it has already won drop
  out, and a bye needs no win. The team you've picked opens on its own, on either side of the game.

## 1.2.0

- **What it takes to reach a first-round playoff game.** In a first-round game on a bracket, each
  team that could play there, and each possible matchup, has a “How?” that opens what has to happen:
  the same conditions the region's page lists for that seed, and for a matchup, both teams' at once.
  The team you've picked opens on its own. Until a region has five or fewer region games left, it shows the
  results that would settle the spot, if there are any, and links to the region.
- **A tidier game sheet.** Its teams and matchups are separated by lines, and “Possible matchups” is
  a section header.

## 1.1.2

- **A bye reads as a bye.** When a region has only three teams, the team that would have played its
  #4 seed in the first round gets a bye. The bracket now shows “BYE” there, and the game's sheet
  says why: “There is no Region 1 #4 Seed, so Calhoun City gets a bye.” Before, it showed “No team
  can get here” and said that so many teams could still meet there that no matchup had even a 0.5%
  chance, which wasn't true.

## 1.1.1

- **Another class keeps your week.** Switching class on the standings or a bracket stays on the season
  and week you picked: the same calendar week, under that class's name for it (2025's “Second Round”
  in 1A–4A is “First Round” in 5A–7A). If that class didn't play that week, it shows the closest
  earlier week it did. Before, it went back to the latest week.
- **Each class remembers its team.** A team you pick in a class stays picked there for the rest of
  your visit: look at other classes, and it's there again when you come back, on the class's standings
  and its bracket. A team picked in one class doesn't affect another. “Show every team”, or picking the
  team again, clears it. The class page now marks the picked team's row too. Before, switching class
  cleared the pick.

## 1.1.0

- **Report a game's final score.** A region game from today or earlier that has no score yet has a
  “Report score” button, next to the “Wrong score?” one on finished games. A moderator checks the
  score, and once it's approved, the next update of the standings, odds and scenarios counts the game
  as played for both teams.
- **Corrections reach past weeks, and quickly.** Once moderators have stopped approving corrections
  for 10 minutes, the standings, odds and scenarios are worked out again from the earliest date the
  corrections change, past weeks included. Before, a correction waited for the next morning's update,
  and past weeks kept the old numbers.
- **The morning update appears all at once.** The new scores, standings, odds and scenarios replace
  the old ones together when the whole update is done. Before, the scores showed first and each
  region's numbers as it was worked out. If the update fails partway, the site keeps the previous
  day's numbers whole.
- **Report a playoff game's final score.** On a bracket, a game whose two teams are set and that has
  no result yet has “Already played? Report the final score.” A moderator checks it, adding the game
  for both teams if the schedule doesn't have it yet.
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
