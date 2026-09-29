# Portable runner: matrix vs opponents + production-parity gates + telemetry.
# No absolute paths, no extra deps beyond kaggle-environments (see RUN.md).
# Usage:
#   python3 harness.py <agent_path>              -> matrix, seeds 200001-200002, all opps
#   python3 harness.py <agent_path> trace        -> matrix + money trace
#   python3 harness.py <agent_path> parity       -> parity gates vs PASS, seeds 0,1,2
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from fast_kaggr_env import FastKaggrEnvPy as Env

OPPS = {'pipe19': HERE + '/opp_pipe19.py', 'pipe18': HERE + '/opp_pipe18.py',
        'kagg': HERE + '/opp_kagg.py', 'v57': HERE + '/opp_v57.py'}
SEEDS = [200001, 200002]


def load(path, tag):
    ns = {'__name__': tag}
    exec(compile(open(path).read(), tag, 'exec'), ns)
    return ns


def play(ns0, ns1, seed, trace_money=False):
    a0, a1 = ns0['agent'], ns1['agent']
    env = Env({'seed': seed, 'episodeSteps': 720})
    env.reset(2)
    money = []
    while not env.done:
        o0, o1 = env.state[0].observation, env.state[1].observation
        try:
            r0 = a0(o0, None)
        except Exception:
            r0 = {'farmer': ['PASS'], 'hands': [], 'market': []}
        try:
            r1 = a1(o1, None)
        except Exception:
            r1 = {'farmer': ['PASS'], 'hands': [], 'market': []}
        env.step([r0, r1])
        if trace_money and o0.step % 48 == 0:
            money.append((o0.step, round(env.state[0].observation.farms[0]['money']),
                          round(env.state[1].observation.farms[1]['money'])))
    rep0 = rep1 = None
    for f in ('REPORT',):
        if f in ns0:
            try:
                rep0 = ns0[f]()
            except Exception:
                pass
        if f in ns1:
            try:
                rep1 = ns1[f]()
            except Exception:
                pass
    return [env.state[0].reward, env.state[1].reward], money, rep0, rep1


def matrix(agent_path, seeds=None, opps=None, seats=(0, 1), trace=False):
    seeds = seeds or SEEDS
    opps = opps or OPPS
    total = 0
    rows = []
    for oname, opath in opps.items():
        for seed in seeds:
            for seat in seats:
                nsA = load(agent_path, 'newA')
                nsO = load(opath, 'opp')
                if seat == 0:
                    (r, money, repA, _) = play(nsA, nsO, seed, trace_money=trace)
                    margin = r[0] - r[1]
                else:
                    (r, money, _, repA) = play(nsO, nsA, seed, trace_money=trace)
                    margin = r[1] - r[0]
                total += margin
                rows.append((oname, seed, seat, r, margin))
                print('%s seed=%d seat=%d rewards=%s margin=%+.0f' % (oname, seed, seat, [round(x) for x in r], margin), flush=True)
                if trace and money:
                    print('   money trace:', money, flush=True)
    print('TOTAL=%+.0f over %d games' % (total, len(rows)), flush=True)
    try:
        print('telemetry:', repA, flush=True)
    except Exception:
        pass
    return total, rows


def _snap(obs, seat):
    """Production snapshot of one farm from raw obs (dict or object)."""
    g = (lambda k, d=None: obs.get(k, d)) if isinstance(obs, dict) else (lambda k, d=None: getattr(obs, k, d))
    farms = g('farms', [])
    farm = farms[seat]
    fg = (lambda k, d=None: farm.get(k, d)) if isinstance(farm, dict) else (lambda k, d=None: getattr(farm, k, d))
    tiles = fg('tiles', []) or []
    herd = {'COW': 0, 'SHEEP': 0, 'GOOSE': 0}
    standing = {}
    ybank = {}
    weeds = 0
    for row in tiles:
        for t in row:
            if isinstance(t, dict):
                if 'animal' in t and t.get('animal') in herd:
                    herd[t['animal']] += 1
                elif t.get('kind') == 'PLANT':
                    standing[t.get('crop')] = standing.get(t.get('crop'), 0) + 1
                    ybank[t.get('crop')] = ybank.get(t.get('crop'), 0) + int(t.get('yield_units', 0) or 0)
                elif t.get('kind') == 'WEED':
                    weeds += 1
    try:
        quads = len(list(fg('unlocked_quadrants', []) or []))
    except Exception:
        quads = 0
    try:
        hires_today = int(fg('hires_today', 0))
    except Exception:
        hires_today = 0
    return {'day': int(g('day', 0)), 'money': round(float(fg('money', 0))),
            'herd': herd, 'herd_n': sum(herd.values()),
            'standing': standing, 'plants_n': sum(standing.values()),
            'ybank': ybank, 'weeds': weeds,
            'quads': quads, 'hands': len(fg('hands', []) or []),
            'hires_today': hires_today}


def parity(agent_path, seeds=None, seat=0, opp_path=None):
    """Production-parity check vs SPEC bands. Prints per-day table + gates."""
    seeds = seeds or [0, 1, 2]
    for seed in seeds:
        nsA = load(agent_path, 'newA')
        nsO = load(opp_path, 'opp') if opp_path else {'agent': lambda o, c: {'farmer': ['PASS'], 'hands': [], 'market': []}}
        aA, aO = nsA['agent'], nsO['agent']
        env = Env({'seed': seed, 'episodeSteps': 720})
        env.reset(2)
        daily = {}
        while not env.done:
            oA = env.state[seat].observation
            oB = env.state[1 - seat].observation
            day = int(oA.get('day', 0) if isinstance(oA, dict) else getattr(oA, 'day', 0))
            # last snapshot WITHIN the day (hands intact; day-rollover resets to [])
            daily[day] = _snap(oA, seat)
            try:
                rA = aA(oA, None)
            except Exception:
                rA = {'farmer': ['PASS'], 'hands': [], 'market': []}
            try:
                rB = aO(oB, None)
            except Exception:
                rB = {'farmer': ['PASS'], 'hands': [], 'market': []}
            if seat == 0:
                env.step([rA, rB])
            else:
                env.step([rB, rA])
        print('== parity seed=%d seat=%d rewards=%s' % (seed, seat, [round(x) for x in (env.state[0].reward, env.state[1].reward)]))
        for d in sorted(daily):
            if d in (0, 1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 15, 27, 28, 29):
                s = daily[d]
                print('  d%2d $%6d herd=%s(%d) plants=%s(%d) ybank=%s weeds=%d quads=%d hands=%d hired=%d' % (
                    d, s['money'], s['herd'], s['herd_n'], s['standing'], s['plants_n'], s['ybank'], s['weeds'], s['quads'], s['hands'], s['hires_today']))
        g = []
        if 5 in daily:
            g.append(('d5 money 634-901', 634 <= daily[5]['money'] <= 901))
            g.append(('d5 herd 2C+3S', daily[5]['herd'].get('COW') == 2 and daily[5]['herd'].get('SHEEP') == 3))
        if 0 in daily:
            g.append(('d0 plants>=15', daily[0]['plants_n'] >= 15))
        if 6 in daily:
            g.append(('d6 quads>=1 (1st LAND)', daily[6]['quads'] >= 1))
            g.append(('d6 herd>=7', daily[6]['herd_n'] >= 7))
        if 10 in daily:
            g.append(('d10 money>=2500 (melon spike)', daily[10]['money'] >= 2500))
        if 12 in daily:
            g.append(('d12 money>=8000', daily[12]['money'] >= 8000))
        if 15 in daily:
            g.append(('d15 money>=20000', daily[15]['money'] >= 20000))
        for name, ok in g:
            print('  [%s] %s' % ('PASS' if ok else 'FAIL', name))
    return True


if __name__ == '__main__':
    ap = sys.argv[1] if len(sys.argv) > 1 else HERE + '/agent_current.py'
    if len(sys.argv) > 2 and sys.argv[2] == 'parity':
        opp = sys.argv[3] if len(sys.argv) > 3 else None
        parity(ap, opp_path=opp)
    else:
        trace = len(sys.argv) > 2 and sys.argv[2] == 'trace'
        matrix(ap, trace=trace)
