# HANDOFF — Kaggriculture agent, beat-all-8 task

## 1. Where we are (Sep 29, 2026)
- `final_agent.py` is the current best. `base_dsm348.py` is the weak baseline it descends from.
- Scores (higher reward wins; margins = US − OPP):
  - Baseline: H2H panel AVG **-50,579**, WINS **0/16**; solo6 mean ~145.6k.
  - Current: H2H panel AVG **-42,838 over 18 games (9 opps)**, WINS **0/18**
    (+7.7k closed); solo6 mean **143.2k** (-1.7%). Verified Sep 29 2026:
    TOTAL=-771081, WINS=0/18, AVG=-42838.
- Panel = `panel_2games.py` (9 opps × seeds 200001/200002, our agent seat 0): pipe19, pipe18,
  kagg, v57, base_v76, main, main1, main_copy_1, **opp_master** (extracted from
  `reference_master_agent.ipynb`, cell-3 blob verified by sha256; entry `agent` alias at
  file end; solo 172k / H2H −44k mean — pipe19-class, MUST be beaten too).
- Solo seeds: 300001–300006 (vs PASS dummy). Fresh H2H seeds seen: 300001/300002.
- Original frozen agent (`my_dsm348.py`, md5 `4da51b90e6457077453fd508e588fc52`) was never
  modified; all work is in this folder. `final_agent.py` must keep `agent()` as the LAST
  callable in the file (harness loads `ns['agent']`).

## 2. What is in final_agent.py (the +7.9k over baseline)
1. Wheat→carrot mix shift d11+ (carrot niche holds price; +4.5k H2H).
2. Carrot quota trim toward opp's 52 births (water/deaths; +0.4k H2H, +1.1k solo).
3. Crash gates (B4, +2.9k panel, solo-neutral): never SELL MILK/WOOL/STRAWBERRY/MELON/TOMATO
   at price ≤ 2; skip CARE/HARVEST of crashed milk/wool (keep FEED); dump sprint goods
   (MILK/WOOL/STRAWBERRY) while strong (≥0.85×base) to race opp bulk waves.

## 3. Rejected (DO NOT retry blindly; all measured solo3+H2H, most also panel)
- Herd expansion (d2/d3 cows + sheep 6→8/6/6): solo +2.9k BUT H2H −5k (opp gains more via
  shared prices/RNG). File `cand_b2_herd.py` kept as reference of the failure.
- d0 remix (H5/2S/M9–12/W7/P14, 3rd sheep cut): solo −8k (d0 wallet cliff → wheat gap d3–6 →
  escapes). Helps only the poorest seed (+35k on 300003) — poverty-insurance pattern.
- Fert opportunity-cost gate + fert buy cuts: solo −6k.
- Full-package v401 (all above stacked): solo −22k. `cand_v401.py` kept for parts only.
- Older: early-cow+d5-straw, bank/loan tweaks, geese 0/2, melon+straw ETH bumps, feed-radius
  lift, d5 herd caps, fert embargo/buffer, 5th-hand-d0 — all flat or negative.
- Feed-visibility half-lift looked good on margin but lowered OUR absolutes while crashing
  OPP (shared-RNG/market denial illusion) — always check US absolutes, not margin alone.

## 4. Engine facts (verified from kaggle_environments 1.32.7 source)
- 30 days (d0–29), 24 steps/day, start $3000. One SHARED market; both seats quoted the same
  pre-commit price per unit; commits apply in seat order (we are seat 0 — small race edge).
- Price = f(net surplus = combined SELL − combined BUY − town drain), persists all game,
  floor $1; sales at $1 add no supply. Town shops unlock over time (RNG) and drain
  MILK/STRAWBERRY/WHEAT/TOMATO heavily; FERT/EGG/MELON/WOOL/CARROT little or none.
- Collapse points (combined sales → $1): STRAWBERRY ~63, MILK ~77, WOOL ~59, MELON ~158.
  WHEAT/EGG never collapse (log curve, floor ~$20/$39). CARROT T=450 hinge, min ~$7.
- FEED = 1 WHEAT/animal/day, all species; ≥2 consecutive unfed days = escape ($300–500
  capital lost). Missed feed also forfeits CARE bonus. Structures (COOP/PASTURE) are FREE
  ($0, tile + action); 1 animal per structure tile. max_held overflow is LOST (goose 4,
  cow 6, sheep 6). CARE doubles-ish output (goose 1→2/d, cow 0.5→1.5/d, sheep 0.33→1.33/d,
  1 act/animal/day). Every animal makes 1 FERTILIZER/day (collect it, sell early: first
  200 fert avg ~$80, then declines; fert has NO town drain).
- Crops: WHEAT seed 10, 4 yield (6 fert) in 4d. CARROT seed 20, 3 (4) in 3d. MELON seed 80,
  6 cap in ~12d, strictly one-shot (second cycle worth $1). STRAWBERRY seed 100, ongoing
  4 (8 fert) over ~17d, first harvest planted+10. TOMATO seed 50, ongoing 4 (8) over ~12d.
  HIRE cost = fib(hires_today) ≈ $1,1,2,3,5,8… (labor is cheap, ~10/day optimal).
  LAND prices 1000/2000/4000. MAX 10 market orders/step.

## 5. Opp intel (opp_pipe19.py active agent = LAST `def agent`, ~line 7101; stacked file)
- d0: HIRE 5, COW 2 + SHEEP 2, PASTURE x4, MELON 12 + WHEAT 7. Funded by daily fert sales
  (4 animals → manure → cash from d1) + wheat churn, NOT savings.
- d2 COW, d3 COW, d5 STRAWBERRY 4, d6 COW 2 + LAND, d7 COW 2, d8/d9 SHEEP 2+2,
  d10 GOOSE 2, d11 GOOSE 1 + LAND. Melons d0 → bulk-sell d10 (~72u). Straw bulk d15+.
- Sells milk/wool EARLY (bulk d6–d10) before collapse; min sell price 2; trickles late.
- Opp solo6 mean ~174.7k (mix: STRAW 50–60k, WOOL 20–46k, MILK 35–65k, FERT 15–23k,
  MELON 16–18k). Our solo6 143.2k. Solo gap ≈ 31k. H2H gap ≈ 43k.
- Opp has 11 sheep by d12 (we stall at 3 — our d10 wallet hole $231 vs their $4436 starves
  our sheep wave; feed_cap then blocks catch-up). Opp buys 0 geese in most lines.

## 6. Ranked gaps (measured, biggest first)
1. Strawberry system: opp $47–60k vs our ~$11k (33+ fert-boosted plants sold into town
   drain vs our SEEDCAP-14 starved stands). Volume + harvest completeness.
2. Milk alignment: same feed/care rates, 2.26 vs 2.68 u/cow-day (same-day feed+care stack
   misses on far cows) + early-sprint timing.
3. d10 melon wave: 6 plants vs 12 + late plantings ripening after the crash.
4. d6 wallet wave: $1–300 vs $845–1541 (failed hires/land/cows).
5. Movement: 2.2× PICKUP trips, 1.75 vs 0.80 move/act late, idle 25–43% d2–7 is POVERTY
   (not dispatch), d29 terminal labor (opp ends W0, we end W10+ unharvested).

## 7. Tool commands (run from this folder; needs kaggle-environments==1.32.7)
- `python3 panel_2games.py <agent.py>` — the OFFICIAL score: 16 games, TOTAL/WINS/AVG.
- `python3 harness.py <agent.py>` — 4-opps × 2-seeds × 2-seats matrix (both seats!).
- `python3 gap_diag.py <agent.py> <seed>` — solo: money/herd/stands trajectory + verbs +
  deaths/escapes (use vs PASS only; do NOT trust its numbers in H2H mode).
- `python3 rev_audit.py <agent.py> <seed>` — solo revenue by first-sold-item per step
  (rough when sells bundle; exact for opp-style bulk single-item sales).
- `python3 milk_audit.py / h2h_cash.py / h2h_melon.py / h2h_herd.py / idle_census.py /
  cow_cap.py / early_trace.py` — focused diagnostics (read the file header first; ~50 lines each).

## 8. Validation protocol (results are noisy — this is MANDATORY, not optional)
- H2H margin noise is ±15–30k per game: our actions change shared prices, town-shop RNG,
  and weed draws (game RNG is shared). NEVER trust 1–2 games. ANY code change reshuffles
  the species line via shop RNG — 2-seed screens cannot resolve effects under ~10–20k.
- **H2H margin is the ONLY acceptance metric. Solo NEVER predicts H2H** (prior session:
  value-sorted selling +4.3k solo / −1.1k H2H; melon-window +3.4k solo / ~0 H2H). Solo is
  a smoke test only. Screen H2H vs BOTH pipe19 and v57, n≥12 H2H games for finalists,
  treat sub-2k deltas as zero.
- Promote a change ONLY if ALL THREE agree: (a) solo6 mean not down vs `final_agent.py`
  (guard, not verdict), (b) 18-game panel AVG up with most games improving,
  (c) fresh-seed H2H (new seeds like 400001+) not collapsing.
- Screen cheaply first: pipe19+v57 H2H on 200001/200002; panel only finalists.
- Always report US absolutes + OPP absolutes + margin (margin alone lies — see §3 denial
  lesson). Never modify `opps/`. Full rewrites are allowed; overfitting to these 9 opps
  (e.g. seed-specific hacks) is forbidden — the grader may use fresh seeds.
- Read `FINDINGS.md` IN FULL before designing anything: months of falsified variants
  (d0 sealed H4/2C+3S/M6 — 5th hire −40k; wheat gate stays yld≥2; deaths are symptom not
  cause; gap-fill priority levers all falsified; goose cap −3.5k; herd-cap decouple
  fails). Do not re-run its rejected list.
- Open validated leads (UNTRIED in our line, from FINDINGS.md): (i) take the 4th
  quadrant (unclamp `land_want`, +3.2k H2H t≈2 both opps); (ii) d10 melon mass-pick —
  12 plants harvested d10 same-morning (5.0→4.0→3.0 late decay, −$9.9k hole);
  (iii) milk yield/cow 22.5→27.9 (cause open: NOT care/cap/shed — measure first);
  (iv) sale-reservation RACE (opp_v57 RACE block: first seller takes the price;
  our polarity is inverted — dump-while-strong is a weak form, race the ORDER
  SEQUENCE next); (v) straw water coverage 57%→~90% of days (29 plants, ~11 die,
  each live plant ~$1.6k; NOT eve coverage which is 90%).
