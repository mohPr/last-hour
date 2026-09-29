"""Per-seat MELON autopsy: plants by day, harvest units, realized price by day.

The d10 melon dump is the whole early gap: pipe19 takes $15,216 of melon on d10
where we take $5,352 (h2h_who). This separates the three candidate causes --
too few melon plants, harvesting them on the wrong day, or harvesting them for
fewer units -- and shows the shared-pool price each seat actually received.

Usage: python3 tools/h2h_melon.py <our.py> <opp.py> [seed]
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fast_kaggr_env import FastKaggrEnvPy as Env   # noqa: E402
from harness import load                           # noqa: E402

ap, op = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 200001
nsA, nsO = load(ap, "newA"), load(op, "opp")
env = Env({"seed": seed, "episodeSteps": 720})
env.reset(2)
D = {"farmer": ["PASS"], "hands": [], "market": []}

# seat -> day -> metric
mplants = [defaultdict(int), defaultdict(int)]     # live melon plants
mplanted = [defaultdict(int), defaultdict(int)]    # PLANT acts on MELON
allplants = [defaultdict(int), defaultdict(int)]   # live plants, any crop
mseeds = [defaultdict(int), defaultdict(int)]      # melon seeds in drawer
hrv = [defaultdict(float), defaultdict(float)]     # melon $ harvested-ish
sellu = [defaultdict(float), defaultdict(float)]   # melon units SOLD
selld = [defaultdict(float), defaultdict(float)]   # melon $ SOLD
px = [defaultdict(float), defaultdict(float)]      # melon price that day
dig_m = [defaultdict(int), defaultdict(int)]       # DIG acts on a melon tile


def tiles_of(o, seat):
    try:
        f = o.farms[seat]
    except Exception:
        return []
    if not isinstance(f, dict):
        return []
    fq = f.get("farms", {}) if isinstance(f.get("farms", {}), dict) else {}
    return f.get("tiles", []) or fq.get("tiles", []) or []


def tgt_xy(tgt):
    if isinstance(tgt, (list, tuple)) and len(tgt) >= 2:
        return int(tgt[0]), int(tgt[1])
    if isinstance(tgt, dict):
        for k in ("x", "y", "pos", "tile"):
            if k in tgt:
                return tgt
    return None


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
        tl = tiles_of(obs[seat], seat)
        nm = na = 0
        for row in tl:
            for t in row:
                if isinstance(t, dict):
                    if t.get("kind") == "PLANT":
                        na += 1
                        if t.get("crop") == "MELON":
                            nm += 1
        mplants[seat][day] = nm
        allplants[seat][day] = na
        sd = obs[seat].seeds if hasattr(obs[seat], "seeds") else None
        if isinstance(sd, dict):
            mseeds[seat][day] = int(sd.get("MELON", 0) or 0)
        pm = dict((obs[seat].market or {}).get("prices") or {})
        if "MELON" in pm:
            px[seat][day] = float(pm["MELON"])
        for od in (r.get("market") or []):
            if od and str(od[0]) == "SELL" and len(od) >= 3 and od[1] == "MELON":
                q = float(od[2])
                sellu[seat][day] += q
                selld[seat][day] += q * float(pm.get("MELON", 0) or 0)
    env.step(rets)

print("=== MELON autopsy: %s (US) vs %s seed %d ===" % (
    os.path.basename(ap), os.path.basename(op), seed))
print("rewards: US %d  OPP %d  gap %+d" % (
    round(env.state[0].reward), round(env.state[1].reward),
    round(env.state[0].reward - env.state[1].reward)))

print("\nday | USmeln OPPmeln | USall OPPall | USpx  OPPpx |"
      " USunits OPPunits |     US$     OPP$   diff")
tu = ts = ou = os_ = 0.0
for d in range(0, 30):
    if not (mplants[0][d] or mplants[1][d] or sellu[0][d] or sellu[1][d]):
        continue
    tu += sellu[0][d]; ts += selld[0][d]
    ou += sellu[1][d]; os_ += selld[1][d]
    print("%3d | %6d %7d | %5d %6d | %5.0f %6.0f | %7.0f %8.0f |"
          " %8.0f %8.0f %8.0f"
          % (d, mplants[0][d], mplants[1][d], allplants[0][d], allplants[1][d],
             px[0][d], px[1][d], sellu[0][d], sellu[1][d],
             selld[0][d], selld[1][d], selld[0][d] - selld[1][d]))
print("\nTOTAL melon sold:  US %.0f units / $%.0f   OPP %.0f units / $%.0f"
      % (tu, ts, ou, os_))
print("d10 melon alone:   US %.0f units / $%.0f   OPP %.0f units / $%.0f"
      % (sellu[0][10], selld[0][10], sellu[1][10], selld[1][10]))
print("\nUS  melon seeds in drawer by day:",
      {d: mseeds[0][d] for d in sorted(mseeds[0]) if d <= 20})
print("OPP melon seeds in drawer by day:",
      {d: mseeds[1][d] for d in sorted(mseeds[1]) if d <= 20})
