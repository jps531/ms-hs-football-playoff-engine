// Turns the API's per-team paths and key insights into the outcome cards the
// region view shows. Pure data shaping, no DOM, so it runs under `node --test`.

import { ordinalWord } from "./format.js";

const ODDS_KEYS = ["p1", "p2", "p3", "p4", "p_playoffs"];

/**
 * True when the snapshot carries Projected (Elo-weighted) odds. Weighted
 * fields default to 0 when ratings weren't available, and every region has
 * playoff teams, so an all-zero playoff column means "not computed".
 */
export function hasProjectedOdds(teams) {
  return (teams ?? []).some((t) => (t.odds?.p_playoffs_weighted ?? 0) > 0);
}

/** A team's p1-p4 / p_playoffs in the chosen mode ("projected" or "tossup"). */
export function oddsFor(entry, mode) {
  const o = entry.odds ?? {};
  return Object.fromEntries(ODDS_KEYS.map((k) => [k, mode === "projected" ? o[`${k}_weighted`] ?? 0 : o[k]]));
}

/** Probability of one path outcome (seed / playoffs / eliminated) in the chosen mode. */
export function outcomeProbability(entry, outcome, mode) {
  const o = oddsFor(entry, mode);
  if (outcome.type === "seed") return o[`p${outcome.value}`];
  if (outcome.type === "playoffs") return o.p_playoffs;
  return 1 - o.p_playoffs;
}

export function isUnconditional(path) {
  return path.conditions.length === 1 && path.conditions[0].length === 0;
}

/**
 * Turn each team's paths into the meaningful outcome cards, grouped into
 * the title race, the playoff race, and seeding. Unconditional outcomes
 * (already clinched/eliminated) are shown by badges instead.
 *
 * "Makes the playoffs" and "is eliminated" are complements, so a bubble
 * team gets one card for whichever reads simpler: fewer alternative paths
 * (the playoffs path unions every seed and can run to a dozen-plus
 * alternatives where elimination is a single condition).
 */
export function outcomeCards(teamEntries, mode = "tossup") {
  const groups = { title: [], playoffs: [], seeding: [] };
  for (const t of teamEntries) {
    const paths = t.paths ?? [];
    const seedPaths = paths.filter((p) => p.outcome.type === "seed");
    const playoffs = paths.find((p) => p.outcome.type === "playoffs");
    const eliminated = paths.find((p) => p.outcome.type === "eliminated");
    const conditionalSeeds = seedPaths.filter((p) => !isUnconditional(p));
    const card = (title, path) => ({
      team: t.school, title, p: outcomeProbability(t, path.outcome, mode), groups: path.conditions,
    });

    for (const p of conditionalSeeds) {
      if (p.outcome.value === 1) groups.title.push(card(`${t.school} wins the region`, p));
    }
    const bubble = !t.clinched && !t.eliminated && playoffs && !isUnconditional(playoffs);
    const onlySeed = seedPaths.length === 1 ? seedPaths[0].outcome.value : null;
    if (bubble) {
      if (eliminated && eliminated.conditions.length < playoffs.conditions.length) {
        groups.playoffs.push(card(`${t.school} is eliminated`, eliminated));
      } else if (onlySeed === null) {
        groups.playoffs.push(card(`${t.school} makes the playoffs`, playoffs));
      } else if (onlySeed !== 1) {
        groups.playoffs.push(card(`${t.school} makes the playoffs as the No. ${onlySeed} seed`, playoffs));
      }
      // A lone path to #1 is already the title card.
    }
    if (onlySeed !== null) continue;
    for (const p of conditionalSeeds) {
      if (p.outcome.value !== 1) {
        groups.seeding.push(card(`${t.school} finishes ${ordinalWord(p.outcome.value)}`, p));
      }
    }
  }
  for (const list of Object.values(groups)) list.sort((a, b) => b.p - a.p);
  return groups;
}

/** Key insights (one guaranteed path each) as cards, for 7-10 games left. */
export function insightCards(insights) {
  const titleFor = (i) => {
    if (i.insight_type === "clinch_seed") {
      return i.seed === 1 ? `${i.team} clinches the region` : `${i.team} clinches the No. ${i.seed} seed`;
    }
    if (i.insight_type === "clinch_playoffs") return `${i.team} clinches a playoff spot`;
    if (i.insight_type === "eliminated_if") return `${i.team} is eliminated`;
    return null;
  };
  const rank = { clinch_seed: 0, clinch_playoffs: 1, eliminated_if: 2 };
  return (insights ?? [])
    .filter((i) => i.conditions?.length && titleFor(i))
    .sort((a, b) => rank[a.insight_type] - rank[b.insight_type] || (a.seed ?? 9) - (b.seed ?? 9))
    .map((i) => ({
      team: i.team,
      title: titleFor(i),
      p: null,
      groups: [i.conditions.map((c) => ({
        type: "game_result", school: c.winner, opponent: c.loser, required_result: "win",
        min_margin: c.min_margin, max_margin: c.max_margin,
      }))],
    }));
}
