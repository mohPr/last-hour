"""IDLE-TILE CENSUS on a live env: did the gap-fill change actually fill tiles?

The replay autopsy found we leak 7-9 tiles/day to idleness (and to the 11.3%/day
weed generator that idleness feeds). This is the direct A/B for a candidate:
mean unlocked-but-idle tiles per day, d12-d27, plus weed count.

Usage: python3 tools/idle_census.py <file.py> <opp.py|-> [seed]
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fast_kaggr_env import FastKaggrEnvPy as Env   # noqa: E402
from harness import load                           # noqa: E402

STRUCT = ("PASTURE", "COOP", "BARN")
ap = sys.argv[1]
opp = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 200001
nsA = load(ap, "newA")
nsO = load(opp, "opp") if opp else None
env = Env({"seed": seed, "episodeSteps": 720})
env.reset(2)
D = {"farmer": ["PASS"], "hands": [], "market": []}

idle = [defaultdict(int), defaultdict(int)]
weed = [defaultdict(int), defaultdict(int)]
plant = [defaultdict(int), defaultdict(int)]
acts = [defaultdict(int), defaultdict(int)]


def tiles_of(o, seat):
    try:
        f = o.farms[seat]
        if not isinstance(f, dict):
            return []
        fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
        return f.get("tiles", []) or fq.get("tiles", []) or []
    except Exception:
        return []


while not env.done:
    o0, o1 = env.state[0].observation, env.state[1].observation
    day, hour = int(o0.day), int(o0.hour)
    obs = (o0, o1)
    rets = []
    for seat in (0, 1):
        if seat == 0 and nsO is None:
            rets.append(dict(D))
            continue
        ns = nsA if seat == 0 else nsO
        try:
            r = ns["agent"](obs[seat], None)
        except Exception:
            r = dict(D)
        rets.append(r)
        for h in ([r.get("farmer")] + list(r.get("hands") or [])):
            for k in (h or []):
                acts[seat][str(k[0] if isinstance(k, (list, tuple)) and k else k)] += 1
        if hour == 0:
            for row in tiles_of(obs[seat], seat):
                for c in row:
                    k = (c if isinstance(c, str) else (c or {}).get("kind")) \
                        if c is not None else "EMPTY"
                    if k == "EMPTY":
                        idle[seat][day] += 1
                    elif k == "WEED":
                        weed[seat][day] += 1
                    elif k == "PLANT":
                        plant[seat][day] += 1
    env.step(rets)

w = list(range(12, 28))
print("=== IDLE CENSUS: %s  seed %d%s ===" % (
    os.path.basename(ap), seed, "  vs " + os.path.basename(opp) if opp else ""))
print("rewards: A %.0f%s" % (
    env.state[0].reward,
    "  OPP %.0f  gap %+.0f" % (env.state[1].reward,
                               env.state[0].reward - env.state[1].reward) if nsO else ""))
nm = "US " if nsO else "A  "
print("  %s idle avg %5.2f peak %2d | weed avg %5.2f peak %2d | plant avg %5.2f peak %2d"
      % (nm, sum(idle[0][d] for d in w) / 16.0, max(idle[0][d] for d in w),
         sum(weed[0][d] for d in w) / 16.0, max(weed[0][d] for d in w),
         sum(plant[0][d] for d in w) / 16.0, max(plant[0][d] for d in w)))
if nsO:
    print("  OPP idle avg %5.2f peak %2d | weed avg %5.2f peak %2d | plant avg %5.2f peak %2d"
          % (sum(idle[1][d] for d in w) / 16.0, max(idle[1][d] for d in w),
             sum(weed[1][d] for d in w) / 16.0, max(weed[1][d] for d in w),
             sum(plant[1][d] for d in w) / 16.0, max(plant[1][d] for d in w)))
print("  PLANT acts %d | DIG %d" % (acts[0]["PLANT"], acts[0]["DIG"]))
