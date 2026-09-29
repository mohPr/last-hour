"""Per-seat day-by-day economic trace: US vs a live opponent.

Target 2: pipe19 holds ~$20k on d12 where we hold ~$6k. Cash is the output of
every path at once, so this traces the inputs alongside it: sell revenue, hand
count, plant count, animal head, and act mix, per seat per day. The question is
not "are we poorer" but "which input is smaller on the days it matters".

Usage: python3 tools/h2h_cash.py <our.py> <opp.py> [seed]
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fast_kaggr_env import FastKaggrEnvPy as Env   # noqa: E402
from harness import load                           # noqa: E402

ANIMALS = ("COW", "SHEEP", "GOOSE")

ap, op = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 200001
nsA, nsO = load(ap, "newA"), load(op, "opp")
env = Env({"seed": seed, "episodeSteps": 720})
env.reset(2)
D = {"farmer": ["PASS"], "hands": [], "market": []}

cash = [defaultdict(float), defaultdict(float)]     # seat->day->$
sell = [defaultdict(float), defaultdict(float)]     # seat->day->$
plants = [defaultdict(int), defaultdict(int)]
hands = [defaultdict(int), defaultdict(int)]
heads = [defaultdict(int), defaultdict(int)]
acts = [defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))]


def farm_of(o, seat):
    # per-seat farm is o.farms[seat]; it may nest one level under "farms".
    try:
        f = o.farms[seat]
    except Exception:
        return {}
    if not isinstance(f, dict):
        return {}
    fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
    if "money" not in f and "money" in fq:
        return fq
    return f


def sell_orders(r):
    out = []
    for od in (r.get("market") or []) if isinstance(r, dict) else []:
        if od and str(od[0]) == "SELL" and len(od) >= 3:
            out.append((od[1], float(od[2])))
    return out


while not env.done:
    o0, o1 = env.state[0].observation, env.state[1].observation
    day = int(o0.day)
    obs = (o0, o1)
    rets = []
    for seat in (0, 1):
        ns = nsA if seat == 0 else nsO
        try:
            r = ns["agent"](obs[seat], None)
        except Exception:
            r = dict(D)
        rets.append(r)
        f = farm_of(obs[seat], seat)
        if f:
            cash[seat][day] = float(f.get("money", 0) or 0)
            hands[seat][day] = len(f.get("hands") or [])
            tiles = f.get("tiles") or []
            np_ = na = 0
            for row in tiles:
                for t in row:
                    if isinstance(t, dict):
                        if t.get("kind") == "PLANT":
                            np_ += 1
                        if t.get("animal") in ANIMALS:
                            na += 1
            plants[seat][day] = np_
            heads[seat][day] = na
        pmap = dict((obs[seat].market or {}).get("prices") or {})
        for item, q in sell_orders(r):
            sell[seat][day] += float(pmap.get(item, 0) or 0) * q
        for k in (r.get("farmer") or []):
            acts[seat][day][k] += 1
        for h in (r.get("hands") or []):
            for k in (h or []):
                acts[seat][day][k] += 1
    env.step(rets)

print("=== %s (US) vs %s seed %d ===" % (
    os.path.basename(ap), os.path.basename(op), seed))
print("rewards: US %d  OPP %d  gap %+d" % (
    round(env.state[0].reward), round(env.state[1].reward),
    round(env.state[0].reward - env.state[1].reward)))
print("\nday |  UScash  OPPcash    diff |  USsell  OPPsell    diff |"
      " USpl OPPpl | UShd OPPhd | UShd OPPhd")
for d in range(0, 30):
    c0, c1 = cash[0][d], cash[1][d]
    s0, s1 = sell[0][d], sell[1][d]
    h0, h1 = hands[0][d], hands[1][d]
    if not (c0 or c1):
        continue
    print("%3d | %7.0f %8.0f %8.0f | %6.0f %7.0f %8.0f |"
          " %4d %4d | %4d %4d | %4d %4d"
          % (d, c0, c1, c0 - c1, s0, s1, s0 - s1,
             plants[0][d], plants[1][d], heads[0][d], heads[1][d], h0, h1))

print("\n--- cumulative sell revenue by seat (where the gap opens) ---")
for d in range(0, 30):
    c0 = sum(sell[0][x] for x in sell[0] if x <= d)
    c1 = sum(sell[1][x] for x in sell[1] if x <= d)
    if c0 or c1:
        print("  through d%-2d  US %7.0f   OPP %7.0f   diff %+8.0f" % (d, c0, c1, c0 - c1))

print("\n--- act mix totals d0-13 vs d14-29 (US then OPP) ---")
for seat, nm in ((0, "US"), (1, "OPP")):
    for lo, hi, tag in ((0, 13, "d0-13"), (14, 29, "d14-29")):
        agg = defaultdict(int)
        for d in range(lo, hi + 1):
            for k, v in acts[seat][d].items():
                agg[k] += v
        tot = sum(agg.values()) or 1
        top = " ".join("%s=%d" % (k, v) for k, v in
                       sorted(agg.items(), key=lambda z: -z[1])[:8])
        print("  %-3s %-7s total=%-5d %s" % (nm, tag, tot, top))
