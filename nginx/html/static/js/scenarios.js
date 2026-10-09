// Turns the API's per-team paths and key insights into the outcome cards the
// region view shows. Pure data shaping, no DOM, so it runs under `node --test`.

import { ordinalWord, joinNames } from "./format.js";

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
  const toGroup = (i) => i.conditions.map((c) => ({
    type: "game_result", school: c.winner, opponent: c.loser, required_result: "win",
    min_margin: c.min_margin, max_margin: c.max_margin,
  }));
  // Several insights can prove the same outcome different ways; each one is
  // enough on its own, so they become one card with the ways joined by OR.
  const cards = new Map();
  (insights ?? [])
    .filter((i) => i.conditions?.length && titleFor(i))
    .sort((a, b) => rank[a.insight_type] - rank[b.insight_type] || (a.seed ?? 9) - (b.seed ?? 9))
    .forEach((i) => {
      const key = `${i.insight_type}|${i.team}|${i.seed ?? ""}`;
      if (!cards.has(key)) cards.set(key, { team: i.team, title: titleFor(i), p: null, groups: [] });
      cards.get(key).groups.push(toGroup(i));
    });
  return [...cards.values()];
}

/**
 * The region's complete scenarios — every distinct way the standings can
 * finish — as cards: { label, seeds: [{ seed, team }], out, groups },
 * numbered in order with duplicates removed.
 * `seeds` are the playoff seeds (1-4), `out` the rest in finishing order,
 * and `groups` is one AND-group of conditions in the chip format. Game
 * results become team chips; margin and point-differential conditions keep
 * the API's wording (its title joins the same conditions with " AND ").
 */
export function completeScenarioCards(scenarios, playoffSeeds = 4) {
  const cards = (scenarios ?? []).map((sc) => {
    const phrases = (sc.title ?? "").split(" AND ");
    const source = sc.conditions?.length
      ? sc.conditions
      : (sc.game_winners ?? []).map((g) => ({ type: "game_result", winner: g.winner, loser: g.loser, min_margin: 1, max_margin: null }));
    const conditions = source.map((c, i) => (c.type === "game_result"
      ? {
        type: "game_result", school: c.winner, opponent: c.loser, required_result: "win",
        min_margin: c.min_margin ?? 1, max_margin: c.max_margin ?? null,
      }
      : { type: "text", description: phrases[i] ?? "" }));
    for (const group of sc.coinflip_groups ?? []) {
      if (group.length > 1) conditions.push({ type: "coin_flip", description: `A coin flip settles the tie ${group.length === 2 ? "between" : "among"} ${joinNames(group)}` });
    }
    const order = Object.entries(sc.outcomes ?? {})
      .map(([team, seed]) => ({ team, seed: Number(seed) }))
      .sort((a, b) => a.seed - b.seed);
    return {
      label: `Scenario ${sc.scenario_num}${(sc.sub_label ?? "").toUpperCase()}`,
      seeds: order.filter((o) => o.seed <= playoffSeeds),
      out: order.filter((o) => o.seed > playoffSeeds).map((o) => o.team),
      groups: conditions.length ? [conditions] : [],
      num: sc.scenario_num,
    };
  });
  return renumber(dedupe(cards));
}

/**
 * Drop scenarios that read the same as an earlier one. The API can split
 * one scenario over a game that changes nothing (its conditions leave that
 * game out), which would show two identical boxes.
 */
function dedupe(cards) {
  const seen = new Set();
  return cards.filter((c) => {
    const key = JSON.stringify([c.seeds, c.out, c.groups]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Number what's left 1, 2, 3…, lettering a scenario's variants A, B, and so on. */
function renumber(cards) {
  const groups = [];
  for (const c of cards) {
    const last = groups[groups.length - 1];
    if (last && last[0].num === c.num) last.push(c);
    else groups.push([c]);
  }
  return groups.flatMap((group, i) => group.map(({ num, ...c }, k) => ({
    ...c,
    label: `Scenario ${i + 1}${group.length > 1 ? String.fromCharCode(65 + k) : ""}`,
  })));
}
