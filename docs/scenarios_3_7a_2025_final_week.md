# Class 7A Region 3 — Final Week Scenarios (2025)

Pre-final-week standings heading into 2025-11-07:

| Team | Region W | Region L |
|---|---|---|
| Oak Grove | 4 | 0 |
| Petal | 3 | 1 |
| Brandon | 2 | 2 |
| Northwest Rankin | 2 | 2 |
| Pearl | 2 | 2 |
| Meridian | 0 | 4 |

Final week games:
- Brandon vs Meridian
- Northwest Rankin vs Petal
- Pearl vs Oak Grove

---

## Division Scenarios (`render_scenarios`)

Scenario 4 (five-way tie when Brandon wins) breaks into 12 sub-scenarios depending on the winning margins of the Pearl–Oak Grove and Northwest Rankin–Petal games.

```
Scenario 1: Pearl beats Oak Grove AND Petal beats Northwest Rankin
1. Petal
2. Pearl
3. Oak Grove
4. Brandon
Eliminated: Northwest Rankin, Meridian

Scenario 2: Oak Grove beats Pearl AND Petal beats Northwest Rankin
1. Petal
2. Oak Grove
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian

Scenario 3: Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4a: Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Northwest Rankin
2. Oak Grove
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4b: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Northwest Rankin
2. Pearl
3. Oak Grove
4. Petal
Eliminated: Brandon, Meridian

Scenario 4c: Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4–10 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Northwest Rankin
2. Pearl
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4d: Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 5–9 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Oak Grove
2. Northwest Rankin
3. Pearl
4. Petal
Eliminated: Brandon, Meridian

Scenario 4e: Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 4–8 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4f: Brandon beats Meridian AND Pearl beats Oak Grove by 1–4 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
1. Oak Grove
2. Petal
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4g: Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4–9 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Pearl
2. Northwest Rankin
3. Petal
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4h: Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
1. Pearl
2. Petal
3. Northwest Rankin
4. Oak Grove
Eliminated: Brandon, Meridian

Scenario 4i: Brandon beats Meridian AND Pearl beats Oak Grove by 7–9 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
1. Pearl
2. Petal
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4j: Brandon beats Meridian AND Pearl beats Oak Grove by 3–5 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
1. Petal
2. Oak Grove
3. Northwest Rankin
4. Pearl
Eliminated: Brandon, Meridian

Scenario 4k: Brandon beats Meridian AND Pearl beats Oak Grove by 4–5 AND Northwest Rankin beats Petal by 1–2 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
1. Petal
2. Oak Grove
3. Pearl
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 4l: Brandon beats Meridian AND Pearl beats Oak Grove by 6–8 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
1. Petal
2. Pearl
3. Oak Grove
4. Northwest Rankin
Eliminated: Brandon, Meridian

Scenario 5: Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Northwest Rankin
3. Petal
4. Brandon
Eliminated: Pearl, Meridian

Scenario 6: Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
1. Oak Grove
2. Petal
3. Brandon
4. Northwest Rankin
Eliminated: Pearl, Meridian
```

---

## Per-Team Scenarios (`render_team_scenarios`)

Margin conditions in Scenario 4 sub-scenarios refer to the winning margins in the Pearl–Oak Grove and Northwest Rankin–Petal games.

```
Meridian

Eliminated.
```

```
Oak Grove

#1 seed if:
1. Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–4 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 4–8 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 5–9 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#2 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3–5 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 4–5 AND Northwest Rankin beats Petal by 1–2 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6–8 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7–9 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

#4 seed if:
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4–10 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4–9 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
```

```
Pearl

#1 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 7–9 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4–9 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#2 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6–8 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4–10 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
5. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 5–9 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4–5 AND Northwest Rankin beats Petal by 1–2 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1–4 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 4–8 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 3–5 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin exceeds Northwest Rankin's by exactly 2

Eliminated if:
1. Oak Grove beats Pearl
```

```
Petal

#1 seed if:
1. Petal beats Northwest Rankin
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3–5 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4–5 AND Northwest Rankin beats Petal by 1–2 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6–8 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less

#2 seed if:
1. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–4 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
3. Brandon beats Meridian AND Pearl beats Oak Grove by 7–9 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#3 seed if:
1. Meridian beats Brandon AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 4–8 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4–10 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4–9 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#4 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 5–9 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
```

```
Brandon

#3 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

#4 seed if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
2. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal

Eliminated if:
1. Pearl beats Oak Grove AND Northwest Rankin beats Petal
```

```
Northwest Rankin

#1 seed if:
1. Meridian beats Brandon AND Pearl beats Oak Grove AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 6 or more AND Pearl's margin and Northwest Rankin's margin combined total 11 or more
3. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 4–10 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6 or more AND Northwest Rankin beats Petal by 5 or more AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1

#2 seed if:
1. Meridian beats Brandon AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
2. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 4–8 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
3. Brandon beats Meridian AND Pearl beats Oak Grove by 1–5 AND Northwest Rankin beats Petal by 5–9 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10
4. Brandon beats Meridian AND Pearl beats Oak Grove by 7 or more AND Northwest Rankin beats Petal by 4–9 AND Pearl's margin exceeds Northwest Rankin's by 3 or more

#3 seed if:
1. Brandon beats Meridian AND Pearl beats Oak Grove by 1–4 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin doesn't exceed Northwest Rankin's by more than 1
2. Brandon beats Meridian AND Pearl beats Oak Grove by 3–5 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin exceeds Northwest Rankin's by exactly 2
3. Brandon beats Meridian AND Pearl beats Oak Grove by 8 or more AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 11 or more

#4 seed if:
1. Oak Grove beats Pearl AND Petal beats Northwest Rankin
2. Brandon beats Meridian AND Oak Grove beats Pearl AND Northwest Rankin beats Petal
3. Brandon beats Meridian AND Pearl beats Oak Grove by 4–5 AND Northwest Rankin beats Petal by 1–2 AND Pearl's margin exceeds Northwest Rankin's by 3 or more
4. Brandon beats Meridian AND Pearl beats Oak Grove by 6–8 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total 9 or less
5. Brandon beats Meridian AND Pearl beats Oak Grove by 7–9 AND Northwest Rankin beats Petal by 1–3 AND Pearl's margin and Northwest Rankin's margin combined total exactly 10

Eliminated if:
1. Pearl beats Oak Grove AND Petal beats Northwest Rankin
```
