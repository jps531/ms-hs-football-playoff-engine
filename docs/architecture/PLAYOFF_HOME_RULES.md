# MHSAA Playoff Home-Site Rules

Raw MHSAA rule text describing which team hosts each playoff round. These rules aren't in the handbook; they come from MHSAA's [football playoff home team instructions](https://www.misshsaa.com/2026/10/20/football-playoff-home-team-instructions-2/) (October 2026), which the About page also cites. Seeds referenced here come from the region tiebreaker procedure in [SCENARIO_RULES.md](SCENARIO_RULES.md); see [SCENARIO_COMPUTATION.md](SCENARIO_COMPUTATION.md) for how the engine turns these rules into the `hosting`/`home_game_odds` fields served by the API.

When two teams from the same region meet in the football playoffs, the higher seed will always be the home team, no matter what round.

1. First round (and second round for 1A-4A) – higher seed hosts.

2. Quarterfinals – If both teams have played an equal number of home matches the home site will be determined by the highest seeded team. If equally seeded teams play and #2 cannot determine a home site, in odd years, the LOWER numbered region will host and in even years, the HIGHER numbered region will host.

3. North/South Championships (Semifinals) – highest seed hosts. If equally seeded teams, in odds [sic] years, the LOWER numbered region will host and in even years, the HIGHER numbered region will host.

4. State Championships South team will be home in odd years, North will be home in even years.
