"""Per-seat HERD + STRAWBERRY census. Target: the milk (-16,534) and strawberry
(-19,115) H2H holes, which are pure VOLUME (identical prices, they just sell
more units). DSM's reference herd is C9 S15 = 24 head, no geese; ours has never
been measured against a live opponent.

Under the corrected objective (my cash - opp cash) extra supply is good: our
units displace theirs and the shared price falls for both, so we win the margin
by selling MORE. So the question is not "is our herd efficient" but "how many
cow/strawberry units can we actually get into the pool".

Usage: python3 tools/h2h_herd.py <our.py> <opp.py> [seed]
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

herd = [{a: defaultdict(int) for a in ANIMALS}, {a: defaultdict(int) for a in ANIMALS}]
cropy = [{"STRAWBERRY": defaultdict(int), "WHEAT": defaultdict(int),
          "MELON": defaultdict(int), "TOTAL": defaultdict(int)} for _ in (0, 1)]
feed = [defaultdict(int), defaultdict(int)]
milk_ord = [defaultdict(int), defaultdict(int)]
acts = [defaultdict(int), defaultdict(int)]


def tiles_of(o, seat):
    try:
        f = o.farms[seat]
    except Exception:
        return []
    if not isinstance(f, dict):
        return []
    fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
    return f.get("tiles", []) or fq.get("tiles", []) or []


while not env.done:
    o0, o1 = env.state[0].observation, env.state[1].observation
    day = int(o0.day)
    hour = int(o0.hour)
    obs = (o0, o1)
    rets = []
    for seat in (0, 1):
        ns = nsA if seat == 0 else nsO
        try:
            r = ns["agent"](obs[seat], None)
        except Exception:
            r = dict(D)
        rets.append(r)
        # snapshot the board ONCE per day (hour 0). Counting every step
        # multiplies every tile by ~24 and reports 288 cows on a 100-tile grid.
        if hour == 0:
            for row in tiles_of(obs[seat], seat):
                for t in row:
                    if not isinstance(t, dict):
                        continue
                    a = t.get("animal")
                    if a in ANIMALS:
                        herd[seat][a][day] += 1
                    elif t.get("kind") == "PLANT":
                        cropy[seat]["TOTAL"][day] += 1
                        c = t.get("crop")
                        if c in cropy[seat]:
                            cropy[seat][c][day] += 1
        for k in (r.get("farmer") or []):
            acts[seat][k] += 1
            if k == "FEED":
                feed[seat][day] += 1
        for h in (r.get("hands") or []):
            for k in (h or []):
                acts[seat][k] += 1
                if k == "FEED":
                    feed[seat][day] += 1
        for od in (r.get("market") or []):
            if od and str(od[0]) == "SELL" and len(od) >= 2 and od[1] == "MILK":
                milk_ord[seat][day] += 1
    env.step(rets)

print("=== HERD + CROP census: %s (US) vs %s seed %d ===" % (
    os.path.basename(ap), os.path.basename(op), seed))
print("rewards: US %d  OPP %d  gap %+d" % (
    round(env.state[0].reward), round(env.state[1].reward),
    round(env.state[0].reward - env.state[1].reward)))

print("\nday |  UScow USshep USgoos  UStot | OPPcow OPPshep OPPgoos OPPtot |"
      "  diff  | USstb OPPstb | USmlk OPPmlk")
for d in range(0, 30):
    u = [herd[0][a][d] for a in ANIMALS]
    o = [herd[1][a][d] for a in ANIMALS]
    if not (sum(u) or sum(o) or cropy[0]["STRAWBERRY"][d] or cropy[1]["STRAWBERRY"][d]):
        continue
    print("%3d | %6d %7d %7d %6d | %6d %7d %7d %6d | %+6d | %5d %6d | %5d %6d"
          % (d, u[0], u[1], u[2], sum(u), o[0], o[1], o[2], sum(o),
             sum(u) - sum(o),
             cropy[0]["STRAWBERRY"][d], cropy[1]["STRAWBERRY"][d],
             milk_ord[0][d], milk_ord[1][d]))

print("\n--- peak / total ---")
for seat, nm in ((0, "US "), (1, "OPP")):
    pk = {a: max(herd[seat][a].values()) if herd[seat][a] else 0 for a in ANIMALS}
    print("  %s peak head: C%-3d S%-3d G%-3d  total %-3d | peak plants %-3d"
          " | peak strawberry %-3d | MILK sell-orders %d"
          % (nm, pk["COW"], pk["SHEEP"], pk["GOOSE"], sum(pk.values()),
             max(cropy[seat]["TOTAL"].values()) if cropy[seat]["TOTAL"] else 0,
             max(cropy[seat]["STRAWBERRY"].values()) if cropy[seat]["STRAWBERRY"] else 0,
             sum(milk_ord[seat].values())))
print("\n--- act totals (whole game) ---")
keys = sorted(set(acts[0]) | set(acts[1]), key=lambda k: -(acts[0][k] + acts[1][k]))
for k in keys[:12]:
    if acts[0][k] or acts[1][k]:
        print("  %-20s US %6d  OPP %6d" % (k, acts[0][k], acts[1][k]))
mov = sum(acts[s][k] for s in (0, 1) for k in
          ("WEST", "EAST", "NORTH", "SOUTH"))
work = sum(acts[s][k] for s in (0, 1) for k in acts[s] if k not in
           ("WEST", "EAST", "NORTH", "SOUTH"))
print("  MOVEMENT share:  US %.1f%%   OPP %.1f%%   (DSM/Boey reference 42-45%%)"
      % (100.0 * sum(acts[0][k] for k in ("WEST", "EAST", "NORTH", "SOUTH")) / max(1, sum(acts[0].values())),
         100.0 * sum(acts[1][k] for k in ("WEST", "EAST", "NORTH", "SOUTH")) / max(1, sum(acts[1].values()))))
