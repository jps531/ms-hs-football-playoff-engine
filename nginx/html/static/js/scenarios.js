// Turns the API's per-team paths and key insights into the outcome cards the
// region view shows. Pure data shaping, no DOM, so it runs under `node --test`.

import { joinNames } from "./format.js";

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
        groups.playoffs.push(card(`${t.school} makes the playoffs as the #${onlySeed} seed`, playoffs));
      }
      // A lone path to #1 is already the title card.
    }
    if (onlySeed !== null) continue;
    for (const p of conditionalSeeds) {
      if (p.outcome.value !== 1) {
        groups.seeding.push(card(`${t.school} finishes as the #${p.outcome.value} seed`, p));
      }
    }
  }
  for (const list of Object.values(groups)) list.sort((a, b) => b.p - a.p);
  return groups;
}

/** Key insights (one guaranteed path each) as cards, for 6-10 games left. */
export function insightCards(insights) {
  const titleFor = (i) => {
    if (i.insight_type === "clinch_seed") {
      return i.seed === 1 ? `${i.team} clinches the region` : `${i.team} clinches the #${i.seed} seed`;
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

/** What decides a tie a scenario leaves open, by the step it's left from. */
export const OPEN_TIE_NOTES = {
  3: "Order decided by the tiebreaker: point differential, then fewest points allowed",
  5: "Order decided by fewest total points allowed in region games. Teams that remain tied start the tiebreakers over among themselves, and a coin flip decides if they're tied on every other tiebreaker.",
  6: "Order decided by a coin flip",
};

/**
 * The region's complete scenarios — every distinct way the standings can
 * finish — as cards: { label, seeds, out, common, groups, p, pWeighted }, one
 * card per finish, numbered in order. The API can list one finish more than
 * once (different results reaching the same standings); those become one card
 * whose ways are joined by OR, with the finish's chance (Toss-up `p`,
 * Projected `pWeighted`; null when the snapshot has none).
 * `seeds` are the playoff seeds (1-4) as { seed, team }, except a tie the
 * scenario leaves to the tiebreaker, which is one { seed: "2–4", teams, note }
 * row over its places: its order isn't stated, so it isn't shown. `out` is the
 * rest (with "the rest of the tie" when one straddles the cutoff). `groups`
 * is the scenario's conditions in the chip format: one AND-group, or several
 * joined by OR when different results lead to the same outcome, with what they
 * all share pulled out into `common`. Game results become team chips; other
 * conditions keep the API's wording.
 */
export function completeScenarioCards(scenarios, playoffSeeds = 4) {
  const cards = (scenarios ?? []).map((sc) => {
    const phrases = (sc.title ?? "").split(" AND ");
    const winners = (sc.game_winners ?? []).map((g) => ({ type: "game_result", winner: g.winner, loser: g.loser, min_margin: 1, max_margin: null }));
    const sources = sc.condition_groups?.length ? sc.condition_groups : [sc.conditions?.length ? sc.conditions : winners];
    const chip = (c, i) => (c.type === "game_result"
      ? {
        type: "game_result", school: c.winner, opponent: c.loser, required_result: "win",
        min_margin: c.min_margin ?? 1, max_margin: c.max_margin ?? null,
      }
      // Older snapshots carry no description; their title then lines up with a single group.
      : { type: "text", description: c.description ?? phrases[i] ?? "" });
    const groups = sources.map((source) => source.map(chip)).filter((g) => g.length);
    for (const group of sc.coinflip_groups ?? []) {
      if (group.length > 1) {
        const flip = { type: "coin_flip", description: `A coin flip settles the tie ${group.length === 2 ? "between" : "among"} ${joinNames(group)}` };
        if (groups.length) groups.forEach((g) => g.push(flip));
        else groups.push([flip]);
      }
    }
    const order = Object.entries(sc.outcomes ?? {})
      .map(([team, seed]) => ({ team, seed: Number(seed) }))
      .sort((a, b) => a.seed - b.seed);
    const ties = (sc.open_groups ?? []).map((g) => ({ ...g, members: new Set(g.teams) }));
    const seeds = [];
    const inTie = new Set();
    for (const o of order.filter((x) => x.seed <= playoffSeeds)) {
      const tie = ties.find((t) => t.members.has(o.team));
      if (!tie) {
        seeds.push(o);
        continue;
      }
      if (inTie.has(tie)) continue;
      inTie.add(tie);
      const places = order.filter((x) => tie.members.has(x.team) && x.seed <= playoffSeeds).map((x) => x.seed);
      const first = places[0];
      const last = places[places.length - 1];
      const shared = places.length < tie.teams.length;
      seeds.push({
        seed: first === last ? String(first) : `${first}–${last}`,
        teams: tie.teams,
        note: (shared ? `${places.length} of these ${tie.teams.length} make the playoffs. ` : "") + (OPEN_TIE_NOTES[tie.step] ?? OPEN_TIE_NOTES[3]),
      });
    }
    const straddle = ties.some((t) => order.some((x) => t.members.has(x.team) && x.seed > playoffSeeds));
    const out = order.filter((o) => o.seed > playoffSeeds && !ties.some((t) => t.members.has(o.team))).map((o) => o.team);
    return {
      seeds, out: straddle ? [...out, "the rest of the tie"] : out, ways: groups, p: sc.p ?? null, pWeighted: sc.p_weighted ?? null,
      why: whyBlocks(sc.explanation),
    };
  });
  return byFinish(cards).map((c, i) => ({ ...c, label: `Scenario ${i + 1}` }));
}

/** The margins a game-result chip allows, as [lo, hi] (hi null for unbounded). */
const marginsOf = (c) => [c.min_margin ?? 1, c.max_margin ?? null];

/** True when every condition of way `v` holds whenever way `w`'s do: `v` covers `w`. */
function covers(v, w) {
  return v.every((x) => w.some((y) => {
    if (x.type !== "game_result" || y.type !== "game_result") return JSON.stringify(x) === JSON.stringify(y);
    if (x.school !== y.school || x.opponent !== y.opponent || x.required_result !== y.required_result) return false;
    const [xlo, xhi] = marginsOf(x);
    const [ylo, yhi] = marginsOf(y);
    return xlo <= ylo && (xhi === null || (yhi !== null && yhi <= xhi));
  }));
}

/**
 * One card per finish, in order of first appearance: the ways to it from
 * every scenario that reaches it, each once, joined by OR, with what every
 * way shares said once (`common`).
 */
function byFinish(cards) {
  const key = (c) => JSON.stringify(c);
  const finishes = new Map();
  for (const c of cards) {
    const finish = JSON.stringify([c.seeds, c.out]);
    const seen = finishes.get(finish);
    if (!seen) finishes.set(finish, { ...c, ways: [...c.ways] });
    else for (const w of c.ways) if (!seen.ways.some((x) => key(x) === key(w))) seen.ways.push(w);
  }
  return [...finishes.values()].map(({ ways: listed, ...c }) => {
    // A way another way already covers adds nothing ("B beats A by 9+" beside "B beats A").
    const ways = listed.filter((w, i) => !listed.some((v, j) => j !== i && covers(v, w) && (!covers(w, v) || j < i)));
    const common = ways.length > 1 ? ways[0].filter((x) => ways.every((w) => w.some((y) => key(y) === key(x)))) : [];
    const shared = new Set(common.map(key));
    return { ...c, common, groups: common.length ? ways.map((w) => w.filter((x) => !shared.has(key(x)))) : ways };
  });
}

/** 1 → "1st", 2 → "2nd", 11 → "11th". */
function ordinal(n) {
  const suffix = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th");
  return `${n}${suffix}`;
}

/**
 * A scenario's "why this order", from the API's `explanation` (one entry per
 * tie reaching the playoff places): [{ title, when, steps }], where `title`
 * is "Tupelo Christian and Smithville, tied for 1st and 2nd", `when` the
 * results that pick the entry out among this finish's ("If Thrasher beats
 * Biggersville", or null when it holds whichever way the finish comes
 * about) and `steps` the sentences. Empty for a snapshot without them.
 */
export function whyBlocks(explanation) {
  return (explanation ?? []).map((e) => {
    const first = ordinal(e.places[0]);
    const last = ordinal(e.places[e.places.length - 1]);
    const where = e.places.length === 2 ? `${first} and ${last}` : `${first}–${last}`;
    const results = (e.when ?? []).map((cube) => cube.map((g) => `${g.winner} beats ${g.loser}`).join(" and "));
    return {
      title: `${joinNames(e.teams)}, tied for ${where}`,
      when: results.length ? `If ${results.join(", or ")}` : null,
      steps: e.steps,
    };
  });
}
