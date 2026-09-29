# AGENT PROMPT — finish the job: beat all 8 Kaggriculture agents. No give-up.

You are taking over a Kaggriculture (kaggle-environments 1.32.7) agent-vs-agent task from a
previous agent. Everything you need is in this folder. Read `HANDOFF.md` FIRST (state,
scores, engine facts, opp intel, gaps, commands, protocol), then follow this prompt exactly.

## STEP 0 — Prove the environment works (do this before ANY agent work)
1. `pip show kaggle-environments 2>/dev/null | head -3` — MUST be 1.32.7. If missing/wrong,
   install it first; nothing below is valid otherwise.
2. `python3 panel_2games.py final_agent.py` — MUST finish 16 games with
   TOTAL ≈ −682637, WINS 0/16, AVG ≈ −42665 (±2000 is fine, RNG/loops vary slightly).
   If it errors or the numbers are wildly different, STOP and fix the env/paths first.
3. `python3 gap_diag.py final_agent.py 300001` — MUST print a day-by-day table ending with a
   reward ≈ 143k–163k. This proves solo mode works.

## How you know a result is REAL (noise discipline — violations waste hours)
- This game has ±15–30k per-game H2H noise: your actions shift shared prices, town-shop
  draws, and weed spawns (all draw from one shared game RNG). A +10k margin on 2 games
  means NOTHING.
- Golden rule: screen cheap (solo3 seeds 300001–300003 + pipe19 200001/200002), promote
  ONLY on all three: (a) solo6 (300001–300006) mean NOT down vs `final_agent.py`,
  (b) full `panel_2games.py` AVG up with most of the 16 games improving,
  (c) fresh-seed H2H (300001/300002, then new seeds like 400001+) not collapsing.
- Always log US absolute + OPP absolute + margin. Margin alone LIES (you can "improve"
  margin by crashing the shared market so the opp loses more than you — while YOUR score
  goes down; that is failure, reject it).
- One themed change per candidate file (`cand_<name>.py` copied from `final_agent.py`).
  If a package fails, BISECT it into single-change files and test each — never stack blind.
- Never touch `opps/`. Never hardcode seed-specific behavior (fresh seeds will grade you).

## THE TASK
`python3 panel_2games.py <your_agent.py>` must reach **WINS 16/16** (beat pipe19, pipe18,
kagg, v57, base_v76, main, main1, main_copy_1 on seeds 200001 AND 200002, you are seat 0).
Current: 0/16, AVG −42,665. You must close ~43k per game AND win every game. There is no
partial credit and no giving up — keep iterating: diagnose → hypothesize → implement →
screen → validate → stack winners → repeat.

## Rules of engagement
- You may do ANYTHING: micro-edits, subsystem rewrites (dispatch, sell engine, shopping,
  herd logic), or a full from-scratch rewrite of the agent. Only results count.
- Keep the agent interface: file defines `agent(observation, configuration)` as the LAST
  callable; actions are `{'farmer': [...], 'hands': [[...], ...], 'market': [[OP, ITEM, N], ...]}`.
- General, not overfit: every economic behavior must make sense on fresh seeds (price
  floors, feed safety, wallet gates). If a change only wins on 200001/200002, kill it.
- Suggested attack order (measured gaps, biggest first): (1) strawberry volume + harvest
  completeness (opp $47–60k vs our $11k — SEEDCAP 14, seed trickle, planter/water labor);
  (2) milk per-cow same-day feed+care stack + early-sprint timing; (3) d0–d3 melon count
  (12 vs 6) WITHOUT breaking the d0 wallet cliff (d0 overspend → wheat gap → escapes →
  −20k; fund via sales float, never via starvation); (4) d6 wallet wave (fert-manure cash
  engine from d1 like the opp); (5) movement/labor (2.2× bank trips, late travel, d29
  terminal sweep). Sketches for each are in HANDOFF.md §6.
- Goose/egg scale-up is the only glut-proof income (never collapses) but opp skips geese —
  test, don't assume. Fert-manure sprint (sell d1+, never hoard, stop buy-to-sell) is
  proven opp tech — copy the economics, not the tape.
- When done: `final_agent.py` = your champion (agent() last, loads clean), plus a short
  note of final panel + solo6 numbers. Finish means 16/16. Do not stop early.
