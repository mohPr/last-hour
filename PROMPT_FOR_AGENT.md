# AGENT PROMPT — finish the job: beat all 9 Kaggriculture agents. No give-up.

You are taking over a Kaggriculture (kaggle-environments 1.32.7) agent-vs-agent task from a
previous agent. Everything you need is in this repo. Read `HANDOFF.md` FIRST (state,
scores, engine facts, opp intel, gaps, commands, protocol), then read `FINDINGS.md` IN
FULL (prior session's falsified-variant log — do not re-run its rejected list), then read
the analysis markdown inside `reference_master_agent.ipynb` (game-theoretic notes + DSM
blueprint), then follow this prompt exactly.

## STEP 0 — Prove the environment works (do this before ANY agent work)
1. `pip show kaggle-environments 2>/dev/null | head -3` — MUST be 1.32.7. If missing/wrong,
   install it first; nothing below is valid otherwise.
2. `python3 panel_2games.py final_agent.py` — MUST finish 18 games with
   TOTAL ≈ −771081, WINS 0/18, AVG ≈ −42838 (±2000 is fine). If it errors or the numbers
   are wildly different, STOP and fix the env/paths first.
3. `python3 gap_diag.py final_agent.py 300001` — MUST print a day-by-day table ending with a
   reward ≈ 143k–163k. This proves solo mode works.
4. `python3 gap_diag.py opps/opp_master.py 300001` — MUST end with reward ≈ 172k. This
   proves the 9th opponent (notebook-extracted master agent) runs.

## How you know a result is REAL (noise discipline — violations waste hours)
- This game has ±15–30k per-game H2H noise: your actions shift shared prices, town-shop
  draws, and weed spawns (all draw from one shared game RNG). A +10k margin on 2 games
  means NOTHING. Any code change reshuffles the species line via shop RNG: 2-seed
  screens cannot resolve effects under ~10–20k.
- **H2H margin is the ONLY acceptance metric. Solo NEVER predicts H2H** (measured:
  value-sorted selling +4.3k solo / −1.1k H2H; melon-window tweak +3.4k solo / ~0 H2H).
  Solo is a smoke test, nothing more.
- Golden rule: screen H2H vs BOTH pipe19 and v57 (a win vs one opp only is mimicry),
  n≥12 H2H games for finalists, treat sub-2k deltas as zero. Promote ONLY on all three:
  (a) solo6 (300001–300006) mean NOT down vs `final_agent.py` (guard, not verdict),
  (b) full 18-game `panel_2games.py` AVG up with most games improving,
  (c) fresh-seed H2H (new seeds like 400001+) not collapsing.
- Always log US absolute + OPP absolute + margin. Margin alone LIES (you can "improve"
  margin by crashing the shared market so the opp loses more than you — while YOUR score
  goes down; that is failure, reject it).
- One themed change per candidate file (`cand_<name>.py` copied from `final_agent.py`).
  If a package fails, BISECT it into single-change files and test each — never stack blind.
- Never touch `opps/`. Never hardcode seed-specific behavior (fresh seeds will grade you).

## THE TASK
`python3 panel_2games.py <your_agent.py>` must reach **WINS 18/18** (beat pipe19, pipe18,
kagg, v57, base_v76, main, main1, main_copy_1, AND opp_master on seeds 200001 AND 200002,
you are seat 0). Current: 0/18, AVG ≈ −43k. You must close ~43k per game AND win every
game. There is no partial credit and no giving up — keep iterating: diagnose →
hypothesize → implement → screen H2H → validate → stack winners → repeat.

## Rules of engagement
- You may do ANYTHING: micro-edits, subsystem rewrites (dispatch, sell engine, shopping,
  herd logic, land policy), or a full from-scratch rewrite of the agent. The notebook's
  game-theoretic analysis and the DSM structural blueprint (C9 S15, 24 animals by d11,
  d0 20-plant sweep, reinvest-to-$0 d1–10, d11 melon payday) are yours to exploit.
  Only results count.
- Keep the agent interface: file defines `agent(observation, configuration)` as the LAST
  callable; actions are `{'farmer': [...], 'hands': [[...], ...], 'market': [[OP, ITEM, N], ...]}`.
- General, not overfit: every economic behavior must make sense on fresh seeds (price
  floors, feed safety, wallet gates). If a change only wins on 200001/200002, kill it.
- Suggested attack order (measured gaps, biggest first): (1) strawberry volume + water
  coverage over the 26-day life (opp $47–60k vs our $11k; eve coverage is fine at 90%,
  DAY coverage is 57%); (2) milk yield per cow 22.5→27.9 (cause OPEN — not care, cap, or
  shed; measure per-prod-day arrivals before guessing); (3) d10 melon mass-pick, 12
  plants harvested d10 same-morning (late decay 5.0→4.0→3.0u, −$9.9k hole) WITHOUT
  breaking the d0 wallet cliff (d0 is SEALED: H4/2C+3S/M6 — 5th hire −40k); (4) 4th
  quadrant (unclamp land, validated +3.2k H2H); (5) sale-reservation RACE vs opp bulk
  waves (first seller takes the price; race order-sequence, not just batch size);
  (6) d6 wallet wave (fert-manure cash engine from d1 like the opp). Full sketches,
  numbers, and dead-ends for each are in HANDOFF.md §6 and FINDINGS.md.
- Geese STAY (fert-flood +$10k suppression; goose cap falsified at −3.5k). Wheat harvest
  gate stays yld≥2 (raising it loses −21 to −27k twice). Deaths are a symptom, not a
  target. Do not re-litigate FINDINGS.md's closed cases without new evidence.
- When done: `final_agent.py` = your champion (agent() last, loads clean), plus a short
  note of final panel + solo6 numbers. Finish means 18/18. Do not stop early.
