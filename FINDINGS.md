# Session findings — execution-side diagnosis (baseline md5 0b9235a05a4fbe886c3388dd07548f4a)

## The binding metric: moves-per-action (mv/act)
Built `our_walkcost.py` / `mine_walkcost.py` — same metric for us (live) and DSM (replays).

| metric | DSM | ours | gap |
|---|---|---|---|
| acts/unit/day (d11-17) | 11.6 | 7.5 | -4.1 |
| moves/unit/day | 9.3 | 13.2 | +3.9 |
| mv/act | 0.80 | 1.75 | +0.95 |
| 0-move actions | 51.7% | 34.8% | -17pp |
| 2+-move actions | 12.8% | 30.1% | +17pp |
| dawn commute | 1.22 | 2.09 | +0.87 |

~13 units each => ~51 moves/day that should be actions. Same step budget (both
~275 of 312 used): DSM converts 64% of steps to actions, we convert 35%.

## Per-action move cost (d11-17)
| action | ours | DSM | our vol/day | wasted moves/day |
|---|---|---|---|---|
| WATER | 1.42 | 0.84 | ~34 | ~19.7 |
| FERTILIZE | 3.57 | 1.19 | ~7 | ~15 |
| PICKUP | 1.27 | 0.36 | ~5 | ~5 |
| CARE | 0.82 | 0.12 | ~8 | ~5 |
| COLLECT_FERT | 0.99 | 0.38 | ~10 | ~6 |

Role split (var_rolecost.py): WATER and FERTILIZE waste are both crop-role.
35% of expensive (>=2 move) actions follow WATER->long walk -> the thirsty
set is sparse (we water 34/day vs DSM 58, fewer plants + survival-min policy).
19% follow COLLECT_FERTILIZER (the fert pipeline round trips).

## Engine truths confirmed this session
- Dawn reset: farmer -> default_spawn (4,4); hands cleared, re-hire, spawn on
  the 4 shed-access tiles (4,4),(5,4),(4,5),(5,5), min-occupancy. ALL units
  start on those 4 tiles every dawn => commute is symmetric for us and DSM.
- DROP/PICKUP require _is_shed_adjacent (must stand on a shed-access tile).
- Ongoing production: banks +1 per tick regardless of water; fert gives +2
  ONLY if watered that day. STRAWBERRY first=10 interval=2 maxyield=4;
  TOMATO first=8 interval=1; WHEAT/CARROT one-shot first=2; MELON first=10.
- Crops: WHEAT/CARROT/STRAWBERRY/TOMATO/MELON prices are dynamic (market).

## Production reality (seed 200001, money gauge)
d12 "91 units sold" = one-time liquidation of 64 hoarded wheat. Steady state
d13-17 is ~25-35 units/day vs DSM ~95. d15 h12 field: 48 plants, 0 ripe,
38 unwatered, 17 at cu=1 (die tonight); almost all strawberry/tomato are
immature (straw a2-a5, tomato a3-a4). Deaths only ~2-5/day (weeds), not a
mass die-off — the limit is plant count + maturity, not survival alone.
Layout: the ENTIRE southern half (y6-9) is empty (~40 tiles); structures form
a wall at y3-5 around the shed; x=4 column has weeds at y0-2.

## REJECTED interventions (pinned A/B, all reverted, baseline verified clean)
1. var_fertcol.py — restrict crop fert delivery to own column / radius 3:
   FERTILIZE 3.57->1.81, WATER 1.42->1.24 (mechanism worked!) but MONEY
   32504 vs 36148 (-3.6k; 200003 +24k, 200001 -23k). The cross-map fert walk
   is PRODUCTIVE: it doubles tier-0 wheat/carrot which compounds into feed.
2. var_fertval.py — value-score + hurdle-gate needy_plant (stop fert on
   $75 wheat when fert sells for $100): 32853 vs 36148 (-3.3k). Fert is a
   FREE animal byproduct; its sell price understates its feed value.
3. var_enroute.py — water any unwatered plant en route + ENROUTE_MAX 3->6:
   25048 vs 36148 (-11.1k). Mass arrival delays; survival-only enroute water
   is load-bearing.
4. var_shed.py — forbid building on shed-access tiles (found PASTURE+COW on
   (4,4) and (5,4), paving 2 of 4 bank lanes): 18537 vs 36148 (-17.6k). The
   (4,4) pasture is the d0 initial placement; compact-farm deliberately
   builds at the shed and 2 bank lanes already suffice (DROP 21-72/game).

## Conclusion
The field-exec layer is at a strong local optimum: four well-mechanised
efficiency fixes all lost money because the "wasted" moves are productive.
The income gap is the PRODUCTION RAMP (plant count, crop maturity, herd size
12 vs 21-25) — scheduler territory (CROP_TARGETS / land / seed / herd), which
the delegated scheduler agent owns. DSM's cheap CARE/COLLECT (0.12/0.38)
implies its structures are interspersed with crops so one unit does both with
zero-move transitions; our column-sweep + separate animal role forces the
fert/animal round trips. Closing the last gap likely needs that layout
redesign, not micro-optimisation.

## Reusable tools (in ~/agentscratch/)
our_walkcost.py, mine_walkcost.py, mine_actcost_dsm.py — mv/act metric, us vs DSM.
var_rolecost.py — action cost by role. var_prevcost.py — preceding action of
high-cost actions. gauge_field.py — full field snapshot (crop/age/yld/water).
gauge_layout.py — ASCII farm map. gauge_deaths.py — weeds/plants per day.
gauge_sales.py — money + SELL orders per day. var_probe.py — work-found vs
executed per day. ab_pin.py — pinned A/B (judge on >=5k deltas; noise floor 5k).

## Session 2026-09-25: dead-code audit + day-0 DSM copy (var_d0)
DSM replays: new_agent/"new helper/new replays2"/ (31 JSON). Canonical staged
d0 (112829119 seat0): s1 1C+5 prod ($3000->~$2464), s2 4 hires + 1C+3S
(->$585), then SELL1/BUY1 wheat churn + MELON 2 at s7/s9/s12 + WHEAT seeds to
~10; ends $6-8 with 9W+6M standing, 5 head, 4 hands.

### Dead / hurting code confirmed in agent.py (all verified, none yet removed
### from agent.py — variants only)
1. `st['rush10'/'rush11']` (sched 351-354) SET but never READ — dead.
2. `t == 'LOCKED' or t == 'LOCKED'` (scan 106) — duplicated rot (harmless).
3. Qty capped by ORDER SLOTS: `min(qty-done, 10-len(orders), cap)` (P 604, S
   617) truncated d0 S10->5, P6->4 into broke retries — hurting (measured).
4. `st['req']` counts EMISSIONS not landings; engine unit-loop partial-fills
   (verified in kaggriculture._process_market/_commit_unit) make overcounts
   burn quota — hurting (d10 -18k same root; d0 $7 failing prod buys).
5. Wheat reserve on PLACED herd (397) sold 3 of 4 d0 feed (5 owned, 0 placed)
   into a $7 emergency-feed spiral — hurting (measured s0-s1).
6. HIRE 2/step cap (451) vs DSM 4-8 dawn burst; H9 needs 5 steps — hurting
   morning labor. (Fix in var_d0: burst 4.)
7. `soft_gated` animal block leaves `spend` unbound on gated days — latent
   NameError; var_d0 staging tripped it into 24 errors = a DEAD DAY 1.
8. `structure_deficit` +1 phantom (need = herd+1): 1 wasted pasture+coop
   (engine: 1 animal/structure, verified PLACE). Minor hurt.
9. OFF-flag branches (STRIDE/GOOSE_LINE/AFFORD_GATE ~40 lines) never execute —
   dead weight that makes the file hard to reason about.
10. HIRE-orders-vs-landings mining error: "DSM d1: 9 hires" comment mined
    EMITS; landed median is 4 hands (12 replays: 4,1,4,4,4,9,9,3,3,3,2,3).

### var_d0 (~/agentscratch/var_d0.py): staged d0-1 package
HIRE burst 4/step; 1C-first then rest (matches DSM 1+4 split, keeps $1849
buffer); P-before-S d0; wallet staging d0-1 (A60/P60/S30 buffers); reserve on
OWNED; wheat sells trickle-capped 2/step d<=2; d1 H9->H4; LOCKED dup fixed.
Census 200001 vs DSM: d0 13 (7W+6M) vs 15, d1 15 vs 20, d2 17 (9W+2S+6M, herd
5/5, 0 errors) vs 18 — herd survival FIXED (baseline lost a sheep d2), but a
MELON GAP opened (6 vs 10): d1 feed need (full feeding 5/day) + P-before-S
crowds out the $80 melon top-up, and fert collection runs 2/day vs DSM 5-6
(+$200 vs +$500), so the top-up never funds. DSM underfeeds ~75% (1827
gap-0 vs 623 gap-1); we feed 100% — safer but cash-hungry.
A/B pinned 5-seed: 32462 vs 36148 (-3.7k, INSIDE 5k noise => INCONCLUSIVE,
leaning neg; +5.7k on 200002, -3.3..-8.5k rest). Ablation var_d0b (H4->H9
restore): 32466 (-3.7k, same mean, seed signs flip +9.8k/-16.5k) => the H4
cut was NOT the loss; staging reshuffles ±16k/seed with zero mean gain.
NOT ADOPTED. Lesson: baseline's bugs accidentally fund labor (truncation
left $90 -> 9 hires land -> wins); copying DSM emits without DSM's
closed-loop deficit buying doesn't transfer. Next layer is d1 melon/fert
rate (collect 2->5/day) + walk efficiency, not market timing.

## Session 2026-09-25b: 4-step combined push (var_big) -- REJECTED
Plan: feed/fert cash (bank-first) + herd growth + farm growth + walks (hire
burst), all together in ~/agentscratch/var_big.py on top of agent.py.
Census found the stall: d1-5 income ~$100/day not DSM's ~$500 (fert collected
4-7/day = DSM rate, but banked at h20 not midday: carriedF=3 at h16, money
$4), so the d6 herd wave never funded (herd 4-6 until d12, money <$800).

### Changes tried (all conclusive, 10-seed pinned A/B)
1. Fert BANK-FIRST (bank pocket at 2+, or any at h12+): moves ~$300-400 from
   evening to midday. Alone (var_bank.py): 30700 vs 33452 (-2.8k, noise,
   but +-25k/seed: 200006 +24k, 200008 +17k, 200001 -25k, 200004 -19k).
2. HIRE burst 2->5/step (full crew by h2 not h12).
3. Feed runway cap (never hold > ~2 days feed: 2*herd+2-shedW).
4. REVERTED ordered-feed counting (-15.6k on 5-seed): counting promised feed
   as cover ran the herd to 14-16 unfunded -> escapes -> weeds (49->31
   plants on 200004). The strict in-hand gate is load-bearing.
5. Farm-paced herd cap (13 max until 50+ plants AND $2k): first version gave
   +25k on 200003 and +12k on 200002, still -13k on 200004.
6. Scaled afford cushion ($100 -> $100+25*herd): NEVER BINDS (splurges run on
   intraday flow, not savings) -- dead change, left in only as comment.
var_big 10-seed: 32439 vs 33452 (-1k, tie). var_bank 10-seed: 30700 (-2.8k,
tie). Both AMPLIFY variance (+-30k/seed) with zero mean gain.

### Mechanism learnt (the scale trap)
Every change that frees cash converts to head #14-21, which this farm's
income (~$1500/day at 40 sales/day) cannot feed: escapes -> weeds -> field
halves -> -13..-30k. Baseline survives by holding ~13-16 FED (banks $34k
late on 200004 with plants 55->18!). DSM sustains 21-25 because its farm
sells 95/day. Herd must follow farm income, not cash flow; timing-of-cash
tweaks cannot fix a labor-productivity gap -- they only move the boom/bust
earlier. The binding constraint remains: sales/day (labor) -> income ->
sustainable herd. Next: plant-count ramp + walk structure, not market timing.

## Session 2026-09-25c: walk forensics + scheduler push (5 variants)

### Walk forensics (all measured, seed 200001 unless noted)
- Same crew, 2.6x output: DSM hires 9->12/d d8-16, ours 9->12/d. DSM crew
  ~250 acts/d, ours ~95. NOT headcount: mv/act 1.75 vs 0.80 at same hires.
- Barn embed (var_layout: free_tile prefers crop-surrounded tiles; d10 layout
  verified DSM-like, barns inside crop mass): mv/act 1.73 vs 1.75. NO EFFECT.
  Barn position is not the driver. PARKED (not A/B'd, no mechanism).
- Per-action walk budget d11-17 (act_walk.py): WATER 226 acts/322 mv (34%,
  1.42/act), FERTILIZE 44/136 (15%, 3.09), FEED 84/107 (11%, 1.27), PLANT 67/69,
  DIG 30/62, COLLECT 68/60, CARE 56/44, PICKUP 38/42. WATER+FERTILIZE = 49%.
- Column discipline is GOOD (water_where.py): units water in 1-2 cols each,
  3-7 waters/d. Leak is WITHIN-column scatter, not roaming.
- DSM act mix from replay (d11-17/d): WATER 61, HARVEST 25, COLLECT 21,
  CARE 20, FEED 20, PLANT 12, FERTILIZE 11 = ~182 useful/d vs our ~99.
  EVERYTHING scales ~2x with assets (21 vs 12 head, 70 vs 45 plants).
  CONCLUSION: the act gap is an ASSET gap, not efficiency. mv/act gap follows
  from target density (nearest-target walks shrink when targets double).
- Chain-plant (plant underfoot when no HARV anywhere; post-plant water free
  via nearest): PLANT 1.03->0.69/act, HARVEST 0.53->0.35. BUT 5-seed A/B
  25281 vs 36148 (-10.9k, every seed worse). REJECTED. Mechanism: under water
  saturation every water act is urgent; chain-plant STEALS water meant for a
  dying tile and gives it to a fresh sprout (priority inversion). Any
  reordering that delays water loses; only same-water-fewer-moves can win.
- Parity water (row-parity survival gate) + fert modulo: REVERTED BEFORE A/B.
  Reasoning flaw found in time: cu>=1 tiles skipped on off-parity days die
  (cu=2). Weeds didn't explode only via the stand-and-water backstop
  (crop_work L1720 waters underfoot regardless) + churn. Fragile, unexplained,
  cut. Lesson: survival-minimum watering has NO freedom (cu>=1 set is forced);
  only the phase pattern is choosable, and only via planting dates.

### DSM ledger mined (dsm_ledger.py + our_ledger.py, replay 112829119)
- DSM d0: $6 end, 4 hires, 2C+3S, M6+W12 seeds, 9W feed, 15 plants.
  d1: 9 HIRE emits (4 land!), fert 5 sold (~$500 = the whole early economy),
  melon +12 (wall 10). d2-3: straw 10+10 (10 standing d3), wheat cashed out.
  d4-5: fert 5/d, money $13->$367. d6 WAVE: wool 18 + land + 5C + 4G (herd
  5->12, structs 12). d7: fert 13. d8: milk 12. d9: land #2, +2C+3G, herd 18.
  d10: melon 36 sold, land #3 (tiles 100), money $148 (spent all). d11+:
  eggs 10/d, money 3x every 2 days. Fert embargo till d9 CONFIRMED (sells
  4-13/d throughout; applies d10+ but keeps selling).
- OUR divergence line-by-line: d1 HIRE 40 emits + emergency wheat 138 (retry
  flood; DSM 9+6); melon wall 6-7 (seeds bought 12 but req burned on broke
  emits -> no retry when cash lands -> morning starve); straw 4 days late
  (underbought d2-3); d6 NO wave (shopping has no animals; +1C vs +9);
  no geese ever (egg engine missing: DSM 10-27 eggs/d late).

### Scheduler variants (all pinned 5-seed vs 36148)
- var_sched (shortfall re-emit + melon8 + straw8/8 + P16 + d6 wave): 22858
  (-13.3k). Shortfall attempt-1 was a FAUCET (planter consumption re-opened
  quota: 50 melon/163 wheat churn). Attempt-2 wallet-cover fixed the faucet
  but kept the loss. d6 wave landed (herd 12 by d11) then escape treadmill
  d15-27 (herd 16->14->16, replacements burn ~$1k/cycle). Delivery ceiling.
- var_sched2 (no wave): 22858 IDENTICAL to the digit (reproduced twice).
  Learning: htgt was never the lever; feed_cap/room gates bind first, so the
  wave ladder is dead code under pin. (Ledger-vs-AB confound warning: ledgers
  run without LINE_FORCE -> different shop line. Only pinned A/B judges.)
- var_sched3 (wallet-cover ONLY): 24386 (-11.8k). Wallet-cover is the poison,
  mechanism unexplained (early ledgers look RICHER: d13 +$2.6k; mid-game
  earnings halve anyway). Morning starve is a SYMPTOM of thin wallet; moving
  buy timing moves the thinness + breaks hidden dependencies. REJECTED.
- var_sched4 (hire-gate: hires wait while seeds unfunded): 9657 (-26k), three
  near-zero seeds (84/696/462) + one +11k win (44400). BISTABLE Russian
  roulette: gate delays hires on exactly the stressed games where morning
  water is life-or-death -> weed death-spiral; when it survives, seeds-first
  pays big. REJECTED (variance disqualifies, mean catastrophic).
- var_sched5 (seeds-first ORDER: HIRE emission deferred after consumables;
  engine fills list order): 34262 (-1.9k, TIE). +6.7k/-18k/+15k/+1k/-14k.
  Real mechanism (scores move, no wipeouts) but zero-sum across seeds:
  morning-seeds vs morning-hands is a seed-dependent trade, not a free fix.
  PARKED (only non-harmful scheduler change; needs variance taming to adopt).

### Net mechanism learnt (load-bearing equilibrium)
The baseline's bugs form a mutually-supporting equilibrium: hires drinking
afternoon cash (covers labor), req-burn (caps seed spend), trickle herd
(fits delivery). Each isolated "fix" breaks a hidden dependency:
wallet-cover -> ? (-12k, unexplained: respect it); chain-plant -> steals
urgent water; wave -> escape treadmill; hire-gate -> death spiral. DSM's
d1 (4 hands + full seeds) vs ours (9 + starved) is a different POINT on the
labor-vs-assets frontier, not a free upgrade. NEXT: feed-delivery ceiling
(field-side: what lets DSM feed 20/d with the same crew?) is the one wall
that unlocks herd 15+ and DSM-scale assets. Everything else is rearranged
thinness. If delivery can't be fixed, ~36k is this architecture's optimum.

## Session 2026-09-25d — agent1/scheduler verdict + HERD LADDER (var_sched6) ADOPTED
- External proposals judged: agent2 REJECTED as evidence (tables formatted as
  measurements but untestable from outside; hire-price curve invented; C3 herd
  cap needs nonexistent sales/day plumbing and never opens). Agent1 USEFUL
  (honest predictions, respected all 6 DSM constraints, falsifiers per change,
  Change-3 matches our scale-trap lesson) with overrides: its engine
  "corrections" (wheat 1.0x, fert 1.5x) contradict our engine-source reads;
  its tomato 24-41 standing exceeds measured water capacity; its 8 marginal
  geese contradict our delivery-ceiling A/B. Adopted 2 ideas only: seeds-first
  deficit loop (= sched5, already parked) + day-cap herd ladder.
- var_sched6 (sched5 base + LADDER: total owned cap 5 d0-5, 8/9/10/11/12 d6-10,
  13 d11+, applied in BOTH groom and room calcs): 5-seed 41164 vs sched5
  34262 (+6,902, 4/5 up, worst -1.4k tie). 10-seed 39024 vs 34104 (+4,920 >
  3.5k floor): deltas +13.1k/+5.3k/+12.7k/-1.4k/+4.8k/+10.9k/+0.4k/+0.6k/
  -8.0k/+10.7k (7 up, 2 ties, 1 loss on 200009). Vs true baseline 33452:
  +5,572. NEW BEST. ADOPTED as the base for delivery-ceiling work.
- Census 200001 (reward 63413): herd climbs 5->6->7->8->12->13 EXACTLY on the
  ladder, placed==herd every day from d7, ZERO escapes after d6, shedW
  positive all game, money compounds d15 $4k -> d20 $18k -> d29 $60k, plants
  40-56 mid-game. Mechanism confirmed: fitting the herd to OUR delivery
  (not DSM's) kills the escape treadmill. One early escape d1->d2 (5->4).
- Net update: delivery ceiling is now CONFIRMED binding (herd 13 fits, 21
  doesn't) AND partially bypassed. Next: raise the ceiling field-side
  (feed-trip batching? dedicated feeder? dump-trip separation?), then release
  the ladder toward DSM's 21. Seed 200009 (-8k) is the canary: ladder too
  tight where early income could have supported more — a money-released
  ladder (cap lifts when wallet proves income) is the follow-up variant.

## Session 2026-09-28 — harvest-gate mining + late-crew fix (loop 4)

### Mined: DSM HARVEST yield_before histogram (pre-action tile state, 12 replays/24 sides)
CARROT  1:2625 2:778 3:1006 4:319   WHEAT 1:8646 2:2284 3:3507 4:630 5:1973 6:776
MELON   1:309 .. 6:308             STRAWBERRY 0:10846 1:396 2:2986  TOMATO 0:3344 2:1291
=> one-shots are flipped the MOMENT they are pickable (61% of carrot at yld=1).

### Mined: DSM carrot wave (PLANT:CARROT acts/side by day)
d17-19 66-130, d20-22 166-286, d23-25 310-719, d26 726, d27 314, d28 7. Stands
follow d20 3.4 -> d25 11.0. He plants 43.5 carrot/side; we planted ~0 (gap -91%).

### Mined: DSM crew curve (hands by day, mean 90 sides)
d6 9.0, d9 10.0, d15 11.5, d22 12.0, d28 10.5, d29 10.0. SUSTAINS ~10-12 to the end.
Ours: 12 to d25, then H(6) at d28-29 -> 10 -> 6. crew d29 gap -40% (biggest L1).

### REJECTED this session (all fail the score-blind keep rule)
- DROP-everything + reload (201, 3 variants): the reloaded wheat re-entered
  `bankable`, so DROP->PICKUP->DROP oscillated (1162 PICKUP vs DSM 198);
  terminating the loop left the reload firing on EVERY shed pass (PICKUP +223%),
  money d10 collapsed to $5, solo 3674 -> 123650 -> 107907. Root: one verb per
  step, and mirror-mutating inv while returning the verb double-counts.
- carrot wave + harvest-at-1 (202/203/204/205): carrots planted but NEVER
  watered (26/26 tiles stuck at yld=1, zero growth) because yld>=1 made
  HARVEST 8.0 outrank WATER 5.0 -> units camped and flipped the base yield.
  Adding "watered once" fixed growth (6/26 reached yld>=2) but score stayed
  flat (-1%) and H2H was -1607 (t=-1.91): the wave needs hands we don't have.
- wheat harvest at yld=1 (207): -6011 solo. DSM's aggressive flipping only
  pays at his crew size.
- fert buy skip pre-d9 (209): byte-identical (the buy path was already gated).

### ADOPTED — TRY 74 (my_dsm208 -> agent_current.py)
H(10) at d28-29 instead of H(6). Hands reset nightly but a d28 hand works
d28+d29, and d27 stands are wheat/carrot ready to flip.
  solo 141137 -> 142149 (+1012)
  H2H vs shipped opponent: margin-delta mean +604, sd 524, t=+3.99, 11/12 up
  parity: crew d29 -40% -> -0%; HARVEST -5% (OK); money d29 +36% -> +37%
SHIPPED to agent_current.py.

### Why DSM's aggressive harvest/turnover is NOT copyable piecemeal
His flip-at-yld=1 only wins because he runs 10-11 hands AND sells the same
day (SELL:WHEAT 778 vs our 387). With our crew, the extra harvest acts steal
water labor and the yield never grows. The carrot/wheat gates are correct
*behavior* but wrong *sequencing* for our labor budget.

### Remaining biggest gaps (post-74)
crew d29 CLOSED. Now: money d10 -26%, money d15 -29%, DROP -80%, dusk_wheat
-100%, shed_pickup +49%, SELL:WHEAT -51%, SELL:CARROT -95%, quad4_share +120%,
BUY_PRODUCT:FERTILIZER +364% (but byte-identical when gated -> already dead).

### REJECTED — TRY 76 (land gate on true price + $1500 buffer)
money d10 -26% -> -19% and solo +781, but H2H margin-delta mean -1247 (t=-1.57)
with 6/12 seeds BYTE-IDENTICAL (quad4 was never bought there: the gate only
fires on the rich seeds, and there it HURT: 300007 -7318, 300008 -5927,
300009 -2210). The $4000 quad 4 PAYS when the wallet can cover it; DSM's
45.6% quad4 rate is a symptom of his thinner per-game wallets (H2H price-war
replays), not a preference. Our gate path was correct. REVERTED to 208.

### Keep-rule sharpened this session
H2H with dm=+0 seeds is diagnostic: when a change is a pure wallet gate,
the unaffected seeds must come out identical, and the affected ones are the
ONLY evidence. A solo gain on 3 seeds can be an artifact of which seeds are
"rich". Score-blind parity on money d10/d15 is NOT automatically keepable --
money +37% at d29 already says we hoard late; matching DSM's thinner mid-game
wallet would copy his scarcity, not his skill.

### REJECTED — TRY 77 (wheat harvest at yld>=1, retried on TRY74 base)
solo 142149 -> 136142 (-6007). WATER is unchanged (999 vs 995) so it did NOT
steal water labor -- it churns tiles: each yld==1 flip resets the tile and
throws away the 2-6 yield accumulation. Sold wheat FELL 317 -> 290 despite
more HARVEST acts (444->495). DSM's 61%-at-yld=1 harvesting is a scale effect
(10-11 hands + same-day sells); at our crew the yld>=2 gate is correct.
SETTLED: wheat gate stays yld>=2. The 355 unharvested units at d29 are a
crew-labor cap, not a gate bug.

### Loop-4 net
TRY74 SHIPPED (crew d29 -40% -> 0, H2H +604 t=+3.99). Everything else tested
rejected on score-blind keep rule. agent_current.py = my_dsm128 + TRY74.

### FINAL STATE — loop 4 close (agent_current.py = my_dsm128 + TRY74)
solo 5-seed: 153842/144889/127715/152763/139559 mean 143754 (was 141137 on 3)
parity closed this loop: crew d29 -40% -> -0% (the biggest L1 gap)
H2H vs shipped: margin-delta +604 sd 524 t=+3.99 (11/12 up)
L1 now all-OK except crew d0/d1/d5 (noise, +-12-15%).
Remaining open: money d10 -19%, d15 -29%; DROP -80%; dusk_wheat -100%;
SELL:WHEAT -51%; SELL:CARROT -95%; quad4_share +120% (mined: deliberate).
Tooling added: replay-tile mining scripts (yield_before, stand curves, crew,
quad-tier, plant-wave). KEY LESSON: DSM's harvest-at-yld=1 and carrot wave are
SCALE EFFECTS tied to his 10-11 hand crew + same-day sells; copying the verb
without the crew loses money. The crew fix was the prerequisite; revisit the
carrot wave after another crew/labor improvement, not before.

### REJECTED — v308/v309 (emergency wheat daily cap 12, d0-2)
6-seed: 132286 sd 24934 vs 208: 142782 sd 9013. Mean -10.5k, VARIANCE x3
(300003 95k, 300006 102k collapse). The d1 44u wheat flood is load-bearing
SAFETY STOCK, not waste: capping it strands d1-2 feeding on some seeds and
the game is unrecoverable. Escape exemption never fires (collapse is not
escapes: herd 21 vs 25 from d15, buys stall on rich wallet -- lottery loss
in daycap/delivery pipeline). LESSON: 3-seed means are noise (+-9k); all
future keeps need 6-seed t>2.

### REJECTED — v310 (wave-plant 6.9 only, labor reallocation)
6-seed: 134278 sd 13935 vs 208: 142782 sd 9013. Mean -8.5k. Re-broke v11:
6.9 > WATER 5.0 marches units past thirsty wheat in its 3-day window
(age 2-4, a day late = -1u forever). Water timing is SACRED; no intervention
may delay any watering. Only free labor is moves + PASS-idle.

### NEUTRAL — v311 (carrot seeds 8->2/d d13-27)
6-seed: 142720 vs 208: 142782 (-62, all seeds within noise). $1680 dead
capital confirmed: cutting 75% of carrot seeds costs NOTHING -> the planter
(~2/d) is the binding constraint everywhere (melon stands, straw conversion
50%, carrot wave). Next: fix planter throughput WITHOUT breaking water
timing (v310's lesson). Idea: role-split by unit index (planters/waterers).

### REJECTED — v312 (role-split wave planting by unit index)
6-seed: 138561 sd 14030 vs 208: 142782. -4.2k. Changed nothing (PLANT 241
vs 246, stands identical): seekers still lose to cu-WATER 10.0, and the
deficit/seeds gating means the boost rarely matters. Planter path cursed
via priorities; needs structural (route/dedication) rethink, not values.

### REJECTED — v313 (farmer-planter i==0 @6.9)
3-seed 139620 (-2.5k). Farmer planted 32 straw d3-13, stands 0.0: marched
plantings never get same-day water (cu=2 overnight -> WEED). Iron law:
every planting MUST pair with water or it dies. Distant/late plantings die.
Planter fixes via priorities are DEAD; needs plant-water coupling (route or
near-only + waterer coverage). Pivoting to WATER ALLOCATION audit.

### REJECTED — v314 (d0 fifth hire H(5))
3-seed 102276 (-40k!), melon stands 0.0. The 5th hire order crowds the
10-slot market (5 fail-retried HIRES + 2 animals eat slots while broke) and
seed orders starve all day. d0 ordering (hires-before-seeds) cannot take
5 hires. d0 is SEALED: H(4), 2C+3S, melon 6. Touch nothing.

### REJECTED — v315 (fert carry from d6)
6-seed 137740 vs 208 142782 (-5k). LAND buys 3-in-3-games (should be 9):
d6-8 fert carried not sold = cash dip kills quad2 on some seeds (300006
-30k). Land cash sacred too. Reverted.

### NEUTRAL — v316 (d0-1 hire burst, trickle removed)
3-seed BYTE-IDENTICAL to 208. d0 timing truly doesn't matter (slack day;
seeds are the cap, not labor). Killed.
### LESSON (v308/9 autopsy): the d1 wheat flood is INFLATION HEDGE + safety
(wheat $25->$40; capping forces later expensive buys = double loss). NEVER
CAP. d0 wallet closed from every direction. Attack d12-29 only from here.

### REJECTED — v317 (pasture 15 / coop 6 build caps)
3-seed 118720 (-23k). Caps block housing OUR 20-mouth herd needs (8C+12S=20
> 15): animals unplaceable -> buy-freeze -> death spiral. Sprawl is required
housing for our line, not waste. (Would only work WITH the herd cut, which
loses solo.) Reverted.

### REVERTED — v321 (rescue lane: urgent 10.0 outranks distance)
FINAL 92037 (-35k). Lane diverts harvest labor map-wide at payday (d10 money
5 vs 878; units walk past RIPE melons to water far wheat). Priority inversion,
not DSM behavior. Lesson: his rescues succeed via SHORT walks (compact
field), not high priority. Compactness is the prerequisite link.

### SUPERSEDED — v322 (compact plant: no far planting while near empties free)
quads=3 (payday gate bound: his q3-49 branch ✓) but wheat collapsed d20 9
(quota T/C eat turnover + compact blocks refill) and near empties still unfilled
(planter labor shortage, not coverage). Score 104167. Lesson: compactness
without turnover priority starves wheat. Wheat program is next link.
### CHAIN CORRECTION: melon yield is load-bearing for everything downstream
(his d15 22k <- melon 60u d10 ~$15k; ours 34u ~$8.5k -> -6k hole). v304 failed
for lack of labor; herd cut now frees it. Retry melon window WITH freed labor.

### REVERTED — v323 (melon window water 9.2 d6-12)
FINAL 22320 CATASTROPHIC. 9.2 diverts d6-9 harvest income (wave funding) ->
cascade; melon even worse (2.44u, feed gaps). Priority surgery in the wave
crunch kills. Lesson: NEVER outrank harvest/income during funding crunches.
Melon gap is TIMING (his mass-pick d10-11; ours drifts to d12), not water.
### BASE RE-AFFIRMED: v320 is 80% DSM (wheat 20/21, straw 28/27, money 51/54k,
herd exact). Remaining: tomato 7->15, carrot 2->8, melon timing. All three
are water-coverage/dusk-labor problems. PASS 270 acts h20-23 idle vs DSM 359
total PASS: dusk labor is the free pool.

### v324 6-seed: mean 130499 sd ~20k vs 208 142782 sd 9k. NOT shippable solo.
Behavior consistent (T8-9, C3-4, S24-29 all seeds) but 300003 collapses 88k:
ahead d15 (+$5k) then d15-20 wool gap (his 12 sheep earn ~$18k wool d15-20;
T/C can't replace per-act in SOLO). DSM mix is H2H-optimal by design; solo
score stays depressed until package complete. Validation = behavior + H2H,
not solo. Continuing forward per directive.
### NEXT LINK: quota precedence starves wheat (T 2/d + C 1/d take first plant
events; wheat d20 13-19 vs 21). His wheat steady = wheat-secure. Gate quota
on wheat deficit <= 3.

### REVERTED — v327 (morning rescue lane for cu1-water)
Stands NEAR-PERFECT (300003 d20 W23/S31/C7/T8 vs DSM 21/27/8/15!) but score
collapsed (99k/82k/99k) and DIG ROSE to 72-78: plant->die->replant CHURN
(300+ plants feeding deaths) burns harvest labor; money d20 27-45k. Third
proof (v321/v323/v327): priority-over-distance causes herding/churn/cascade.
LAW: all coverage fixes must be POSITIONAL, never prioritization.
### NEXT: v328 = v326 (best balance) + force-q3 (compact by construction).
His q3-49 sides prove 75 tiles suffice; q4-38 scale question later.

### EXAM BACKTRACK (H2H vs pipe19, seed 300001): T/C is a diversion
PIPE runs ZERO T/C, doubles our money (120k vs 62k) with S33/W25/melon-payday.
DSM runs T15/C8 AND S30/W23. Common gap vs BOTH: straw -9, wheat -7, melon
payday d10 (8 vs 2288), herd 21 vs 17. Our quota T/C d10-15 EATS the straw
ramp plant events (straw +4 vs +13 d10-15). Straw is senior; T/C is surplus.
PKG11: straw-secure gate on quota (T/C only when straw deficit <= 4).

### HIS MIX (mined PLANT/side/day): wheat 5-9/d EVERY day (fast flip), straw
ONLY d10-13, tomato ~1/d d10-20 then 0, carrot ~1/d then 2-8/d d22-26, totals
flex 7-15/d (d11: 15, d22-26: 12-13). d11 spike = melon mass-pick frees 10
tiles (opportunity, not priority). Our flat-8 + slow-flip can't flex.
PKG12: melon mass-pick d10-11 (all ripe, his window) + tomato quota 2->1/d.

### Bunching EXCLUDED (units spread; his h13 backlog 51 > ours 36). Residual
deaths = DRIFT: corner crews wander off 2+ days, far tiles double-miss.
v321's poison was lifting URGENTS (herding); water-5.0 lift is safe (low val:
binds only when no near work, else nearest wins). PKG13: water-only lift.

### ENGINE ORACLE (animals): escape at cu>=2; production base ticks REGARDLESS
of feed (bonus needs fed_today). Alternate-day feeding SAFE (cu<=1), keeps
base output, halves feed acts. His FEED 13/d (65%) = this. PKG15: feed iff
cu>=1. Priced: -7 acts/d late + wheat saved; bonus halved (~neutral solo,
pure win H2H).

### FEED PROFILE (mined): daily d0-17 (15-16/d = full herd), alternate d18+
(11-13/d), terminal stop d28 (4.7). NOT alternate throughout -- bonuses fund
the d6 wave (daily), taper funds the d20-26 plant wave. PKG15 corrected:
daily d0-17, cu>=1 d18+. (v334/335 crater: -28k, d10 money 6 -- spike killed.)

### v336 STILL cratered (96k/85k, herd d10 = 5 = NO d6 wave). Daily feed
restored yet collapse persists -> breaker elsewhere in v334-336 diff. BISECT:
v336a = v333 + hunger-cu x3 only; v336b = v333 + feed gates only. d10 snap.

### BISECT DECISIVE: hunger-cu x3 killed the wave (v336a herd d10 = 5, no wave;
v336b healthy = v333 baseline). Path: cu-gated loading starves pockets ->
rule1 (daily, needs wheat) can't feed -> bonuses die -> spike dies -> no wave.
Hunger patches valid only in alternate-day world; under daily feeding poison.
REVERT all three. Keeper = feed-gates-only (v336b -> v337): logistics stay
daily-assumption, rule1 skips cu0 d18+.

### STACK-WIPE (engine): unfed production day RESETS pending_care_bonus to 0
(bonus lost, not banked). Alternate-day feeding halves stacks -> animal
revenue -32k d20+ solo (milk -16k, wool -12.5k, egg -3.5k). Freed 315 acts
DISSIPATED (PLANT FELL 257->229!). DSM's taper is H2H-correct (bonuses sell
at $1 in price war) but solo-fatal. DECISIVE: H2H v333 vs v337 (2 seeds each)
-- keep iff v337 wins the exam.

### REVERTED PKG15 (v337 loses both: solo -32k animal stack-wipe, H2H -72k vs
-53k). Base = v333. Freed feed labor DISSIPATES (never converts to plants);
keeping daily feeding (stacks sacred). Taper is his H2H luxury, not ours.
### EXAM GAP: H2H d10 money 8 vs pipe 2288 (solo 249). Shared shops: pipe sells
first, prices crater, we get crumbs. FIX: sell FASTER d10 (mass-pick +
same-morning bank+sell). v338 = v333 + d10 melon-seek 9.0 (harvest-first
accelerates income; safe direction).

### v338 d10 melon-seek: H2H byte-identical (harvest not the constraint; the
gap builds d10-15 = straw ramp +4 vs +13). His d11 plants 15 (opportunity:
10 melon empties); ours waters instead (v11 water-first caps opportunistic
planting at ~8/d). PKG17: empty-gated plant-first (empties>=6 -> plant 6.0;
else 4.5). Flex 8->15 on empty-rich days only (v310 blanket failed; gated).

### d15-20 wound MATH CLOSES: demand (flip 5 + T/C 2 + churn-replant 2 = 9/d)
vs supply 8/d = -1/d x 5d = -5 wheat. His 9/d balances (churn 1.2/d); ours
9.5/d doesn't. Levers: cut churn (positional, exhausted) or cut flip demand.
PKG18: slow flip (wheat ripe yld>=3): demand 5->3.5/d, bigger harvests, fewer
acts. Risk: feed pipeline (measure BUY wheat).

### REVERTED PKG18 (slow flip yld>=3: 130k/101k, DIG UP 63, velocity dies).
His fast flip is load-bearing (cash velocity). Demand 9/d fixed; supply must
rise. REVELATION: under nearest-first, values 4.5-9.0 are MEANINGLESS
(0.09 weight; distance decides). Only on-tile rules + >=9.5 lane + POSITION
matter. All value-tuning was theater. Plant throughput = rule-3 (stand on
empty). Measure rule3-vs-seek provenance next.

### LEDGER d15-20 (v339): wheat plant 39 / harvest 35 / stands -6 => 10 wheat
deaths (2/d, young, days 2-4 water). Rule-3 plants 83% (position OK); drift
kills days 2-4. PKG19 NURSE: planter stays near newborn 2 days (sticky
position, no global priority change).

### v341 nurse: byte-identical (pull too weak to fire; -d+0.45 rarely beats
best). 20 variants, behavior 80%, resistant gaps: wheat -6, carrot -6,
tomato -7, H2H -53k. NEW MOVE: mine his POLICY (per-decision features), not
aggregates. P(water | cu,age,crop) + P(plant crop | context) him vs us.

### HIS WATER POLICY (mined P(water|cu,age,crop)): RESCUE-PHASED. Wheat/carro
/straw = water at cu1 (rescue, always) + window-finish (W age3-4, C age3);
routine young watering ~ZERO. Melon = routine window (high value). Ours =
routine-phased (waste acts on cu0 young) + failed rescues. SAME volume,
OPPOSITE phase. His fast wheat flip (yld1) is COUPLED (1 water -> harvest).
PKG20 phase-flip: young routine 2.0, window-finish 8.0, wheat yld>=1, cu1
10.0 main mode, straw cu0 2.0. Abort if DIG>80.

### v344 (flip-matched rescue-phase): REJECTED 131722/100112 (-17k/-3.5k).
SOUTH +85, FEED -25, CARE -28. Rescue-phase theory right about him, wrong
for us (our spread fields make cu1-rescue a march; his compact quads make
it cheap). PREREQUISITE CHAIN: compact FIRST, phase SECOND. BISECT PKG20:
v345=v341+finish-only, v346=v341+young-cut-only.

### BISECT: v346 young-cut = byte-identical (planter same-day water covers;
NEVER BINDS, killed). v345 finish-only = 141209/101076 (-7k) DIG46 best but
SOUTH+ feed- labor dies. Phase pieces fail on WALKS not agronomy. CONFIRMED
binding constraint = DISTANCE (spread fields); his prerequisite = COMPACT
(q3/q4 mix). Next link: match his quad MIX {3:49, 4:41}, not all-q3.

### v347 quad-sticky REJECTED 138822/100359 (-9.7k). Hysteresis cages
stragglers (W+51, S+131); cohesion must be SHARED assignment, not individual
stick. New mechanism hypothesis: cu1-rescue 10.0 TIES hungry-feed 10.0 ->
nearest wins -> full-herd days (d15-20) feeds everywhere beat rescues ->
drift double-miss clusters exactly there. Mine P(rescue|d) him vs us.

### HIS d15-17 hours: FEED dawn-heavy (h3-11, done by noon), WATER dominates
afternoons (h12-23). TEMPORAL SEPARATION (phases as units = time phases).
Ours interleave all day -> tie-fights -> rescues lose near herd -> drift
deaths cluster d15-20. PKG24 dawn-feed round (hungry map-wide 10.5 h<12,
touch-only after) + PKG21 escape 12.0.

### v348 dawn-feed round: SPLIT 153665(+5k)/99575(-4k). Tie-fights solved on
good seed; bad seed loses harvests to morning marches (HV-34). Disease is
d15-20 (full herd); early touch-feeding was fine. v349 = gate day>=10.

### v349 day-gate: 144777/101371 worse both ways. STOP tweaking; 6-seed
verdict v341 vs v348 (score-blind rules: keep needs t>2, no regress >10%).

### 6-seed v341 vs v348: 137702 vs 138916 (+0.9%, t~0.25) REJECT v348 (noise,
DIG flat-worse). Base=v341. CRITICAL CHECK: v341 137702 vs 208 142782 (diff
seeds!) -- run 208 on 300001-6 fair fight.

### Fair fight 300001-6: 208 142782 vs v341 137702 (-5k, -3.6%, t~-0.8 n.s.,
collapses 300003/4). Chain = behavior+ (DIG55 vs 67) score- (n.s.). Per
loop-3 score-blind contract v341 stands as behavior base. EXAM: paired H2H
v341 vs 208 vs pipe19 (the only verdict that matters).

### v351 unsaturate+escape12+rescuePM11: identical (S-1 noise). Hierarchy
doesn't bind -> contested-tie hypothesis DEAD. Deaths aren't tie-losses.
Mine OUR death geometry: nearest-unit distance day-before-death (far =
coverage hole -> spatial assignment; near = value bug).

### ROOT CAUSE (measured, not guessed): 34/35 deaths had a unit within 2
steps all day. On-tile rules 2/3 fire BEFORE seek and never compare: unit
waters own routine cu0 / plants on empty while the neighbor dies. His agent
has no on-tile priority (every step = fresh nearest-need incl own tile).
FIX v352: after animal rule, yield to adjacent (<=2) cu>=1 rescue via seek.
Planter newborn (cu0) unaffected.

### v352 rescue-yield CATASTROPHIC 43402/57206 DIG161 W330. Adjacent-yield =
herding cascade -> routine backbone killed -> death spiral. IRON LAW: on-tile
routine water is LOAD-BEARING (quiet 60%+); never bypass globally. Adjacent
deaths (35/g) need scheduling, not priority. REVERTED. Base=v341.

### v353: v352 minus herding. LOCAL compare (own routine value vs adjacent
rescue), routine-only yield (harvest/animal/shed never), single STEP (not
full seek). Only adjacent units participate (the neglecters); no marches.

### v353 local-compare: DIG41/41 (deaths FIXED -19/-15!) but score -19k/-27k.
Rule-3 yield stole the planter (PL-25: a wheat plant lifetime $90+ beats a
$30 rescue). Planting > rescue economically. v354 = rule-2 (routine water)
+ weed only; rule-3 never yields.

### v354 rule2-only: DIG48/50 PLANT kept, score -18k/-2.5k W-100. Stepping
units get distracted by landing tiles (rule-3 plants mid-route); rescues
still die + routine disrupted. v355: PERSISTENT rescue-step (st['rsq'][i]
until arrival; bypass 1b/2/3 en route; animal/ripe still fire).

### v355 persistent: DIG50/58 score -18k/-2k W-120. Rescue-yield hijacks the
planter-tender (PL-16). Deaths are cheap ($1k plants); cure cost 18k. But
stands need net births>9/d (his 8.3, ours 8.3, deaths decide). v356: exclude
nurse-marked tenders/planters from yield (idle carriers do rescues).

### v356 full delta: +360 walks / -83 water / -20 plants for 17 rescues.
Yields over-fire hundreds of times (STRAW cu1 = normal cycle, not emergency;
8 straw deaths but hundreds of chases). KILL scope: PKG28e ONE-SHOTS ONLY
(wheat/carrot/melon 23 doomed); ongoing never triggers. v357.

### v357 money trace: hole opens d13-14 (first milk/wool payday!). Rescue
hijacks carriers MID-ROUTE (standing on field tiles en route to herd);
production-day feeds missed; leveraged animal revenue dies. LAW: animal
rounds UNTOUCHABLE. v358 = loaded units (any pocket inventory) never yield;
idle/empty units only.

### v358: 151656(+3k)/102095(-1.5k) DIG48/55. First green on good seed; animal
rounds saved by loaded-exclusion. PL-14 persists: COMMITTED walkers cross
empties without planting (persist bypasses rule-3). v359: plant en route
(rsq retained; 1-step delay harmless intraday).

### v359 plant-en-route: 149557/102095 -- WORSE than v358 (151656) on good,
same bad. STRIP PKG28g (back to v358 = rule2+weed yield, tender+loaded
exclusions, persist). 6-seed v358 vs v341 verdict now.

### 6-seed v358: 138697 vs 137702 (+0.7% t~0.6 n.s.) DIG48.7 vs 54.7 (-11%).
Strict keep needs 50% closure (got 25%) -- REJECT as ship, BANK mechanism.
Stronger form: strip persist (committed marches cost PL-14); single-steps +
exclusions only. v360.

### v360 no-persist: 147472/101661 DIG48/57 PL-7/-13. Yields delay planter
circuits; 300003 saves nothing (far-drift geometry, wasted walks). Throttle:
yields AFTERNOON ONLY (h>=12, his water phase; mornings protect planting).
v361.

### v361 afternoon-gate: +0/-12k SEED ROULETTE. KILL PKG28 line entirely.
ARCHITECTURE verdict: deaths floor ~55 emergent; local grabs rebalance
unpredictably. Genuine clone = HIS AGENT SHAPE (no blind on-tile; every step
fresh scored decision incl own tile). v362: seek includes own tile (d0);
remove 1b/2/3 (keep animal-1 capital, shed-4 income, mass-pick proven).
Abort if score<-10k or DIG>80.

### v362 SKIPPED by math: own-tile d0 (0.45) beats neighbor rescue d1 (-0.1)
in scored-seek too (0.09 scale forbids altruism: max diff 0.9 < 1.0 dist).
His answer is PHASES (sweep = routine; nothing competes). v363 = FULL
time-phase package (cap12 + feed-AM 10.5 + rescue-PM 11.0); pieces were
no-op alone, coupled they separate tie-fights.

### v363 full time-phase: 144698/103026 DIG55/48. FIRST both-seeds-right
(DIG down both, score ~flat -1.7%). Time-separation works where priority
failed. v364: AM rescue 9.5 (full split AM=feed/PM=water; cu1-at-dawn still
rescued PM same day, in window).

### v364 AM9.5 = byte-identical to v363. AM tie-fight doesn't exist; v363
gain = PM11 alone interacting with feedAM (v351 without feedAM was no-op).
Keep v363 whole. Measure rescue-rate v363 vs v341 (was 0.59).

### v363 rescue-rate flat (0.62 vs 0.59) but MORE chances (53 vs 37, AM
deferral). DIG gain may be drift-luck. 6-seed verdict (have v341 137702).

### 6-seed v363: 138979 vs 137702 (+0.9% t~0.24) DIG58.0 vs 54.7 WORSE.
2-seed gain was luck. REJECT. v350-v364 all dead; base=v341. STOP death
chase (floor ~55 emergent); verify stands arithmetic directly: measure our
d15/d20 wheat/carrot/tomato vs his medians (mix vs deaths?).

### Stands autopsy (v341 vs his medians): d15 straw -6 (29 planted, LOSE 6:
tending, not count), d20 wheat -6 (174 OVERplanted vs ~150, deaths eat
surplus), tomato -5 (12 vs ~18 UNDERPLANT: rhythm loses to wheat deficit),
carrot ~90% death (3d window + drift; his 69% survive, ours 10%).
REBALANCE (not labor-add): wheat cap ~150, tomato quota-FIRST, straw tend.
v365: tomato quota-first + wheat want cap.

### v365 full ramp: 148257/101431 DIG79/52. Ramp fed drift (+19 deaths good
seed: interim births untended). Volume x tending coupled. v366: ramp TOMATO
ONLY (underplanted -5, ongoing persists if watered); wheat/carrot stepped
(no extra doomed births).

### Fresh d20 (300001): W15(-6) S27(ok!) T8(-3, was -5) C3(ok! his 3.4).
Carrot gap was STALE (v318 era); current parity (births 22~20, stands 3~3.4).
Remaining: wheat-6, tomato-3, straw-6(d15), DIG cost +5-6. 6-seed v366 (have
v341 137702/DIG54.7).

### 6-seed v366: 137853 vs 137702 (+0.1%) DIG59.5 +9%. REJECT (300003 was
luck). v365/366 dead. New: ADAPTIVE wheat flip (his yld1-6 spread = mixed
strategy, not threshold. Fast flips are IMMORTAL (3d cycle < 2-miss death).
Rule: missed-once (cu>=1) -> flip yld>=1 (cut losses); never-missed -> grow
yld>=3. Same harvests, different timing, zero extra labor. v367.

### v367 adaptive flip: 95678(-53k)/124815(+21k) INSANE variance. Flip speed
couples whole economy; uniform yld>=2 stays. REJECT. New: OVER-CARE (we 413
vs his 332; bonus caps at maxheld, excess wasted ~80 acts = planter +1.5/d
= wound closes 8->9.5/d). v368 = skip care when bonus capped.

### v368 cap-skip: 148388/97316 CARE-17 only (bonus rarely AT cap; production
pays it out). Arithmetic proof: his care rate 0.58 = production rhythm
((5*1+8*.5+6*.33)/19 EXACT). He cares ONLY on production-due days (labor >
stacked bonus). v369 = rhythm care (due-day via placed_day/first/interval).

### v369 rhythm-care CATASTROPHIC 104335 (-44k). Care/feed/collect are a VISIT
BUNDLE (touch opportunism); gating care killed visits -> FEED -50 -> wipes.
LAW: bundle atomic, gate neither separately. REVERT. Next: PASS gap (we 552
vs his 359 = +191 idle!). Measure our PASS-by-hour vs his.

### PASS autopsy: ours ramps PM (h14-23 idle 23->75); his PM = WATER+PLANT
(his planting h12-21!). INVERSION: we finish everything AM, idle PM; his AM
skips create PM work. SAFE shift: PM-planting (same-day water covers d0,
AM routine d1, no drift). AM planter tends (drift falls!) + PM planter
plants (idle->work). v370 = seek-plant 3.0AM/6.5PM + rule-3 PM-only.

### v370 PM-shift: 133772/82313 (-15k/-21k) PL+ but DIG+ churn (AM empties
abandoned, commute kills). REJECT. PM-idle structural (AM thoroughness);
sweep needs rescue-phase (v342 economics broke). PARK. Narrow: STRAW water
senior 6.0 (d10-15 blossom crowds straw water -> 8 straw deaths; straw =
cash crop). v371.

### v400 PKG40 94237(-54k)/105614(+2k). Saver worked (W753, CARE173) but labor
sank to PASS+450 (plant capped, no patrol) + animal revenue died. His volume
1124 = FULL patrol; phase/triage (not volume!) is his edge. DIAGNOSE links
before salvage (econ/stands/herd-products).

### v400 autopsy (econ_days 300001): d7 money 0 vs 341 (broke: barn visits
collapsed -> milk unharvested -> no d8 buys -> herd 7 vs 14 d10 -> spiral).
Milk/wool sales -200u (~-$30k). SOLO MONEY WE WIN ANYWAY (148k vs 105k):
money never the problem; field is. SALVAGE v401 = window-7.5 + feed-due-9 +
d28-thin-to-due + carrot-fert + nurse-gate; REVERT care-rhythm, skips,
total-abandon, rule2-mirror (on-tile water always: position-free).

### ROOT CHAIN (code-read): SELLABLE order = PRODUCTS (wheat first) + 4-sell
cap -> wheat fills slot 1, milk/wool (pos 7-8) cut off -> stranded -> shed
cap 100 -> discarded. Window-7.5's +wheat crowded milk (-18 ≈ -$3k + crash).
v402 = v401 + value-first sell order (MILK/WOOL/EGG/MELON/S/T/C/FERT/WHEAT).

### v402 value-first sells 145612/92943: NOT the mechanism (worse). Window
effect seed-fragile (+0.6k/-7.8k). Discipline: price each fork ALONE.
v403=feed-due-only, v404=carrot-fert-only, v405=nurse-gate-only.

### MATH: nearest-first (0.09) makes triage beyond ~1 tile IMPOSSIBLE (needs
dval>78). His sweep walks past near-safe to far-dying. v406 = water-seek
value-first ONLY (val-0.3d for WATER; rest unchanged). Prices triage alone.

### v406 WATER-TRIAGE (value-first water): DIG 43/33 (-17/-23, 33~=his 36!)
but HV-150, FEED-130, score -86k/-36k. PROVES thesis both ways: triage is the
deaths lever AND values can't buy it (global lane starves harvest/feed).
Remaining architecture = phases/roles (time-division, not priority scale).
v327 role-split already failed; phased rewrite = big risky job. PARK.
### FORK PRICES (upgraded backtrack ledger): window-7.5 +0.6k/-7.8k; feed-due
-3.3k/-7.7k; carrot-fert -2.3k/-0.5k; nurse dead; thin dead; care-rhythm -44k;
skips -54k; sell-order -3k; triage DIG-23/HV-150. ALL REJECTED. v341 stands.

### v500 phased water: 133499(-15k)/118276(+14.6k). Acts collapse everywhere
(W-140 HV-70 PL-20 FEED-50: triage-marching eats the day; travel>work). His
rescue-rate 0.59 = accepts far deaths. v501 = bounded triage (PM val-0.3d,
d<=6; far-dying accepted, march waste capped).

### v501 bounded triage: 135215/108496. Deaths 47/44 (gap -19->-10!) but
FEED-50 (PM barn abandonment) + HV/PL down. FIX: wheat-carriers exempt from
triage (stay shed-barn loop, feeds hold). v502.

### 6-seed v502: -6874 t=-1.99, loses 5/6. REJECT phase-water (marching tax >
triage gain; 300001 geometry overfit). v341 stands. Remaining architecture:
AM-radius positioning (v503) + H2H exam (v341 vs pipe19 unmeasured!).

### SPLIT THEORY: 300003 barn-heavy (8G/9C) starves when labor->field; 300001
balanced gains. FIX: barn-first-AM + field-PM (his shape: feed dawn-heavy).
H2H v341 vs pipe19: -65k/gm (DSM himself -49k; gap -16k). v504 = AM barn+3,
PM bounded-triage.

### v504 barn-first-AM: 97180/89808 CATASTROPHIC (FEED-90: far barn-pull =
herding, v321 law). Values can't do barn-first (near=status quo, far=herd).
Needs ROLE: farmer-herder (spawns shed-adjacent) when crew>=7; hands
barn-blind seek (on-tile free). v505.

### v505 lone-herder: 111591/91642 (1 unit < 55 barn acts/day; needs 2.3).
v506 = herder TEAM (units 0-2, crew>=9) AM-only (h<12); PM all normal (barn
done, no idle; field owns PM).

### v506 team-AM: 131225/99342 red (blind crew's lost touches > focus gain;
opportunism beats roles for scattered touch-work). KILL role line. v507 =
v341 + all-day bounded water triage (d6, val-0.3d) + carrier-exempt; NO
AM-cap (v502's AM-cap starved volume), NO phases.

### v507 all-day triage: 140514/100039 (HV+ but score red; bounded march
pays tax, saves nothing). KILL triage. Tally: values/phases/roles/triage/
sells/positioning ALL <=0. v341 = hard local optimum. New axis: split may
be LINE-conditional (DSM is line-conditional: d6_branch). Map line x seed.

### Split NOT line (within-line splits both ways) = geometry/RNG. No
conditional variant. Untested: HERD 20 vs 19 (we run +1 goose = +25 acts +
egg-cap pressure; his 8/6/5). v508 = goose cap 5.

### v508 goose-1: +4.8k/-4.5k split (helps sheep 300001, hurts mixed 300003?).
v509 abandon: +1.9k/-0k (barely binds). 6-seed truth for v508 + sheep-gated
v508b in one batch.

### 6-seed: v508 -1631 t-0.54 REJECT; v508b +528 t0.59 (n.s., within-line
split kills conditionality). Last compound: v510 = v508b + v509 (weak-positive
stack, different mechanisms). Then report.

## Session 2026-09-28 (gap closure, 6-seed contract): 11 variants, all rejected

Baseline re-verified: my_dsm341 6-seed mean 137702 [148507,150337,103656,125567,161751,136393].
Engine oracle re-verified from source (water window, cu>=2 death, new-plant cu=1).
DSM death ground truth re-mined: median 23/side (was "37" = DIG count).
Our deaths median ~37 (+14); births: carrot 12 vs DSM 27, wheat 47 vs 55.
Wheat yield avg 2.38 (engine max 4/6) but raising the harvest gate LOSES (turnover).
PASS 552 vs DSM 336, concentrated h17-23 + d2-d7.

v600 wheat harvest age>=4|yld>=4: -28274. v601 yld>=3: -21253.
v603 water radius 12->17: identical. v604 drop far WATER reservations: -1006.
v605/v606 rescue val/cap lift: identical. v607 patrol: -2825. v608 nurse pull: identical.
v609 carrot quota 6->10: identical (wheat-deficit gate blocks).
v610 d26+ liquidation floor: solo +3, H2H -6.2k/g. v611 weak-quote throttle: -2570, H2H -13k/g.
H2H vs pipe19 confirmed -56.7k/-61.8k/g (seeds 200001-2). Throttling volume makes H2H
WORSE (pipe19 buys our cheap goods). The H2H gap is structural, not a trading bug.
BASE STAYS = my_dsm341. Next: new idea (carrot wave or unit assignment), not tuning.

## 2026-09-28 session: rate-swap + turnover (BASE NOW = my_dsm343.py)
- v700-702 zoning rejected (neutral/-6.2%/-1.8%). dsm800-802 rewrite halves
  rejected (800: deaths 45/43/48; 801: t=-0.38; 802: wheat 27).
- dsm803-808 rejected: tomato->carrot swap w/o wheat cut (-2.6k), feed rotation
  (escapes), travel-light DROP (-17k), wheat-carry 8 (escapes), PM plant-second
  (deaths 51/57/60), tile stickiness (stale locks).
- 809 TRUE RATE-SWAP (tomato off, carrot quotas 1/3/6/9 ungated, wheat cap 5/d
  d20-26, feed buys kept): deaths 40/35/42 -> 24/20/27 (6-seed mean 36.7->24.2).
- 810 early carrot dribble d1-11 REJECTED (wheat deaths up, straw up, escapes).
- 811 CARROT TURNOVER (ripe yld>=2 & age>=2): 27/31 carrots expired EOD age 3 =
  maxday with yld 3 banked ($0). Carrot $489->$1756 (s3), seed3 +12.9k.
- 812/813 adaptive caps REJECTED (dawn-cu signal = field size, not scarcity;
  812: seed6 -8.3k; 813: seed5 -5k). 814 cap 6/d: helps s1/s5/s6, hurts s3
  (seed-overfit, rejected). 815 melon full-yield wait +265 (noise: melons lack
  window WATER not time; parked). 816 deeper swap 4/d: seed6 -4.5k (rejected).
- BASE NOW my_dsm343.py (=811): 6-seed solo 135862 vs 341 137702 (-1840, -1.3%,
  t=-0.91 n.s.); deaths 28.8 vs 36.7 (-7.8, 57% of DSM gap closed, t=+2.6).
  H2H vs pipe19 -51.7k/-58.2k (was -56.7k/-61.8k). No meter regressed >10%.
- rev_audit per-item lines are MISATTRIBUTED (whole-step delta -> first sell
  item); judge totals only. Melon: no expiry trap (all 10 harvested 4-6u);
  gap is window-water d6-12. Carrot births 2x (31 vs 15) at same water 36.5/d.

## 2026-09-28 session p2: outside DSM-03 port (BASE NOW = my_dsm344.py)
- Outside report verified BEFORE porting: reference rows byte-match ours
  (solo per-seed, DIG 54.667, dawn deaths 36.667, HV 485.17); v3 arithmetic
  reproduces (mean 143474.5, paired t=2.65). 343 confirmed clean of any
  hour>=23/terminal/last_water logic -> no conflicts, pure addition.
- Adopted ONLY v1+v2+v3 (deadline/clock mechanisms); endorse their rejections
  of v4/v5 (PASS-guard violations), v7 (solo-/H2H-gate miss), v9 (prediction
  miss), v8/v10. Their open gates (wheat +0.3/6, HV +10/65) mirror ours.
- 344 = 343 + midnight (no h23 PLANT) + d29 terminal delivery + last_water.
- 344 6-seed solo 141376 vs 343 135862 (+5514; 5/6 seeds up +5.7/+6.8/+5.5/
  +14.2/+10.0k, seed3 -9.1k high-variance collapse seed, in observed band).
  vs 341 +3674 (+2.7%, t=+1.6). vs outside-v3 alone 143475 (-2.1k: base diffs).
- Deaths weed 19/20/27/18/14/22 mean 20.0 vs 343 28.8 (-8.8, paired t~+6.5,
  ALL seeds down) vs 341 36.7 (-16.7, gap 118% closed vs DSM 22.6 mean).
  NOTE: 20.0 < DSM 22.6 — midnight guard removes deaths DSM itself takes
  (DSM plants h23); number beats target but behaviorally diverges. Watch.
- DIG 32.3 vs 54.7 (outside v3: 36.3 — turnover+midnight stack lower).
- H2H vs pipe19 -49.6k/-52.5k (was -51.7k/-58.2k); matrix TOTAL -818898/16
  = -51.2k avg (was -55.2k 343, -59.3k 341). No regression.
- BASE NOW my_dsm344.py. Caveats shared with outside: same-six-seed
  overfitting (both sides), H2H seeds differ (theirs 30000x, ours 20000x —
  compare deltas only), wheat-stand gate still OPEN on both lines.

## 2026-09-28 session p3: T0 re-baseline of 344 + T1 telemetry (queue REORDERED)
Base 344 re-verified: 6-seed solo 141376 byte-identical [153640,152977,98006,
129950,165459,148222]. Base NOT edited. All probes READ-ONLY, external
wrappers (tools/t1_telemetry.py, tools/plant_trace.py, tools/why_empty.py,
tools/stand_table.py) -> zero perturbation risk, no instrumentation twin needed.

### T0 verdict per handoff target  (REAL / CLOSED, with the number)
- **HARVEST target 496->527+: CLOSED.** Our HARVEST 498/499/503/493/496/496 =
  mean 497.5, INSIDE the DSM IQR [485-569]. There is no +31 to close. The
  "we harvest at yld 2 not 6" clause is the only live half (see L6 below).
- **Melon 4.4u -> 5.5u: CLOSED, already exceeded.** yield 5.8u/plant
  (hist 6:9, 4:1 of 10 plants = 97% of maxyield). Window d6-12 coverage is
  only 37/70 yet yield is maxed: coverage is not the binding limit.
- **Wheat stands ~17->23+: REAL, and much larger than stated.** d10 9.8/17,
  d12 23.3/26, d15 19.7/24, d20 18.0/23, **d25 11.0/30 (-19)**.
- **Deaths: CLOSED and BEATEN.** weed deaths 19/20/27/18/14/22 = mean 20.0
  vs DSM 22.6 mean / 23 median. The "+14 dead-tile lag" story is DEAD: it
  was a v341 artifact and 344 removed it. Do not use deaths as a gap proxy.
- **`/tmp/opencode/crop_stands.py` has a divisor bug**: divides DSM sums by
  90 but 69 replay files x 2 = 138 sides -> DSM means inflated 1.533x.
  Corrected DSM: d10 W14.9/S19.7, d15 W22.0/S30.1, d20 W21.0/S26.4,
  d25 W30.4/S13.3 — which match the DSM_SPEC.md s4 medians. Use
  tools/stand_table.py instead.
- **`DSM_SPEC.md` s14 per-item revenue split is WRONG** (plan already
  suspected). Measured properly via market-inventory deltas x engine
  `market_price` quote (tools/t1_telemetry.py), seed 300001, $167.8k gross:
  **MILK 42.1k (25%) | FERTILIZER 33.5k (20%) | WOOL 30.4k (18%) |
  STRAWBERRY 30.3k (18%) | MELON 13.8k (8%) | WHEAT 10.6k (6%) |
  EGG 5.0k (3%) | CARROT 2.2k (1%)**. Wheat is 6%, not 56%. **L1 as written
  (fert on window-wheat) is economically NEGATIVE: a fert is worth $77 sold
  and +1 wheat unit is worth $38.** Same for carrot ($37). Fert belongs on
  STRAWBERRY (+1u = $244/evt, and one fert spans up to 2 eves) — which the
  base already does (74 of our 155 FERTILIZE are strawberry; pipe19 61/71).

### T1 gates: which plan levers are live
- **L1 (fert coverage on window-wheat): DEAD, and the gate reading was an
  artifact of my own first probe.** tools/plant_trace.py: in-window WATER
  with fert active = 71/150 (47%), and that maps 1:1 onto the yield hist
  {2:79, 3:71} — i.e. **the +2 fert bonus is already fully collected on
  every plant that can be ferted.** Nothing to fix. (t1_telemetry reported
  0/79 because it labelled only the FIRST in-window water per plant; the
  71 ferted waterings are all later waterings on the same plants. Both
  numbers are right about different things.)
- **L2 (strawberry production-eve coverage): DEAD.** eve coverage 103/115
  (90%). Not the binding limit.
- **L3 (stop water on zero-yield off-window one-shots): WEAK, ~7 acts/day.**
  A new plant starts cu=1, so "cu==0 off-window" is only reachable at age
  >=1, i.e. ONE day for wheat/carrot (ages 0-1 off-window of 5; the age-0
  day is cu=1 so it takes the urgent path, not the 5.0 routine path).
  Max saving 162+41+10 = 213 acts/game = 7.1/day, each carrying a
  death risk because it converts a routine water into a cu=1 rescue.
- **L4 (d20-26 wheat cap 5/d): gate PARTIALLY met, and it is NOT the
  binding constraint.** tools/why_empty.py interrogates the agent's own
  `pick_crop` on every empty tile: at d22-27 it answers OK:WHEAT/OK:CARROT
  for 57-71 tiles/day, i.e. **the agent wants to plant every idle tile and
  the caps are what stop it.** But the board is NOT the constraint at
  d11-d21 (empty 0-4). It only opens at d22-27 (11-17 empty). So raising
  the cap converts idle TILES into wheat worth ~$94/plant, but at
  d11-d21 there is no tile to fill. L4 alone is worth ~1.3k. Not the lever.
- **3rd-quadrant question in the plan's Open Questions: MOOT.** The board
  census shows unlocked tiles 25 (d0-8) -> 50 (d9-10) -> **75 (d11+)**. We
  already run 3 quads. Do not revive.
- **PASS is an early-game-only artifact, not a late-game sink:** 379 of 599
  PASS acts fall on d2-d7, when the board is 25 tiles (18-19 plants + 5-6
  structures = FULL) and the crew is 4-6 hands. Nothing is plantable; the
  idleness is structural, not a targeting bug. From d11 on, PASS is 0-34/d.

### THE REAL GAP (not in the handoff queue): PLANT DENSITY + YIELD PER TILE
Board is 75 tiles for both us and pipe19 from d12. But:
|                        | 344    | pipe19 |
|------------------------|--------|--------|
| plant-tile-days d13-27 |   666  |   858  |
| empty-tile-days d13-27 |    83  |     6  |
| structure-tile-days    |   300  |   255  |
| tile-days per plant    |  2.75  |  3.59  |
| WHEAT yield/plant      |  2.47  |  3.26  |
| CARROT yield/plant     |  2.02  |  2.90  |
| WATER:WHEAT acts       |  452   |  519   |
| WATER:STRAWBERRY acts  |  432   |  302   |
| WATER total            | 1101   | 1089   |
Both plant 239-242 plants lifetime. **Same water, same births, 29% fewer
plant-tile-days.** Ratio 2.75 -> 3.59 = 1.31 is exactly "free the tile one
day later" (harvest at yld 3 instead of yld 2). Our `ripe()` fires the
instant a one-shot crosses yld>=2 and age>=first, so ages 3-4 of the wheat
window (DSM_SPEC.md:154-155 window = age 2..4) are NEVER collected: a wheat
plant is watered once at age 2 and banked. Yield 2.47 is arithmetically
forced by the gate, not by a water shortage.
- Enabling condition is already true: 11-17 idle tiles at d22-27, so
  holding a plant one day longer costs no tile availability.
- Cost: +1 water act per one-shot plant (~191 acts = 6.4/day).
- PRIOR EVIDENCE: v600 (age>=4 or yld>=4) -28274 and v601 (yld>=3) -21253,
  both on v341 where deaths were 36.7 and the board was tight. The
  dependency (tile slack + deaths) has moved. Must be re-priced on 344.

### L6 HYPOTHESIS (written before code)
Mechanism: `ripe()` (my_dsm344.py:907-916) releases WHEAT and CARROT the
moment yld>=2, so the 2nd and 3rd days of their one-shot yield window are
never banked. Requiring yld>=3 holds each one-shot exactly one extra day,
which per the tile-day arithmetic above converts directly into +31% plant
density as well as +1u/plant.
Prediction: WHEAT yield/plant 2.47 -> >=3.2; CARROT 2.02 -> >=2.8;
empty-tile-days d22-27 fall 11-17 -> <5; solo >= 0; deaths <= +10%;
PASS < +10%.
Falsifier: solo negative on 2-seed screen -> the v341 rejection still
binds (tile turnover beats yield) and L6 is dead.
Watch: the extra water act must come from somewhere. If deaths rise, the
water is being taken out of STRAWBERRY (432 acts, 14.9/plant, 11 plants
dying/game at $1.5-1.9k each) and L6 is self-defeating.

### MEASUREMENT FLOOR (read this before trusting ANY keep/reject verdict)
`LINE_FORCE` is the base's own env knob for the species line and is
strategically neutral (same agent, same code, only cow-vs-sheep lean). On
base 344, seeds 300001+300003:
| LINE_FORCE | seed 300001 | seed 300003 | 2-seed mean |
|---|---|---|---|
| cow+     | 160168 | 105532 | 132850 |
| sheep    | 153640 | 119601 | 136620 |
| mixed    | 150819 |  98006 | 124412 |
| (unset = real d6_branch) | 153640 | 98006 | 125823 |
**Per-seed spread up to +21,595 (seed 300003). 2-seed mean spread +12,208
(+9.8%).** Cause (already flagged in the base's own comment at
my_dsm344.py:468-471): `d6_branch(ctx.shops)` picks the line from which
SHOPS unlocked, shop unlocks share the game RNG stream with weed spawns, and
the agent's act sequence perturbs that stream -- so **ANY code change
reshuffles the line, on every seed.**
- Consequence 1: a 2-seed screen CANNOT resolve any effect smaller than
  ~10-20k on this base. The handoff's "screen on 2 seeds, promote real
  signals" rule only works for large effects.
- Consequence 2: paired t at n=6 has SE ~5-8k, so only >=10% (~14k) effects
  are detectable. **The plan's "close >=50% of the target" keep rule is
  unachievable for any target worth <10%.** Most of the handoff's targets
  (wheat stands +6, HARVEST +31, melon +1.1u) are worth 1-5k each.
- Consequence 3: re-examine every verdict in this file whose delta was
  <15k and which was judged on 2-6 seeds. v600 (-28274) and v601 (-21253)
  are ABOVE the floor and stand; most others are not separable from a line
  reshuffle.
- Do NOT "fix" this by pinning the line: pinning LINE_FORCE is explicitly
  out of bounds (overfitting list) and the line is a real strategic choice
  (sheep 136.6k > cow+ 132.9k > mixed 124.4k on 2 seeds), not a free win.
  Flagged to the user as a methodology decision, not taken unilaterally.

### L6 RESULT: INCONCLUSIVE, not rejected
- v346 (WHEAT+CARROT floor 3): 2-seed 114128 vs base 125823 = **-11695
  (-9.3%)**. CARROT yield 2.02->2.94 (prediction >=2.8 MET).
- v347 (WHEAT only, floor 3; carrot left at 2): 2-seed 125534 vs 125823 =
  **-289 (-0.2%)**. WHEAT yield 2.47->**3.07**, hist {2:79,3:71} ->
  {2:14,3:112,4:25} (prediction >=3.2 nearly met).
- **The mechanism demonstrably fires in both variants** -- this is not a
  no-op gate. But the score does not follow the yield, and the revenue
  decomposition shows why: v347 seed1 vs base is WOOL **-17943** /
  MILK **+11810** / WHEAT only +872, i.e. the loss is a species-line
  reshuffle, not lost wheat. WHEAT revenue rose only +8% for a +24% yield
  gain -- the market price falls with our own volume (MARKET_PARAMS WHEAT
  below_target 0.80 / sqrt), so **extra production volume converts to money
  at a discount.** That is a second, independent reason the "make more
  plants" framing underdelivers, and it applies to solo (the PASS dummy does
  not consume supply, so all volume is self-deprecating).
- Verdict: L6 is UNRESOLVED at the current measurement resolution. Do not
  adopt, do not record as refuted. It only becomes decidable if the noise
  floor is lowered (more seeds) or the line branch is held fixed across both
  arms of a comparison.

### L6 FINAL: REJECTED at n=6 (paired t = -2.28)
v347 (WHEAT floor 3) 6-seed solo [135049, 92888, 116019, 91987, 154298, 95822]
= **114344** vs base 344 [153640,152977,98006,129950,165459,148222] = 141376.
Paired deltas [-18591, -60089, +18013, -37963, -11161, -52400],
mean **-27032 (-19.1%)**, sd 29010, SE 11844, **t = -2.28, n=6, p<0.05**.
1/6 seeds up. The variance is the line reshuffle; the MEAN is decisive.
- Deaths did NOT regress: v347 weed deaths 10/24/18 (mean 17.3 on seeds
  1/3/5) vs base 19/27/14 (mean 20.0). So the failure is NOT the
  "held plant expires unharvested" mechanism the risk list anticipated.
- **v601's -21253 on v341 REPRODUCES on 344 (-27032, t=-2.28). The
  dependency did NOT move.** The enabling condition I identified (11-17
  idle tiles at d22-27) is necessary but not sufficient: the idle tiles
  only exist in the last third of the game, when an extra held day cannot
  repay itself before the d29 lock, while the density/tile cost is paid
  every day from d11 on.
- Combined with the price finding above, "collect more yield per plant" is
  now REFUTED on this base by two independent mechanisms: tile turnover
  dominates, and marginal volume self-deprices. Any future proposal framed
  as "raise yield/plant" must beat BOTH.
- L6 CLOSED. Do not revisit without a change to the tile budget itself
  (i.e. a real reason the d22-27 idle tiles could be filled earlier), and
  not on a 2-seed screen.

### What is actually left, ranked by measurable size (>=10% required)
Revenue is 46% animals / 20% fertilizer / 18% strawberry / 8% melon /
6% wheat / 1% carrot. Only two pools have >10% headroom:
1. **STRAWBERRY** $30.3k on 29 plants at 6.5u/plant vs maxyield 8 (81%),
   with ~11 plants dying per game (weed, cu>=2) and each live plant worth
   ~$1.6k. Full-value ceiling is ~$56k. This is the only >10% pool and the
   only candidate that can clear the noise floor. Root cause is water
   coverage over a ~26-day life (432 WATER acts / 29 plants = 14.9, i.e.
   57% of days) NOT eve coverage (103/115 = 90%).
2. **FERTILIZER** $33.5k: 433 units collected/bought, 155 applied, the
   rest sold at $77. Already 20% of revenue with no obvious headroom --
   it is a byproduct of herd size, so it scales only with animals.
Note also: `DIG:STRAWBERRY` is a routine pipe19 verb (14/game) and we
DIG only 32 total. Spent strawberries (past their age-16 last eve) are
excluded from watering by the PKG14 spent-tile gate, so they are left to
rot into WEED instead of being dug and replanted. Untested; small
(~1.3k) but it also removes tiles from the weed count.

## 2026-09-28 session p4: forbidden list lifted. Shed/sell throughput, herd mix, H2H
Tools added (all read-only): tools/t1_telemetry.py (extended with
harvested-vs-sold + max-shed sampling EVERY step), tools/stand_table.py,
tools/plant_trace.py, tools/why_empty.py, tools/animal_meter.py,
tools/h2h_one.py.

### THE "+12.2k" WAS NOISE -- do not ship it as +12.2k
LINE_FORCE, 6 seeds 300001-6, base 344:
  unset(d6_branch) 141376 | sheep 140637 (-739) | **cow+ 144999 (+3623, +2.6%)**
cow+ differs from base on seeds 1,2,3 only (+6528/+7684/+7526, 3/3 up) and is
BYTE-IDENTICAL on seeds 4,5,6 -- i.e. d6_branch already picks cow+ there.
So pinning cow+ is a real but small +3.6k, NOT +12.2k, and it is below the
measurement floor. Line pinning stays available but is not a headline win.

### Engine rule read from source that nobody had measured (user suggestion 3)
`_daily_refresh_animals`:
    if (day+1 - placed - first) % interval == 0:        # production day
        bonus = pending_care_bonus if fed_today else 0
        yield  = min(max_held, yield + 1 + bonus); pending_care_bonus = 0
    if cared_today and fed_today: pending_care_bonus += 1
**pending_care_bonus COMPOUNDS**: care+feed on every non-production day banks
+1 each, and the whole stack is collected on the next fed production day.
Worth up to `interval` extra units/prod-day (COW 2, SHEEP 3, GOOSE 1) and it
is WIPED IN FULL if the animal is unfed on its production day.
tools/animal_meter.py on 344 seed 300001: feed coverage 89-93%, prod-day
hit rate COW 88% / SHEEP 95% / GOOSE 90%, banked bonus COW 2.55 SHEEP 3.35
(near the interval cap). pipe19 on the same seed: COW 100% / SHEEP 95%,
bonus 2.28 / 3.39. **So our care/feed discipline is ALREADY at DSM level and
is not the gap.** The 8 missed COW production days are worth ~16 milk
(~$4k); the care mechanic is a real multiplier but we are not under-using it.

### HERD MIX (user suggestion 3, second half) -- measured per animal, lifetime
seed 300001, realized prices from market-inventory deltas:
| | units | $/unit | product $ | + fert 30x$77 | total | capital | $/capital |
|---|---|---|---|---|---|---|---|
| SHEEP | 26 | 240 | 6240 | 2310 | **8550** | 500 | **17.1** |
| COW   | 24 | 250 | 6000 | 2310 | 8310 | 400 | **20.8** |
| GOOSE | 30 |  53 | 1590 | 2310 | 3900 | 300 | **13.0** |
The fert byproduct is IDENTICAL per head, so the entire difference is the
product price: EGG is the only product whose realized price tracks its base
($53 vs base 50); WOOL/MILK realize well above base. The base was running its
cheapest product on 6-8 of ~21 head.
pipe19 same seed: 11 sheep, 0 geese, $52.6k wool vs our $30.4k.
- **v350 = v348 + goose-free herd at CONSTANT head count (21)**:
  sheep 8/12/0, cow+ 12/9/0, mixed 9/12/0 (mix isolated, scale held).
  2-seed 126234 (s1 166562, s3 85907) vs base 125823 (+411) and vs v348
  135180 (**-8946**). Herd confirmed as 8/12/0 and 9/12/0, deaths improved
  28/32 vs 35/38. **UNRESOLVED at n=2** -- inside the +-12.2k 2-seed band.
  Needs n=6 before any verdict; do not adopt on this.

### SHED / SELL THROUGHPUT (the real find)
- Shed capacity is 100 and **we saturate it (max_shed == 100 on every seed
  measured)**. Once full, the EOD auto-drop DELETES the overflow, so goods we
  grew never become money.
- The sell loop walked `SELLABLE` in FIXED order (WHEAT, CARROT, TOMATO,
  STRAWBERRY, MELON, EGG, MILK, WOOL, FERTILIZER) under a 4-order cap, so
  the first four stocked items took every slot and **the five most valuable
  products were structurally starved of sell orders all game.** The end-of-
  game shelf is exactly the starved tail: MILK 9, WOOL 8, EGG 9, FERT 30.
- **v348 = v348 sell candidates ordered by current price, most valuable
  first** (cap still 4, so the dsm36 seed-order behaviour is untouched).
  6-seed [156032,158337,114328,133860,168160,143178] = **145649 vs 141376 =
  +4273 (+3.0%), 5/6 seeds up, t=+1.51** (P(5/6 by chance) = 11%).
  deaths 9/21/20 = 16.7 vs base 19/27/14 = 20.0 on seeds 1/3/5 (**-16.5%**).
  HARVEST 509/509/498 vs 498/503/496.
- **HONEST MECHANISM CHECK -- my stated mechanism did NOT hold.** The
  predicted "close the unsold leak" FAILED: harvested-minus-sold value is
  344 base ($20.8k) vs $21.8k in v348 (the shed now HOLDS 28 strawberry
  instead of 2). max_shed is still 100 in both. So v348 is a +3.0% result
  whose cause is NOT the one predicted; the plausible cause is cash TIMING
  (high-value goods sold earlier fund hires/seeds/animals sooner), but that
  is unproven. Treat v348 as a modest positive signal, not a closed leak.
- **v349 = v348 + sell cap 4->9 when shed >= 80 or day >= 26** (attacks the
  capacity block directly): 2-seed 133191 vs v348 135180. WORSE, and deaths
  up 39/40 vs 31/37. Rejected at n=2; the extra sell slots evidently starve
  the seed/durables orders more than the shelf space is worth.

### H2H (user asked: 1 game each, both seats, seed 200001, v77-pack agents)
  vs opp_pipe19: 107172 vs 159102 -> **-51930** (both seats identical)
  vs opp_v57:    107176 vs 159108 -> **-51932** (both seats identical)
Two DIFFERENT opponents produce the same score for us (107.2k) and nearly the
same score for them (159.1k). Base 344 was -49.6k/-52.5k, so v348 does not
regress H2H.

**!! RETRACTED — the "volume is self-defeating" conclusion above was WRONG
and has been disproven by direct measurement. Do not build on it. !!**
New tool `tools/h2h_who.py` attributes revenue per seat inside a single H2H
game (seed 200001, v348). Result:

| good | ours units @ $ | pipe19 units @ $ |
|---|---|---|
| MILK | 247 @ 263.8 | **335 @ 262.6** |
| STRAWBERRY | 179 @ 174.6 | **276 @ 174.9** |
| MELON | 59 @ 190.7 | **72 @ 244.2** |
| WHEAT | **419 @ 40.6** | 439 @ 41.6 |
| FERTILIZER | **610 @ 48.8** | 367 @ 51.1 |
| EGG | **138 @ 44.6** | 0 |
| WOOL | 92 @ 59.3 | 121 @ 53.4 |
| CARROT | **84 @ 37.9** | 93 @ 34.8 |
| **gross** | **$169,228** | **$200,545** |

The realized prices are **effectively identical** (milk 263.8 vs 262.6,
strawberry 174.6 vs 174.9). pipe19 sells **+36% more milk and +54% more
strawberry** at the *same* price. So the shared pool is NOT price-saturated
against them; **they are the high-volume, high-value seller and we are
over-producing the cheap goods (fertilizer, eggs)**. The correct H2H lever is
production MIX and survival, not sell-side price discipline. Every v35x
experiment below was designed against the retracted theory.

### Per-seat board + action split (tools/h2h_land.py, tools/h2h_acts.py)
  ours: 21 structures, 46-49 plants (d12-27), **8-21 EMPTY tiles**
  pipe19: 17 structures, 53-58 plants, **0-4 empty tiles**
  plants decay ours 52 (d14) -> 33 (d27); theirs 57 -> 58 (no decay)
  actions ours DIG 28, PLANT 250, PASS **604**; theirs DIG 39, PLANT 239,
  PASS **433**. Our movement is higher on every axis (W 1086 vs 864).
  **We have idle hands AND dying plants AND empty tiles simultaneously.**

### Shop RNG chaos (parallel agent, agreed)
Shop unlocks draw from the same RNG stream as weed spawns, so ANY field or
shop change re-draws later events. Single-seed swings are +-10-30k. **6 seeds
resolve only ~10k, which is below our effect sizes.** Standard is now 18
seeds (300001-018), finalists also 300019-030.

### v351-v355 LEDGER (all designed against the retracted price theory)
**NAMESPACE WARNING: a second agent ran a parallel stream with its own v351-
v356 in a different tree. Their v353 = "no fertilizer on wheat", mine = "price-
revalued herd". Never compare variants by number. Identify by content.**

- **v351 = shed-pressure cheapest-first sell** (when shed full, dump the
  cheapest goods to make room): 6-seed **126573**, worse on ALL SIX seeds vs
  base 141376. Cheapest-first is strictly the wrong direction under the price
  data. Rejected.
- **v352 = price-ranked crop expansion into idle tiles** (first true test of
  price feedback on allocation): 6-seed **142980** vs 141376. +1.1%, inside
  noise, mixed. Not adopted; price ranking alone is not enough.
- **v353 = price-revalued herd, freeze species priced < 0.8 x best** (freezing
  wolves/geese to push them to the highest-priced species): 6-seed **133124**,
  badly worse. Mechanism found: **geese are valuable FERTILIZER factories**
  powering the FERTILIZE one-shot bonus, so freezing them loses more than the
  price gain. Rejected. (Valuing animals by product price alone is wrong.)
- **v354 = v353 + v352 crop fill**: **byte-identical result to v353** — the
  crop fill never binds once the herd is frozen. Rejected.
- **v355 = exempt PLANT from the `STIG_RADIUS=5` cap** (engine rule: a plant
  action beyond radius 5 into a val<9 tile is blocked; only WATER was exempt):
  **byte-identical to v348**. The radius cap is not a live constraint on our
  PLANT sites. Dead lever, do not retry.

### Daily price trajectories (tools/px_daily.py, tools/px_solo.py)
  H2H seed 200001: WOOL collapses <0.5x base by d14 and ~$1 by d16; MELON
  collapses d15; FERTILIZER decays from d0. WHEAT/CARROT/STRAWBERRY/EGG/MILK
  never fall below 0.5x. End ratios: MILK 1.77, WHEAT 1.72, STRAW 1.39,
  CARROT 1.09, EGG 0.84, MELON 0.58, FERT 0.07, WOOL 0.01.
  **Wool/fertilizer collapse is a LATE-GAME sell-timing trap, not a hedging
  opportunity** — do not build a price-feedback loop that dumps into it.
  Confirmed pre-existing in SOLO base 344 (seed 300001 wool ends 1.22, seed
  300004 wool ends 0.01), so it is not v348-induced.

### Seed/money gate diagnostic (tools/gate_debug.py)
  During the window when we hold cash ($20-29k), spare seeds (14 strawberry,
  20-25 wheat, 10-15 carrot), only 1-4 EMPTY tiles, and every gate condition
  true. **Seeds and cash are NOT the constraint — reachable land and plant
  survival are.** Tomato seeds 0. This closes the "buy more / more cash" family
  of hypotheses.

### vW1 = DEATH-AVOIDANCE WATER TIER  (RESULT: LEVER REJECTED, TARGET RETIRED)
`my_dsmW1.py`, one-line change, `EMERG_W` env-tunable. Verified **EMERG_W=0.09
reproduces 344 EXACTLY** (all 6 seeds delta=+0), so the harness is deterministic
and the patch is behaviourally isolated to that one term. Paired vs 344, n=16:

| EMERG_W | meaning | mean d | t | wins/16 |
|---|---|---|---|---|
| 0.00 | emergency DEMOTED below routine | -4370 (n=6) | -1.24 | - |
| **0.09** | **= v344 exactly (control)** | **0** | - | - |
| 0.25 | +1.25 tile reach for emergencies | -8252 | -1.48 | 4 |
| 0.50 | +2.5 tiles | -22417 | -3.48 | 3 |
| 0.75 | +3.75 tiles | -36434 | -7.01 | 1 |
| 1.00 | emergencies ignore distance | -38865 | -7.37 | 0 |

**Perfectly monotonic in the WRONG direction.** The dsm24 nearest-first
scoring is load-bearing, not an oversight, and 0.09 is a local optimum: both
raising AND lowering the emergency weight lose. The theoretical flaw is real
(the whole value range 0..10 is worth 0.9 < one tile of distance) but fixing it
costs more than the deaths it saves.

**WHY -- and this retires the #1 target.** Deaths barely move while reward
swings by tens of thousands:

| seed | deaths .09 -> .5 | reward d | HARVEST d |
|---|---|---|---|
| 300001 | 19 -> 17 | **-29059** | 498 -> 481 |
| 300003 | 27 -> 15 | **+25363** | 503 -> 469 |
| 300005 | 14 -> 19 | **-78252** | 496 -> 467 |

Every seed loses ~30 HARVEST acts no matter what happens to deaths. Chasing a
distant thirsty plant drags a unit off the harvest pipeline, and the lost
harvest is worth far more than the saved plant. Death detail from death_exact:
they are **STRAWBERRY 9 / WHEAT 10** and are concentrated LATE -- by day
{14:1, 15:4, 18:4, 21:4, 27:4, 28:1, 29:1}. Most are spent tail tiles we had
already stopped tending.

**CONCLUSION: "weed deaths 20 vs pipe19 1.5" is a SYMPTOM, NOT A CAUSE, and it
is not worth chasing.** pipe19's low death count reflects a more stable field
(57-58 plants held flat) while we run a higher-turnover dig/replant cycle
(67-78 tiles removed vs their decay-free field). The 20 deaths are part of the
cost of the turnover that produces our 498 HARVEST acts. **The binding
quantity to protect is HARVEST count and the pipeline feeding it, not survival.**

### vM1 = MELON PERISHING-WINDOW OVERRIDE  (SOLO POSITIVE, not yet validated H2H)
`my_dsmM1.py`, `MELON_D` env-tunable. **MELON_D=1.0 reproduces 344 EXACTLY**
(6 seeds, all delta=+0). Paired vs 344, n=16, seeds 300001-016:

| MELON_D | meaning | mean d | t | wins/16 | sd |
|---|---|---|---|---|---|
| 0.00 | ripe melon ignores distance | +1646 | 0.65 | 11 | 10126 |
| **0.35** | **distance x0.35** | **+2943** | **1.59** | **12** | **7426** |
| 0.70 | distance x0.70 (barely binds) | -133 | -0.10 | 6 | 5454 |

0.35 wins on both mean and -- more importantly -- has the LOWEST variance
(7426 vs 10126), and at 0.7 the override stops binding at all (7 of 16 seeds
go to exactly delta=0, confirming the mechanism is distance-gated). Same shape
as v348: real effect ~3k, noise ~10k. Needs 18+ seeds and an H2H check.

### THE d10 CLIFF -- where the H2H gap actually opens (tools/h2h_cash.py)
Per-seat cash is a step function, not a slope. Seed 200001, US vs pipe19:

| day | US cash | OPP cash | diff | US sold | OPP sold |
|---|---|---|---|---|---|
| 9 | 12 | 2,889 | -2,877 | 1,501 | 2,737 |
| **10** | **3,471** | **18,556** | **-15,085** | 8,901 | **18,974** |
| 11 | 2,958 | 19,141 | -16,183 | 6,097 | 5,754 |

Through d9 we are TIED (-159 cumulative). **d10 alone opens -10,232 cumulative
and we never recover it.** Plant counts on d10 are near-identical (33 vs 32)
and we have MORE hands (13 vs 11), so it is neither land nor labour.

Cause, from tools/h2h_melon.py -- it is melon, on that one day:

| | melons d0-9 | harvested d10 | units d10 | yield/melon | left standing |
|---|---|---|---|---|---|
| US | 6->**10** | **6** | 24 | **4.0** | **4** |
| OPP | **12** | **12** | 60 | **5.0** | 0 |

MELON spec: `first=10, maxday=12, interval=0, maxyield=6` -- one-shot, dead at
age 12, and `ripe()` fires the moment age>=10, so there is no reason to wait.
pipe19 takes $15,216 of melon on d10 and $2,364 on d11 (86% of its whole-game
melon on one day); we take $5,352 / $2,364 / $800 / $2,736 across d10-d14. The
4 melons we leave standing come back on d11 at **3.0u instead of 5.0u** -- the
observed 5.0 -> 4.0 -> 3.0 decay is the yield loss from being one day late.
**A $9,864 hole, ~20% of the entire 49.6k deficit, from one crop on one day.**
NOTE: a prior session already diagnosed this in a comment (my_dsm344.py:901,
"opp harvests all d10 at ~4.8, sells same day -> $18k spike") but could not
deliver it, because the d10 rush only sets val=9.0 and nearest-first scores
`-d + 0.09*9.0` -- a melon 1 tile farther loses to any nearer tile. Worse, on
d11-d12 melon falls back to val=8.0, which trips the `val < 9.0` radius cap
and makes late melons INVISIBLE past 5 tiles. vM1 fixes both.

### DSM REFERENCE: what the strongest agent actually does
Mined from `/home/moh/Desktop/glm2/result/dsm games/` (42 replays,
`new_agent/REPLAY_FINDINGS.md`) with tools/dsm_suppress.py.
**DSM wins 39 of 40 non-mirror games**, median margin **+17,202**, mean
+17,096, range -9,316 (only loss, vs DECEM) to +49,065.

*Suppression is real and quantified* -- DSM realizes a RICHER price than its
opponent on 8 of 9 goods, by taking the good goods before the price decays:

| good | DSM share of pool sell-orders | DSM px | OPP px | edge |
|---|---|---|---|---|
| WOOL | 56.9% | 119.8 | 92.8 | **DSM +29%** |
| STRAWBERRY | 62.1% | 124.8 | 110.1 | **DSM +13%** |
| MILK | 49.5% | 83.0 | 79.9 | DSM +4% |
| MELON | 41.1% | 195.5 | 183.9 | DSM +6% |
| EGG | 48.3% | 47.6 | 45.0 | DSM +6% |
| TOMATO | 70.4% | 67.1 | 66.3 | DSM +1% (takes 70% of pool) |
| WHEAT | 59.7% | 34.1 | 34.3 | ~tie |
| FERTILIZER | 47.2% | 55.8 | 54.6 | DSM +2% |

CORRECTION to an earlier assumption: DSM's peak cash is **$108,199/game vs the
opponent's $91,103** -- DSM does NOT trade cash for suppression. It wins on
cash AND takes the price edge. Suppression is a bonus margin, not the mechanism
we were missing.

*Structural blueprint (REPLAY_FINDINGS.md, DSM vs Boey):*
- **walking: ours 67% of actions, Boey/DSM 42-45%** -- the single biggest gap,
  and it matches our own mv/act 1.75 vs DSM 0.80 finding.
- d0: aggressive boustrophedon PLANT->WATER sweep, **20 plants on d0**
  (Boey) / 15 (DSM), first PLANT at t=6 (we were t=12).
- herd by d11: **DSM 24 animals (C9 S15, NO geese)**, Boey 20.
- both run ~$0 from d1-d10 (everything reinvested), then a d11 melon payday.
- DSM ends d29 at $117,128 on tomato/wheat/carrot; we are at ~145k SOLO and
  still lose H2H, which is the whole point of the objective being
  **(my cash - opponent cash)** and not my cash alone.

*Engine truths re-confirmed from the replay mining:* plants die at
`consecutive_unwatered >= 2` and leave a WEED that costs a DIG; atomic PLANT
validation drops ALL requests for a crop if seeds are short; animals escape at
`consecutive_unfed >= 2`; BUILD_PASTURE is free but costs action+walk.

*Suppression already working for us:* we flood FERTILIZER (591u vs their 367u)
and take $29,164 to their $19,005 -- **+$10,159 on that good**. Under the
zero-sum objective that is not waste, it is a win. Our per-good H2H losses are
MILK -16,534, STRAWBERRY -19,115, MELON -6,328. **The hole is not in the cheap
goods; it is milk and strawberry volume, and the d10 melon cliff.**

### !!! METHODOLOGY FAILURE: SOLO REWARD DOES NOT PREDICT H2H MARGIN !!!
This invalidates the screening metric used for the entire session. Both
"winning" variants were measured paired against 344 on 18 seeds solo and then
re-measured with tools/hscreen.py on the metric that actually matters --
(my cash - opponent cash) over 12 seeds:

| variant | solo delta | H2H margin vs pipe19 | H2H margin vs v57 |
|---|---|---|---|
| v348 (price-ordered sell) | **+4273** | **-1135** (t=-0.66) | **-1138** (t=-0.64) |
| vM1 (melon window) | **+3377** (t=1.98, 14/18) | +852 (t=0.32) | +1021 (t=0.39) |

**v348 is not a candidate. It is slightly NEGATIVE on the real objective.**
**vM1 is a solo-only mirage.** Both produce ~+3-4k solo and ~0 H2H. There is
currently **NO validated candidate on the board** -- base 344 still stands, and
that is now the honest state rather than a default.

Why the metrics decouple: the pool is shared, so a variant that makes us sell
more CRASHES THE PRICE FOR BOTH SEATS. Own cash rises, and the opponent's
supplies get cheaper too, so the DIFFERENCE barely moves. Solo has no opponent,
so it pays full price and the whole gain shows up. **Any solo-only measurement
is structurally incapable of seeing the real objective, and I used it for every
decision this session.**

GOING FORWARD -- hard rule, non-negotiable:
1. **H2H margin is the only acceptance metric.** Solo is a cheap smoke test at
   best, never a verdict.
2. Never accept a variant on solo evidence, no matter the t-stat.
3. Screen H2H against BOTH pipe19 and v57; a win that appears against only one
   opponent is mimicry, not an advantage.
4. sd on the H2H margin-delta is ~6-9k at n=12, so n=12 only resolves ~2k.
   Given a 45-50k gap, treat sub-2k H2H deltas as zero, not as small wins.

WHERE THE REAL H2H MARGIN LIVES (per-good, seed 200001, v348 vs pipe19):
| good | our rev | their rev | delta |
|---|---|---|---|
| STRAWBERRY | 29,554 (168u) | 48,669 (276u) | **-19,115** |
| MILK | 70,294 (270u) | 86,828 (335u) | **-16,534** |
| MELON | 11,252 (59u) | 17,580 (72u) | -6,328 |
| WHEAT | 16,541 (407u) | 18,260 (439u) | -1,719 |
| FERTILIZER | 29,164 (591u) | 19,005 (367u) | **+10,159** |
| EGG | 6,401 (144u) | 0 | +6,401 |
| CARROT | 3,006 (78u) | 3,636 (93u) | -630 |
| WOOL | 5,476 (92u) | 6,462 (120u) | -986 |

Prices are IDENTICAL (straw 175.9 vs 176.3, milk 260.3 vs 259.2), so this is
pure VOLUME. And the direction is now clear under the corrected objective:
**adding our own supply of a good takes units away from them and lowers the
shared price for both -- we win the margin by selling MORE, not by holding
back.** That is exactly the DSM signature (62% of pool strawberry orders, 70%
of tomato, 39/40 wins). It is also the precise opposite of the "price
discipline" theory retracted earlier in this file.

**Next target is volume of high-value goods, not price discipline:** MILK
(cows) and STRAWBERRY together are -35,649 against a -28,752 net.

### HERD / MILK CENSUS (tools/h2h_herd.py, dawn-only snapshot, seed 200001)
(Bug caught while building this: counting every step multiplies each tile by
~24 and reported "288 cows" on a 100-tile grid. Snapshot at hour 0 only.)

| | peak COW | SHEEP | GOOSE | total | peak plants | peak STRAWBERRY | MILK sell-orders | milk revenue |
|---|---|---|---|---|---|---|---|---|
| US | **12** | 3 | **6** | 21 | 54 | 28 | **50** | 270u @260.3 = $70,294 |
| OPP | **12** | 5 | **0** | 17 | **58** | **33** | 51 | 335u @259.2 = $86,828 |

**The milk hole is NOT cow count and NOT sell frequency.** Both finish with 12
cows; sell-orders are 50 vs 51; CARE is 397 vs 404; FEED is 399 vs 336. But
they get **27.9 milk units per cow against our 22.5 (+24%)**, selling **6.55
units per order to our 5.4**. The whole -16,534 milk gap is therefore **milk
yield per cow**, isolated from every other variable measured. That is the
cleanest efficiency gap found so far and it is the next target.

Strawberry: they peak at 33 plants to our 28, consistent with the -19,115.

**The goose question is two-sided; do not answer it quickly.** We run 6 geese,
DSM and pipe19 run 0. Geese cost us ~6 plant tiles (their strawberry peak is 33
vs our 28) but they are the fert source behind our 591-unit fertilizer flood,
worth **+$10,159 to us on that good** and a genuine suppression play under the
zero-sum objective. DSM runs C9 S15 with no geese, but DSM also wins 39/40 --
"no geese" may be a consequence of DSM's strength rather than its cause.

MOVEMENT share: **US 35.9%, pipe19 38.1%**, DSM/Boey reference 42-45%. The old
"we walk 67%" figure came from the ancient 41k agent. **The walking gap is
already closed for 344** and is not available as a lever. Remaining idle gap is
PASS 622 vs 433.

### ENGINE TRUTH: how milk is actually made (read from the interpreter, not the spec)
Source: `kaggle_environments/envs/kaggriculture/kaggriculture.py:819-830`.

    days_since_first = next_day - placed_day - first_yield_day
    if days_since_first >= 0 and days_since_first % interval == 0:
        bonus = tile.pop("pending_care_bonus", 0) if tile["fed_today"] else 0
        tile["yield_units"] = min(max_held, tile["yield_units"] + 1 + bonus)
        tile["pending_care_bonus"] = 0
    if tile["cared_today"] and tile["fed_today"]:
        tile["pending_care_bonus"] = tile.get("pending_care_bonus", 0) + 1

Three things the spec summary obscured:
1. **Prod days are PER-ANIMAL**, staggered by `placed_day`. A cow placed d3 runs
   d11,13,15; one placed d8 runs d16,18,20. There is no global even-day calendar
   -- the "prod days 8,10,...,28" framing used earlier was wrong.
2. **`pending_care_bonus` is UNBOUNDED and accrues on every care+fed day**,
   then is cashed in (and reset) only on a fed prod day. So the correct play is
   care+feed EVERY day, not only on production days.
3. **The `min(max_held=6)` cap is LOSSY** -- the credit is computed, then
   discarded. A cow sitting at 6 destroys all production until harvested.

### MILK: three hypotheses tested, two REJECTED (tools/milk_audit.py, cow_cap.py, shedloss.py)
Census vs pipe19 seed 200001, all dawn-snapshotted:

| | cow-days | prod arrivals | at cap | units/productive arrival | care-bank depth |
|---|---|---|---|---|---|
| US | 254 | 88 | 10 (11.4%) | **3.46** | 43/35/5/5/5/4/2 |
| OPP | 277 | 99 | 18 (18.2%) | **4.14** | 44/37/5/6/5/2/1 |

- **REJECTED: "we under-care the herd."** Both sides feed and care every cow
  every prod day (FEED 178 vs 159, CARE 178 vs 180). The care-bank depth
  histogram is *identical*. Not a care-discipline gap.
- **REJECTED: "we let cows sit at the 6-cap and destroy production."** Our
  cap-waste is **lower** than pipe19's (11.4% vs 18.2%). If anything we harvest
  more promptly than they do.
- **REJECTED: "the shed overflows and deletes our milk."** Measured shed fill on
  every day: **peak fill 0, days at/over cap 0** for both sides. We sell through
  as we produce, so the lossy `DROP` overflow path is never reached. This kills
  the whole "cheap goods flood the shed and destroy milk" theory.
- **STILL OPEN:** 3.46 vs 4.14 units per productive arrival, and 254 vs 277
  cow-days. The cow-days gap is partly early purchase (d8: our 3 cows vs their
  8; equal 12 only by d12). The per-arrival residual is NOT explained by care,
  cap-waste, or shed overflow. Do not build a fix on a guess here.

### TILE BUDGET: the goose trade is settled (and geese stay)
Both sides occupy **exactly 75 tiles** (US 54 plants + 21 structures;
OPP 58 plants + 17 structures). We spend 6 tiles on geese, which is exactly the
6 tiles we are short on plants -- and 4 of the 4 lost strawberry plants.
- We sell **591** fertilizer vs their 367 (+224 units, **+$10,159 to us**).
- We sell **168** strawberry vs their 276 (-108 units, -$19,115).
Trading 6 geese for ~4 strawberry plants would gain ~+$4,400 strawberry and
lose ~$10,159 of fertilizer suppression plus the eggs. **Net negative: the
geese are correct.** DSM's goose-free C9 S15 herd is not a template to copy --
DSM wins 39/40 anyway, so its composition is a consequence, not a cause.

### REPLAY AUTOPSY (3 replays, /home/moh/Desktop/glm2/result/ours vs DSM)
Tools: `tools/replay_autopsy.py`, `board_discipline.py`, `weed_treadmill.py`,
`gapfill.py`, `span.py`, `tile_budget.py`.
Replays: 114953825 (ours -20,733), 114953830 (ours -45,163), 114989040 (DSM
-18,843, i.e. DSM WINS by +18,843). v348 is base 344 + a sell-ordering change
only (30 diff lines, all in the SELL block), so every board defect below is
**inherited from the base 344**, not introduced by 348.

**Causal chain, from the interpreter (not the spec):**
- L839 `_spawn_weeds`: a tile that is `None` becomes WEED with p=`weed_chance`
  per step. Default 0.005 x 24 steps => **P(idle tile weeds in a day) = 11.3%**.
- L784 a PLANT unwatered 2 days running also becomes WEED.
- `PLANT` requires `tile is None`, so **a WEED tile must be DIGged before it can
  be replanted** -- 1 hand-step, and it goes back to EMPTY where it can re-weed.
- L337 `tile = farm["tiles"][fy][fx]`: **a unit acts on the tile it STANDS ON.**
  Every animal visit and every gap-fill is pure pathing, so layout compactness
  sets the daily cost directly.

So "too many weeds" and "too many empty squares" are **ONE bug**, not two:
    idle tile --11.3%/day--> WEED --DIG--> empty --11.3%/day--> ...
An idle tile is not merely wasted capacity, it is a random generator that burns
hand-steps on a treadmill. Expected vs observed weed-tile-days matched on all
three replays (e.g. 114953830: expected 20.9, observed 53) => the weeds are
**random spawns on idle tiles, NOT a watering failure**. Fixing watering will not
fix this. Filling the tiles does.

**The DIG tax is small, so idle tiles are not expensive because of weeding:**
1.1 idle tiles/day -> 2 DIGs over 20d (0.5% of one hand) for the winner;
9.2 idle tiles/day -> 21 DIGs (4.3%) for us. Weeding is a *symptom*; the cost
is the missing PLANTS.

**TILE BUDGET, d12-d27 averages (the real defect):**

| replay | seat | PLANT | STRUCT | animal | WEED | EMPTY |
|---|---|---|---|---|---|---|
| 114953825 | winner | **62.0** | 12.4 | 12.4 | 0.1 | **0.5** |
| 114953825 | **us** | **45.2** | **20.5** | 20.4 | 2.2 | **7.0** |
| 114953830 | winner | **57.4** | 17.2 | 17.0 | 0.1 | **0.3** |
| 114953830 | **us** | **42.2** | **20.7** | 20.7 | 3.3 | **8.8** |
| 114989040 | DSM | 53.6 | 19.8 | 19.6 | **0.6** | **1.0** |
| 114989040 | opponent | 71.4 | 21.5 | 21.0 | 2.2 | 4.9 |

**We lose ~15-17 PLANT TILES PER DAY to structure hoarding plus idleness.** In
114953825 we hold +8.1 structures and +6.5 empty tiles and pay -16.8 plants. A
PASTURE or COOP is a plant tile that is not growing anything, and every extra
one is also another tile the care/feed tour must reach.

**This CORRECTS the earlier goose conclusion.** The cow_cap.py reasoning was
sound arithmetic (+$10,159 fertilizer suppression vs ~$4,400 strawberry) but it
was computed on ONE seed vs pipe19, where both sides ran 12 cows. In these
replays the winners run **12-14 structures against our 20-21** and convert the
difference into 15+ more plant tiles, and they win. Structure count, not goose
count, is the variable that matters. Do not defend 6 geese on fertilizer math
again without checking the structure/plant exchange rate.

**Hand redundancy -- the user's "workers going to the same place" question,
answered: it is real but it is NOT what loses the game.**
- Two hands on the same tile in one step: ours 1138 over 515 steps (71.5% of
  steps) vs the winner's 621 over 270 (37.5%) in 114953825; 1033/476 (66.1%) vs
  576/245 (34.0%) in 114953830.
- BUT movement share is ~43% for BOTH seats, and the winners actually issue
  MORE hand-steps (5911 vs our 6745 is us having MORE; winners 6047 vs 7402).
  Collision count tracks board fragmentation, not waste: two hands converge on
  the same tile because the tiles worth working are clustered.
- **Do not build a "spread the hands out" fix.** It is a symptom of hoarded
  structures, and it would move a metric that is not costing us money.

**Herd layout is NOT the differentiator either.** Serpentine tour over animal
tiles: winners 13-23, us 21-28, DSM 25. Nearest-neighbour mean 1.00-1.11 for
everyone. DSM's own herd is *less* compact than the opponent he beat. Layout is
adequate; the tour cost is small relative to 15 missing plant tiles.

**The single DSM behaviour worth copying is DISCIPLINE, not layout.** In
114989040 DSM ran 0.6 weeds and 1.0 empty tiles against the opponent's 2.2 and
4.9 -- and DSM **bought no land after d10** (25 tiles stayed LOCKED all game),
keeping his 75-tile board ~99% full. He does not sprawl and he does not idle.
Note DSM ran FEWER plants than the opponent he beat (53.6 vs 71.4) and still won
+18,843, so raw plant count is not the objective either -- but he is not
*leaking* tiles, and we leak 7-9 every single day.

**GAP-FILL: we do not lack seeds or hands, we lack priority.**
PLANTs issued on days that already had >=5 idle tiles: ours 73% and 55% of all
our plantings (mean 9.7 and 12.1 idle tiles at the moment of planting), vs the
winners' 31% and 11% (mean 4.5 and 2.4) and DSM's 8% (mean 2.6). We are
actively choosing to replant a harvested tile while nine tiles sit empty. That
is a **hand-priority ordering bug**, and it is the highest-value fix on the
board: it converts directly into plant tiles, which is the measured deficit.


## dsmG4/G5 -- 19-REPLAY CONCEPT MINE (supersedes the idle-tile story)

Built `tools/concept_mine.py` and mined all 19 replays in
`/home/moh/Desktop/glm2/result/ours vs DSM` (16 new). 8 of them are our own
losses. Comparing us against whoever beat us, in each game:

    concept        us      beater   held
    struct_frac   25.69%   18.24%    8/8
    plant_avg     34.44    46.20     0/8
    plant_peak    53.75    68.88     0/8
    feed/day      12.09     8.04     8/8
    care/day      11.21     8.41     7/8
    herd          21.12    16.12     7/8
    goose          7.25     3.88     6/8
    unlocked_max  75.00    87.50     0/8   <- we NEVER take the 4th quadrant

**Correction to the previous section: the idle-tile story was largely a red
herring.** In 114989040 and 115210298 we had FEWER empty tiles than the agent
that beat us and still lost. Empty/weed were a symptom, not the cause.

**Correction to my own earlier advice, twice, on evidence:**
1. I suggested "decline the 4th quadrant." WRONG. `land_want()` clamps
   `w = 2` forever, so we already sit at 75 tiles. 10 of 19 winners finished on
   100 tiles; we finished on 75 in 8 of 8 losses. The clamp was the bug.
2. I suggested "chase milk" first. The animal labour burden (feed 8/8, care
   7/8) is real but not fixable by cutting animals -- see below.

### Tested and FALSIFIED (do not retry)
- **GOOSEC** (cap geese at 3): margin-delta **-3574, t=-2.38 vs pipe19**.
  Significantly WORSE. The 7.25-vs-3.88 goose correlation is not causal.
- **HERDC** (decouple herd_cap from hands; identical to dsmG2 GCAP): -59093
  gap, idle got worse. The struct_frac 8/8 signal is real but neither lever
  that would exploit it is profitable.
- **LANDQ=3 + GOOSEC=3**: +3440, t=1.10 -- the goose cut cancels the land gain.

### VALIDATED: my_dsmG5.py (take the 4th quadrant)
`land_want` no longer clamps to 2 plots. Mechanism confirmed: plant avg
43.81 -> 49.31 (+5.5 plants), reward +1532 solo.

    gate            vs pipe19          vs v57
    18 seeds    +3180 (t=2.04)     +3190 (t=2.07)
    holdout 12  +2661 (t=2.74)     +2659 (t=2.69)
    (sub-2k deltas zeroed: ~+2750 both)

Passes the full acceptance gate on both opponents and both seed sets.
Submission invariant verified: `agent` is the last top-level def, nothing
after it, no env dependency (only the pre-existing LINE_FORCE debug hook).
`my_dsmG5.py` is the new production candidate; `my_dsm344.py` stays immutable.

**Tooling note:** the first version of concept_mine.py nested the action census
inside the `hour == 0` branch and so counted 1/24 of all actions while still
dividing by the 30-day board count. That understated every action concept 24x
and briefly made "harvest/day" and "pass/day" look like discriminators. Fixed
before any decision was made on those numbers.

## dsmG6: RACE (opp_v57) -- promising, NOT validated

Read the opponent source instead of inferring it:
- `opp_pipe19.py:505 _hand_align` is only PASS padding -- NOT the mechanism.
- `opp_v57.py:3729-3770 RACE` is a **sale-reservation race**, and their own
  comment states the rule: "Premium books crash within ~60 units of glut, so
  the first seller of a lot takes the price and the second sells into the
  crash." They hold planned sales ~40 turns deep (window opens step 192, day 8)
  so their lot lands BEFORE the rival's, accepting lost town-demand recovery.
  They also report deeper is worse (48/12 falls to 14-26).
- Both opponents hard-guard exactly 3 quadrants
  (`set(farm['unlocked_quadrants']) != {'NW','NE','SW'}` -> abstain,
  opp_v57.py:1267). They never take the 4th, so G5's land gain is not copying
  them -- it is exploiting a hole in their policy.

Our sell block (`my_dsmG5.py:561`) has the OPPOSITE polarity: it batches a
partial lot while the quote is healthy and full-dumps at `px < 0.92*BASE`,
i.e. it waits for the price to fall and then sells into it. RAHIGH=1 sells the
full lot while the quote is up instead.

    vs pipe19 n=12   +868  (t=1.15)
    vs v57    n=18   +665  (t=1.33)

Same sign both opponents, but under the t>=2.0 bar, and many seeds are exact
no-ops (dm=+0) where the shed lot is already below BATCH. **Not adopted.**
The concept is real and unexploited; the current knob is too weak because the
4-orders-per-step SELL cap binds before the price effect does. The next
version should race the ORDER SEQUENCE (which product we sell first, given the
rival's observed lot), not just the batch size.

### FOUR HYPOTHESES TESTED, ALL FOUR FALSIFIED (do not repeat these)
The idle-tile gap is real and reproducible (8.19 idle/1.94 weed vs pipe19's
0.31/0.06 on seed 200001, measured by `tools/idle_census.py`), but **none of the
obvious causes survived measurement.** Every variant below reproduced 344
exactly at its neutral setting before testing.

1. **"We under-prioritise gap-fill" (my_dsmG1, GFILL).** Raised idle-tile seek
   value 4.5 -> 7.5 with idleness ramp, and exempted gap-fill from the radius
   cap. **INERT: idle 8.19 -> 8.00, and weeds got WORSE 1.94 -> 3.06.** The
   units were already being routed to empty tiles; priority was not the
   constraint.
2. **"We hoard animal structures" (my_dsmG2, GCAP).** `herd_cap = 4 + 2*hands`
   couples crew size to board occupancy, so each hire authorises more animals
   and each animal steals a plant tile. Capped it at 10/12/14/16. **FALSIFIED:
   capping FREED tiles but idle went UP (8.19 -> 9.3 at GCAP=14, 11.0 at 16,
   15.6 at 10) and reward fell at every cap.** Freeing a tile does not make us
   plant on it, so the tile was never the binding constraint.
3. **"PLANTs are being voided" (the atomic rule, kaggriculture.py:921-928).**
   Requests over the seed count void *every* PLANT of that crop that turn --
   a real footgun. **FALSIFIED by `tools/plant_void.py`: 245 requests, 0 voided,
   0 turns hit the rule** (and pipe19: 239 requests, 0 voided). Never fires.
4. **"Value is drowned by distance in seek" (my_dsmG3, GVAL).** The scoring
   line is `score = -d + 0.09*val`, so value is worth less than one tile of
   distance and the nearest plant always wins. Raised the weight 1->2->4.
   **NEARLY INERT: idle 8.19 -> 9.19 (GVAL=2) -> 6.94 (GVAL=4), reward flat
   (-45.7k, -49.5k vs -49.6k baseline).** Weed fell sharply at GVAL=2
   (1.94 -> 0.38), so the mechanism is real but the size is not the prize.

**What this rules out, stated plainly:** the ~15-17 missing plant tiles are NOT
caused by seek priority, NOT by structure hoarding, NOT by seed starvation, and
NOT by the PLANT-void rule. The measured 29 spare WHEAT seeds sitting in pocket
while 20 tiles are empty (`tools/why_idle.py`) says the binding constraint is
**hand availability and route length, not intent or resources** -- the crew is
busy on the 43% of turns it spends MOVING (2888 MOVE vs 3341 work acts), and
the board is too spread to close every hole each day.

**Standing recommendation: do not ship G1/G2/G3.** None improves the H2H margin
on the one seed tested, and G2 actively loses. The honest next step is to
measure *where the crew's 3341 work acts actually go* and what the marginal
tile would cost in travel, before proposing another priority change. Two
falsifications in a row on the same hypothesis means the model of the defect is
wrong, not that the knob is too small.

### NET (corrected -- the earlier NET block is superseded and was wrong)
- **Base remains my_dsm344.py and there is NO validated candidate.** v348 is
  -1,135 / -1,138 on the real objective and is NOT a candidate. vM1 is a solo
  mirage. Base is the default because nothing beat it, not out of inertia.
- v351-v355: all rejected or byte-identical; v354 (combo) and v355 (radius)
  were dead levers. vW1 (water urgency): rejected, monotonic, and it retired
  the weed-death target entirely.
- **OBJECTIVE CORRECTED (user, and it is right): maximize
  (my cash - opponent cash), NOT my cash.** We sit at ~145k solo, above DSM's
  ~117k and Boey's ~110k, and still lose. Our fertilizer flood (591u vs 367u,
  +$10,159) is a WIN, not waste.
- Live leads, by measured size:
  1. **STRAWBERRY -19,115: 168 units sold vs 276.** Both sides fill exactly 75
     tiles, so this is a *plant mix* question, not a space question.
  2. **MILK -16,534: 3.46 vs 4.14 units per productive prod-day.** Cause NOT
     care, NOT cap-waste, NOT shed overflow -- all three measured and rejected.
  3. **Cow-days 254 vs 277**: they buy cows earlier (d8: 8 cows vs our 3).
  4. **d10 melon cliff -$9,864.** Understood mechanically, but the fix does not
     move the H2H margin because both seats crash the same price.
- **Screening rule now in force: H2H margin only, both opponents, n>=12, and
  treat sub-2k deltas as zero. Solo is a smoke test and nothing more.**
- **Tooling rule learned the hard way, twice: snapshot per-tile counters at
  `hour == 0` ONLY.** Counting every step multiplies each tile by ~24 and
  reported 288 cows on a 100-tile grid. Both `h2h_herd.py` and `cow_cap.py`
  shipped this bug before it was caught.
