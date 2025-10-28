#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, math, os
from itertools import product
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

try:
    import psycopg
except Exception:
    psycopg = None

def pct_str(x: float) -> str:
    val = x * 100.0
    if abs(val - round(val)) < 1e-9:
        return f"{int(round(val))}%"
    return f"{val:.0f}%".rstrip('0').rstrip('.')

@dataclass(frozen=True)
class CompletedGame:
    a: str; b: str; res_a: int; pd_a: int; pa_a: int; pa_b: int

@dataclass(frozen=True)
class RemainingGame:
    a: str; b: str

def normalize_pair(x: str, y: str) -> Tuple[str, str, int]:
    return (x, y, +1) if x <= y else (y, x, -1)

def fetch_division(conn, clazz: int, region: int, season: int) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school FROM schools WHERE class=%s AND region=%s AND season=%s ORDER BY school",
            (clazz, region, season),
        )
        return [r[0] for r in cur.fetchall()]

def fetch_completed_pairs(conn, teams: List[str], season: int) -> List[CompletedGame]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT school, opponent, result, points_for, points_against FROM games "
            "WHERE season=%s AND final=TRUE AND region_game=TRUE "
            "AND school = ANY(%s) AND opponent = ANY(%s)",
            (season, teams, teams),
        )
        rows = cur.fetchall()
    tmp: Dict[Tuple[str,str], Dict[str,int]] = {}
    for school, opp, result, pf, pa in rows:
        a,b,_ = normalize_pair(school, opp)
        d = tmp.setdefault((a,b), {"res_a": 0, "pd_a": 0, "pa_a": 0, "pa_b": 0})
        res = 1 if result == 'W' and school == a else               -1 if result == 'W' and school == b else               -1 if result == 'L' and school == a else                1 if result == 'L' and school == b else 0
        d["res_a"] += res
        if pf is not None and pa is not None:
            pd = (pf - pa) if school == a else (pa - pf)
            d["pd_a"] += pd
            if school == a:
                d["pa_a"] += pa
            else:
                d["pa_b"] += pa
    out: List[CompletedGame] = []
    for (a,b), v in tmp.items():
        res_a = 1 if v["res_a"] > 0 else (-1 if v["res_a"] < 0 else 0)
        out.append(CompletedGame(a,b,res_a, v["pd_a"], v["pa_a"], v["pa_b"]))
    return out

def fetch_remaining_pairs(conn, teams: List[str], season: int) -> List[RemainingGame]:
    with conn.cursor() as cur:
        cur.execute(
            "WITH cand AS ("
            "  SELECT LEAST(school,opponent) a, GREATEST(school,opponent) b FROM games "
            "  WHERE season=%s AND final=FALSE AND region_game=TRUE "
            "    AND school = ANY(%s) AND opponent = ANY(%s)"
            ") SELECT DISTINCT a,b FROM cand",
            (season, teams, teams),
        )
        return [RemainingGame(a,b) for a,b in cur.fetchall()]

def standings_from_mask(teams, completed, remaining, mask, pa_win, margins, base_margin_default=7):
    wlt = {t: {"w":0, "l":0, "t":0, "pa":0} for t in teams}
    for cg in completed:
        if cg.res_a == 1:
            wlt[cg.a]["w"] += 1; wlt[cg.b]["l"] += 1
        elif cg.res_a == -1:
            wlt[cg.b]["w"] += 1; wlt[cg.a]["l"] += 1
        else:
            wlt[cg.a]["t"] += 1; wlt[cg.b]["t"] += 1
        wlt[cg.a]["pa"] += cg.pa_a; wlt[cg.b]["pa"] += cg.pa_b
    for i, rg in enumerate(remaining):
        bit = (mask >> i) & 1
        winner, loser = (rg.a, rg.b) if bit==1 else (rg.b, rg.a)
        m = margins.get((rg.a, rg.b), base_margin_default)
        wlt[winner]["w"] += 1; wlt[loser]["l"] += 1
        wlt[winner]["pa"] += pa_win; wlt[loser]["pa"] += pa_win + m
    return wlt

def build_h2h_maps(completed, remaining, mask, margins, base_margin_default=7):
    pts = defaultdict(float); pd_cap = defaultdict(int); pd_uncap = defaultdict(int)
    for cg in completed:
        if cg.res_a==1: pts[(cg.a,cg.b)]+=1.0
        elif cg.res_a==-1: pts[(cg.b,cg.a)]+=1.0
        else:
            pts[(cg.a,cg.b)]+=0.5; pts[(cg.b,cg.a)]+=0.5
        cap_a = max(-12, min(12, cg.pd_a))
        pd_cap[(cg.a,cg.b)]+=cap_a; pd_cap[(cg.b,cg.a)]-=cap_a
        pd_uncap[(cg.a,cg.b)]+=cg.pd_a; pd_uncap[(cg.b,cg.a)]-=cg.pd_a
    for i, rg in enumerate(remaining):
        bit=(mask>>i)&1; m=margins.get((rg.a,rg.b),base_margin_default)
        if bit==1:
            pts[(rg.a,rg.b)]+=1.0
            pd_cap[(rg.a,rg.b)]+=min(m,12); pd_cap[(rg.b,rg.a)]-=min(m,12)
            pd_uncap[(rg.a,rg.b)]+=m; pd_uncap[(rg.b,rg.a)]-=m
        else:
            pts[(rg.b,rg.a)]+=1.0
            pd_cap[(rg.a,rg.b)]-=min(m,12); pd_cap[(rg.b,rg.a)]+=min(m,12)
            pd_uncap[(rg.a,rg.b)]-=m; pd_uncap[(rg.b,rg.a)]+=m
    return pts, pd_cap, pd_uncap

def base_bucket_order(teams,wlt):
    def key(s):
        w,l,t=wlt[s]["w"],wlt[s]["l"],wlt[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        return (-wp, l, s)
    return sorted(teams, key=key)

def tie_bucket_groups(teams,wlt):
    buckets=defaultdict(list)
    for s in teams:
        w,l,t=wlt[s]["w"],wlt[s]["l"],wlt[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        buckets[(round(wp,6),l)].append(s)
    order=base_bucket_order(teams,wlt); seen=set(); out=[]
    for s in order:
        if s in seen: continue
        w,l,t=wlt[s]["w"],wlt[s]["l"],wlt[s]["t"]
        gp=w+l+t; wp=(w+0.5*t)/gp if gp>0 else 0.0
        group=buckets[(round(wp,6),l)]
        out.append(sorted(group)); seen.update(group)
    return out

def step2_step4_arrays(teams,bucket,base_order,completed,remaining,mask,margins,base_margin_default=7):
    bucket_set=set(bucket); outside=[s for s in base_order if s not in bucket_set]
    comp_idx={(cg.a,cg.b):cg for cg in completed}; rem_idx={(rg.a,rg.b):i for i,rg in enumerate(remaining)}
    def res_vs(s,opp):
        a,b,_=normalize_pair(s,opp); cg=comp_idx.get((a,b))
        if cg is not None:
            if cg.res_a==1: return 2 if s==a else 0
            if cg.res_a==-1: return 0 if s==a else 2
            return 1
        idx=rem_idx.get((a,b)); 
        if idx is None: return None
        bit=(mask>>idx)&1; winner=a if bit==1 else b
        return 2 if s==winner else 0
    def pd_vs(s,opp):
        a,b,_=normalize_pair(s,opp); cg=comp_idx.get((a,b))
        if cg is not None: return cg.pd_a if s==a else -cg.pd_a
        idx=rem_idx.get((a,b)); 
        if idx is None: return None
        bit=(mask>>idx)&1; m=margins.get((a,b),base_margin_default)
        if bit==1: return m if s==a else -m
        else: return -m if s==a else m
    step2={s:[res_vs(s,o) for o in outside] for s in bucket}
    step4={s:[pd_vs(s,o)  for o in outside] for s in bucket}
    return step2, step4

def resolve_bucket(bucket,teams,wlt,base_order,completed,remaining,mask,margins,base_margin_default=7):
    if len(bucket)==1: return bucket[:]
    h2h_pts,h2h_pd_cap,_=build_h2h_maps(completed,remaining,mask,margins,base_margin_default)
    step1={s:0.0 for s in bucket}
    for s in bucket:
        for o in bucket:
            if s==o: continue
            step1[s]+=h2h_pts.get((s,o),0.0)
    step3={s:0 for s in bucket}
    for s in bucket:
        for o in bucket:
            if s==o: continue
            step3[s]+=h2h_pd_cap.get((s,o),0)
    step2,step4=step2_step4_arrays(teams,bucket,base_order,completed,remaining,mask,margins,base_margin_default)
    def key(s):
        return (-step1[s],
                tuple([-x if x is not None else math.inf for x in step2[s]]),
                -step3[s],
                tuple([-(x if x is not None else -10**9) for x in step4[s]]),
                wlt[s]["pa"], s)
    return sorted(bucket, key=key)

def resolve_standings_for_mask(teams,completed,remaining,mask,margins,base_margin_default=7,pa_win=14):
    wlt=standings_from_mask(teams,completed,remaining,mask,pa_win,margins,base_margin_default)
    base_order=base_bucket_order(teams,wlt)
    final=[]
    for bucket in tie_bucket_groups(teams,wlt):
        final.extend(resolve_bucket(bucket,teams,wlt,base_order,completed,remaining,mask,margins,base_margin_default))
    return final

def rank_to_slots(order): return {s:(i,i) for i,s in enumerate(order,start=1)}

def unique_intra_bucket_games(buckets,remaining):
    inb=set().union(*(set(b) for b in buckets if len(b)>1)); seen=set(); out=[]
    for rg in remaining:
        if rg.a in inb and rg.b in inb:
            key=(rg.a,rg.b)
            if key not in seen:
                seen.add(key); out.append(rg)
    return out

# ---------- Boolean minimization helpers ----------
def minimize_minterms(minterms):
    terms={frozenset(m.items()) for m in minterms}
    changed=True
    while changed:
        before=len(terms)
        # absorption
        to_remove=set()
        lst=list(terms)
        for i,a in enumerate(lst):
            for j,b in enumerate(lst):
                if i!=j and a.issuperset(b):
                    to_remove.add(a)
        if to_remove:
            terms=terms - to_remove
        # combine
        lst=list(terms); n=len(lst); merged=set(); used=[False]*n
        for i in range(n):
            for j in range(i+1,n):
                a=lst[i]; b=lst[j]
                da=dict(a); db=dict(b)
                keys=set(da.keys())|set(db.keys())
                diffs=[k for k in keys if da.get(k,None)!=db.get(k,None)]
                if len(diffs)==1:
                    k=diffs[0]
                    if k in da and k in db:
                        new=dict(da); new.pop(k,None)
                        merged.add(frozenset(new.items()))
                        used[i]=used[j]=True
        out=set()
        for idx,t in enumerate(lst):
            if not used[idx]: out.add(t)
        out |= merged
        terms=out
        changed=(len(terms)!=before)
    return [dict(t) for t in terms]

# ---------- Main enumeration + outputs ----------
def enumerate_region(conn, clazz, region, season, out_csv=None, explain_json=None, out_seeding=None, out_scenarios=None):
    teams=fetch_division(conn,clazz,region,season)
    if not teams: raise SystemExit("No teams found.")
    completed=fetch_completed_pairs(conn,teams,season)
    remaining=fetch_remaining_pairs(conn,teams,season)
    R=len(remaining)

    first=Counter(); second=Counter(); third=Counter(); fourth=Counter()
    scenario_minterms = {}  # team -> seed -> list of minterm dicts

    pa_win=14
    base_margins={(rg.a,rg.b):7 for rg in remaining}

    game_vars=[]
    for i,rg in enumerate(remaining):
        var=f"{rg.a}>{rg.b}"
        game_vars.append((var, rg.a, rg.b))

    if R==0:
        order=resolve_standings_for_mask(teams,completed,remaining,0,margins={},base_margin_default=7,pa_win=pa_win)
        slots=rank_to_slots(order)
        for s,(a,b) in slots.items():
            if 1>=a and 1<=b: first[s]+=1
            if 2>=a and 2<=b: second[s]+=1
            if 3>=a and 3<=b: third[s]+=1
            if 4>=a and 4<=b: fourth[s]+=1
        denom=1.0
    else:
        total=1<<R
        for mask in range(total):
            base_assign={}
            for i,(var,a,b) in enumerate(game_vars):
                bit=(mask>>i)&1
                base_assign[var]=bool(bit)
            wlt=standings_from_mask(teams,completed,remaining,mask,pa_win,base_margins,base_margin_default=7)
            buckets=tie_bucket_groups(teams,wlt)
            intra_games=unique_intra_bucket_games(buckets,remaining)
            K=len(intra_games)

            thresholds = {}
            if K>0:
                baseline_order=resolve_standings_for_mask(teams,completed,remaining,mask,margins=base_margins,base_margin_default=7,pa_win=pa_win)
                baseline_places={t:baseline_order.index(t)+1 for t in teams}
                for rg in intra_games:
                    pair=(rg.a,rg.b); threshold=None
                    for m in range(1,13):
                        margins=dict(base_margins); margins[pair]=m
                        test_order=resolve_standings_for_mask(teams,completed,remaining,mask,margins=margins,base_margin_default=7,pa_win=pa_win)
                        test_places={t:test_order.index(t)+1 for t in teams}
                        if any(baseline_places[t]!=test_places[t] for t in teams):
                            threshold=m; break
                    if threshold is not None:
                        thresholds[pair]=threshold

            if K==0 or not thresholds:
                order=resolve_standings_for_mask(teams,completed,remaining,mask,margins=base_margins,base_margin_default=7,pa_win=pa_win)
                slots=rank_to_slots(order)
                for s,(a,b) in slots.items():
                    if 1>=a and 1<=b: first[s]+=1
                    if 2>=a and 2<=b: second[s]+=1
                    if 3>=a and 3<=b: third[s]+=1
                    if 4>=a and 4<=b: fourth[s]+=1
                for team,(a,b) in slots.items():
                    seed=a
                    scenario_minterms.setdefault(team, {}).setdefault(seed, []).append(dict(base_assign))
            else:
                keys=list(thresholds.keys())
                for hi_lo in product([0,1], repeat=len(keys)):
                    margins=dict(base_margins)
                    assign=dict(base_assign)
                    frac=1.0
                    for (pair,flag) in zip(keys,hi_lo):
                        t = thresholds[pair]
                        varm=f"{pair[0]}>{pair[1]}_GE{t}"
                        if flag==1:
                            margins[pair]=t; assign[varm]=True
                            frac *= (13 - t) / 12.0
                        else:
                            margins[pair]=max(1, t-1); assign[varm]=False
                            frac *= (t - 1) / 12.0
                    order=resolve_standings_for_mask(teams,completed,remaining,mask,margins=margins,base_margin_default=7,pa_win=pa_win)
                    slots=rank_to_slots(order)
                    for s,(a,b) in slots.items():
                        if 1>=a and 1<=b: first[s]+=frac
                        if 2>=a and 2<=b: second[s]+=frac
                        if 3>=a and 3<=b: third[s]+=frac
                        if 4>=a and 4<=b: fourth[s]+=frac
                    for team,(a,b) in slots.items():
                        seed=a
                        scenario_minterms.setdefault(team, {}).setdefault(seed, []).append(assign)
        denom=float(1<<R)

    results=[]
    for s in teams:
        o1=first[s]/denom; o2=second[s]/denom; o3=third[s]/denom; o4=fourth[s]/denom
        op=o1+o2+o3+o4
        clinched=op>=0.999; eliminated=op<=0.001
        fop=1.0 if clinched else (0.0 if eliminated else op)
        results.append((s,o1,o2,o3,o4,op,fop,clinched,eliminated))

    print("school,odds_1st,odds_2nd,odds_3rd,odds_4th,odds_playoffs,final_odds_playoffs,clinched,eliminated")
    for row in sorted(results, key=lambda r: (-r[6], r[0])):
        print("{},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{:.6f},{},{}".format(*row))

    if out_seeding:
        by_seed={1:[],2:[],3:[],4:[],"out":[]}
        for (school,o1,o2,o3,o4,op,fop,clinched,eliminated) in results:
            by_seed[1].append((school,o1))
            by_seed[2].append((school,o2))
            by_seed[3].append((school,o3))
            by_seed[4].append((school,o4))
            by_seed["out"].append((school,1.0-op))
        for k in [1,2,3,4,"out"]:
            by_seed[k].sort(key=lambda x:(-x[1],x[0]))
        lines=[f"Region {region}-{clazz}A",""]
        for seed in [1,2,3,4]:
            lines.append(f"{seed} Seed:"); wrote=False
            for team,prob in by_seed[seed]:
                if prob>0: lines.append(f"{pct_str(prob)} {team}"); wrote=True
            if not wrote: lines.append("None")
            lines.append("")
        lines.append("5 Seed (Out):"); wrote=False
        for team,prob in by_seed["out"]:
            if prob>0: lines.append(f"{pct_str(prob)} {team}"); wrote=True
        if not wrote: lines.append("None")
        lines.append(""); lines.append("Eliminated:")
        elim=[team for team,prob in by_seed["out"] if abs(prob-1.0)<1e-12]
        if elim:
            for t in sorted(elim): lines.append(t)
        else:
            lines.append("None")
        with open(out_seeding,"w") as f: f.write("\n".join(lines)+"\n")
        print(f"Wrote seeding odds text: {out_seeding}")

    if out_scenarios:
        def var_phrase(var: str, val: bool) -> str:
            if "_GE" in var:
                base,ge = var.split("_GE")
                a,b = base.split(">")
                return f"{a} Win over {b} by ≥ {ge} points" if val else f"{a} Win over {b} by < {ge} points"
            else:
                a,b = var.split(">")
                return f"{a} Win over {b}" if val else f"{b} Win over {a}"

        def extract_pair(clause: str):
            # Returns (a,b,kind,thr) where kind in {'base','ge','lt'} and thr is int or None
            if " Win over " not in clause:
                return None
            left, right = clause.split(" Win over ", 1)
            a = left.strip()
            # Check for margin qualifiers
            if " by ≥ " in right:
                opp_part, thr_part = right.split(" by ≥ ", 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, 'ge', thr)
            elif " by < " in right:
                opp_part, thr_part = right.split(" by < ", 1)
                b = opp_part.strip()
                try:
                    thr = int(thr_part.split()[0])
                except Exception:
                    thr = None
                return (a, b, 'lt', thr)
            else:
                b = right.split(" by")[0].strip()
                return (a, b, 'base', None)

        def is_opposite(p1, p2):
            # Opposites when:
            #  (A) directions flip (A>B vs B>A) and both are base, OR
            #  (B) directions flip and both are margin-qualified with SAME comparator and SAME threshold, OR
            #  (C) directions are the SAME and both are margin-qualified at SAME threshold but complementary comparators (≥ vs <).
            if p1 is None or p2 is None:
                return False
            a1,b1,k1,t1 = p1
            a2,b2,k2,t2 = p2
            # Case A/B: reversed direction
            if a1==b2 and b1==a2:
                if k1=='base' and k2=='base':
                    return True
                if k1==k2 and t1==t2 and k1 in ('ge','lt'):
                    return True
            # Case C: same direction, complementary margin at same threshold
            if a1==a2 and b1==b2 and t1==t2 and {k1,k2}=={'ge','lt'}:
                return True
            return False

        minimized = defaultdict(dict)
        for team, seeds in scenario_minterms.items():
            for seed, minterms in seeds.items():
                mins = [dict(m) for m in minterms]
                mins = minimize_minterms(mins)
                minimized[seed][team] = mins

        lines=[f"Region {region}-{clazz}A",""]
        prob_idx = {1:1,2:2,3:3,4:4}
        for seed in [1,2,3,4]:
            lines.append(f"{seed} Seed:")
            prob_map = {row[0]: row[prob_idx[seed]] for row in results}
            teams_sorted = [t for t in sorted(prob_map, key=lambda t: -prob_map[t]) if prob_map[t] > 0]
            for team in teams_sorted:
                p = prob_map[team]
                lines.append(f"{pct_str(p)} {team}")
                if abs(p-1.0) < 1e-12:
                    lines.append("")
                    continue
                mins = minimized.get(seed, {}).get(team, [])

                def clauses_for_m(m):
                    base_pairs=[]; margin_map={}
                    for var,val in m.items():
                        if "_GE" in var:
                            base,_ = var.split("_GE")
                            margin_map[base]=(var,val)
                        else:
                            base_pairs.append((var,val))
                    clauses=[]
                    for var,val in base_pairs:
                        if var not in margin_map:
                            clauses.append(var_phrase(var,val))
                    for base,(mvar,mval) in margin_map.items():
                        clauses.append(var_phrase(mvar,mval))
                    return clauses

                prepared = [(m, clauses_for_m(m)) for m in mins]
                prepared.sort(key=lambda x: len(x[1]))

                seen_pairs = set()
                printed_any_block = False
                for i, (m, clauses) in enumerate(prepared):
                    cleaned=[]
                    for c in clauses:
                        pair = extract_pair(c)
                        if pair is None:
                            cleaned.append(c); continue
                        if any(is_opposite(pair, prev) for prev in seen_pairs):
                            continue
                        cleaned.append(c)
                    clauses = cleaned

                    if not clauses:
                        continue

                    for c in clauses:
                        pair = extract_pair(c)
                        if pair: seen_pairs.add(pair)

                    if printed_any_block:
                        lines.append("  OR")
                    lines.append(f"  - {clauses[0]}")
                    for clause in clauses[1:]:
                        lines.append(f"    AND {clause}")
                    printed_any_block = True
                lines.append("")
        lines.append("Eliminated:")
        elim = [row[0] for row in results if abs(row[5]) < 1e-12]
        if elim:
            for t in sorted(elim): lines.append(t)
        else:
            lines.append("None")
        with open(out_scenarios,"w") as f:
            f.write("\n".join(lines)+"\n")
        print(f"Wrote scenarios text: {out_scenarios}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--class", dest="clazz", type=int, required=True)
    ap.add_argument("--region", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dsn", type=str, default=os.getenv("PG_DSN",""))
    ap.add_argument("--out-csv", type=str)
    ap.add_argument("--explain-json", type=str)
    ap.add_argument("--out-seeding", type=str)
    ap.add_argument("--out-scenarios", type=str)
    args=ap.parse_args()
    if not psycopg: raise SystemExit("Please install psycopg: pip install 'psycopg[binary]'")
    if not args.dsn: raise SystemExit("Provide --dsn or PG_DSN")
    with psycopg.connect(args.dsn) as conn:
        enumerate_region(conn, args.clazz, args.region, args.season,
                         out_csv=args.out_csv,
                         explain_json=args.explain_json,
                         out_seeding=args.out_seeding,
                         out_scenarios=args.out_scenarios)

if __name__ == "__main__":
    main()
