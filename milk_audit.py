"""COW PROD-DAY COMPLIANCE audit.

Census (tools/h2h_herd.py) showed the milk hole is NOT cow count (12 vs 12) and
NOT sell frequency (50 vs 51 orders) -- it is 22.5 vs 27.9 UNITS PER COW at
identical CARE/FEED totals. This tool finds the mechanism.

Engine rule (DSM_SPEC.md:149-155), COW first=8 interval=2, so prod days are
8,10,12,...,28. On a prod day EOD each cow yields:
    base 1  +  pop(bonus) iff fed_today  +  1 iff (cared AND fed same day)
So the +2 stack needs BOTH feed and care on the same prod day, and the day must
also be HARVESTed (yield>0 and age>=first). Any one of the three missing costs
1-2 units per cow per prod day -- which is exactly the size of our gap (5.4).

Usage: python3 tools/milk_audit.py <our.py> <opp.py> [seed]
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fast_kaggr_env import FastKaggrEnvPy as Env   # noqa: E402
from harness import load                           # noqa: E402

# COW: first=8, interval=2 -> production on even days from 8.
PROD_DAYS = set(range(8, 30, 2))
ANIMALS = ("COW", "SHEEP", "GOOSE")
ap, op = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 200001
nsA, nsO = load(ap, "newA"), load(op, "opp")
env = Env({"seed": seed, "episodeSteps": 720})
env.reset(2)
D = {"farmer": ["PASS"], "hands": [], "market": []}


def farm_of(o, seat):
    try:
        f = o.farms[seat]
    except Exception:
        return {}
    return f if isinstance(f, dict) else {}


def tiles_of(o, seat):
    f = farm_of(o, seat)
    fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
    return f.get("tiles", []) or fq.get("tiles", []) or []


def head(o, seat):
    out = dict.fromkeys(ANIMALS, 0)
    for row in tiles_of(o, seat):
        for t in row:
            if isinstance(t, dict) and t.get("animal") in ANIMALS:
                out[t["animal"]] += 1
    return out


def pocket(o):
    """Total pocket goods per commodity at this instant."""
    try:
        inv = (o.private or {}).get("inventories") or []
    except Exception:
        return {}
    tot = defaultdict(float)
    for u in inv:
        for k, v in (u or {}).items():
            if isinstance(v, (int, float)):
                tot[k] += v
    return tot


dawn_head = [defaultdict(int), defaultdict(int)]
dawn_milk = [defaultdict(float), defaultdict(float)]
sellq = [defaultdict(float), defaultdict(float)]
selln = [defaultdict(int), defaultdict(int)]
# per-day, per-action counts: acts[seat][action][day]
acts = [{a: defaultdict(int) for a in
         ("FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER", "WHEAT")}
        for _ in (0, 1)]

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
        if hour == 0:
            h = head(obs[seat], seat)
            for a in ANIMALS:
                dawn_head[seat][(a, day)] = h[a]
            dawn_milk[seat][day] = pocket(obs[seat]).get("MILK", 0.0)
        for k in (r.get("farmer") or []):
            if k in acts[seat]:
                acts[seat][k][day] += 1
        for hh in (r.get("hands") or []):
            for k in (hh or []):
                if k in acts[seat]:
                    acts[seat][k][day] += 1
        for od in (r.get("market") or []):
            if od and str(od[0]) == "SELL" and len(od) >= 2 and od[1] == "MILK":
                q = od[2] if len(od) > 2 and isinstance(od[2], (int, float)) else 1
                sellq[seat][day] += q
                selln[seat][day] += 1
    env.step(rets)

print("=== COW PROD-DAY AUDIT: %s (US) vs %s seed %d ===" % (
    os.path.basename(ap), os.path.basename(op), seed))
print("rewards: US %d  OPP %d  gap %+d" % (
    round(env.state[0].reward), round(env.state[1].reward),
    round(env.state[0].reward - env.state[1].reward)))
print("prod days (COW first=8 interval=2): %s" % sorted(PROD_DAYS))

print("\n  side day | cows | FEED CARE HARV COLLECT | pocketMILK@dawn | sold n/qty")
for seat, nm in ((0, "US "), (1, "OPP")):
    for d in sorted(PROD_DAYS):
        c = dawn_head[seat][("COW", d)]
        if not c and not dawn_milk[seat][d]:
            continue
        A = acts[seat]
        print("  %s  %3d | %4d | %5d %4d %6d %7d | %13.0f | %4d %5.0f"
              % (nm, d, c, A["FEED"][d], A["CARE"][d], A["HARVEST"][d],
                 A["COLLECT_FERTILIZER"][d], dawn_milk[seat][d],
                 selln[seat][d], sellq[seat][d]))
    print()

print("--- totals over prod days (the ones that score) ---")
for seat, nm in ((0, "US "), (1, "OPP")):
    A = acts[seat]
    pd_feed = sum(A["FEED"][d] for d in PROD_DAYS)
    pd_care = sum(A["CARE"][d] for d in PROD_DAYS)
    cow_days = sum(dawn_head[seat][("COW", d)] for d in PROD_DAYS)
    tot = sum(sellq[seat].values())
    print("  %s cow-prod-days=%-4d FEED=%-5d CARE=%-5d  milk sold=%.0f  "
          "units/cow-day=%.2f" % (nm, cow_days, pd_feed, pd_care, tot,
                                  tot / max(1, cow_days)))
