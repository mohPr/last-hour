"""COW CAP-WASTE + CARE-BANK audit.

Read from the OFFICIAL interpreter (kaggriculture.py:819-830), not the spec:

    days_since_first = next_day - placed_day - first_yield_day
    if days_since_first >= 0 and days_since_first % interval == 0:
        base = 1
        bonus = tile.pop("pending_care_bonus", 0) if tile["fed_today"] else 0
        yield_units = min(max_held, yield_units + base + bonus)   # CAP 6, LOSSY
        pending_care_bonus = 0
    if cared_today and fed_today:
        pending_care_bonus += 1                                  # UNBOUNDED

Three consequences that the spec summary hid:
  1. PROD DAYS ARE PER-ANIMAL, staggered by placed_day. A cow placed d3 runs
     d11,13,15...; one placed d8 runs d16,18,20... There is no global calendar.
  2. pending_care_bonus ACCRUES on every non-prod day and is only cashed in on a
     fed prod day. So care+feed EVERY day, not only on prod days.
  3. The min() cap is LOSSY: credit is computed, then discarded. A cow sitting at
     6 destroys all production until harvested.

This tool measures, per side: care-bank depth, and cap-waste (prod-day arrivals
that found the cow already full).

Usage: python3 tools/cow_cap.py <our.py> <opp.py> [seed]
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fast_kaggr_env import FastKaggrEnvPy as Env   # noqa: E402
from harness import load                           # noqa: E402

FIRST, INTERVAL, MAXHELD = 8, 2, 6     # COW, from ANIMALS table
ap, op = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 200001
nsA, nsO = load(ap, "newA"), load(op, "opp")
env = Env({"seed": seed, "episodeSteps": 720})
env.reset(2)
D = {"farmer": ["PASS"], "hands": [], "market": []}


def tiles_of(o, seat):
    try:
        f = o.farms[seat]
        if not isinstance(f, dict):
            return []
        fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
        return f.get("tiles", []) or fq.get("tiles", []) or []
    except Exception:
        return []


bank = [defaultdict(int), defaultdict(int)]         # care-bank depth -> cow-days
capwaste = [0, 0]
prodcount = [0, 0]
caredays = [0, 0]
firstprod = [None, None]
cows_live = [defaultdict(int), defaultdict(int)]
harvest_acts = [defaultdict(int), defaultdict(int)]

while not env.done:
    o0, o1 = env.state[0].observation, env.state[1].observation
    day, hour = int(o0.day), int(o0.hour)
    obs = (o0, o1)
    rets = []
    for seat in (0, 1):
        ns = nsA if seat == 0 else nsO
        try:
            r = ns["agent"](obs[seat], None)
        except Exception:
            r = dict(D)
        rets.append(r)
        # dawn snapshot ONLY: counting every step multiplies by ~24 per day.
        if hour != 0:
            for hh in ([r.get("farmer")] + list(r.get("hands") or [])):
                for k in (hh or []):
                    if k == "HARVEST":
                        harvest_acts[seat][day] += 1
            continue
        for row in tiles_of(obs[seat], seat):
            for t in row:
                if not isinstance(t, dict) or t.get("animal") != "COW":
                    continue
                cows_live[seat][day] += 1
                placed = int(t.get("placed_day", day))
                y = int(t.get("yield_units", 0) or 0)
                pb = int(t.get("pending_care_bonus", 0) or 0)
                caredays[seat] += 1
                if pb > 0:
                    bank[seat][pb] += 1
                # EOD of day-1 credited to arrive here at dawn of `day`:
                dsf = day - placed - FIRST
                if dsf >= 0 and dsf % INTERVAL == 0:
                    prodcount[seat] += 1
                    if firstprod[seat] is None:
                        firstprod[seat] = day
                    if y >= MAXHELD:
                        capwaste[seat] += 1
        for hh in ([r.get("farmer")] + list(r.get("hands") or [])):
            for k in (hh or []):
                if k == "HARVEST":
                    harvest_acts[seat][day] += 1
    env.step(rets)
print("=== COW CAP-WASTE / CARE-BANK: %s (US) vs %s seed %d ===" % (
    os.path.basename(ap), os.path.basename(op), seed))
print("rewards: US %d  OPP %d  gap %+d" % (
    round(env.state[0].reward), round(env.state[1].reward),
    round(env.state[0].reward - env.state[1].reward)))
print("\n side | cow-days | prod-day arrivals | arrived AT CAP(6) | wasted%% | first prod | peak cows")
for seat, nm in ((0, "US "), (1, "OPP")):
    n = max(1, prodcount[seat])
    pk = max(cows_live[seat].values()) if cows_live[seat] else 0
    print("  %s  | %7d | %17d | %17d | %6.1f%% | %10s | %8d" % (
        nm, caredays[seat], prodcount[seat], capwaste[seat],
        100.0 * capwaste[seat] / n, firstprod[seat], pk))

print("\n--- care-bank depth (pending_care_bonus observed at dawn) ---")
depths = sorted(set(list(bank[0]) + list(bank[1])))
print("  depth :  " + " ".join("%5d" % d for d in depths))
for seat, nm in ((0, "US "), (1, "OPP")):
    tot = max(1, sum(bank[seat].values()))
    print("  %s  |  " % nm + " ".join(
        "%4.0f%%" % (100.0 * bank[seat][d] / tot) for d in depths))
print("  (depth d means the cow had banked d care-days -> cashes in d+1 units,")
print("   so the deepest banks are the highest-yield harvests)")
