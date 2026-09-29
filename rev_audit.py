import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fast_kaggr_env import FastKaggrEnvPy as Env
from harness import load

def run(path, seed):
    """Revenue by item: sum money gained in steps where a SELL of that item filled.
    Engine _process_market sells min(order, shed_have) at current price."""
    ns = load(path, 'A')
    env = Env({'seed': seed, 'episodeSteps': 720}); env.reset(2)
    a = ns['agent']
    rev = {}; spend = {}
    prev_money = 3000.0
    while not env.done:
        o = env.state[0].observation
        farm = o.farms[0]
        r = a(o, None)
        sells = [m for m in (r.get('market') or []) if m and m[0]=='SELL']
        if sells:
            after = None
            env.step([r, {'farmer':['PASS'],'hands':[],'market':[]}])
            after = env.state[0].observation.farms[0]['money']
            delta = after - prev_money
            if delta > 0:
                # attribute to first sell item (engine fills in order)
                it = sells[0][1]
                rev[it] = rev.get(it,0) + delta
            prev_money = after
            continue
        # track buys
        for m in (r.get('market') or []):
            if m and m[0] in ('BUY_PRODUCT','BUY_SEED','BUY_ANIMAL','BUY_LAND','HIRE'):
                pass
        env.step([r, {'farmer':['PASS'],'hands':[],'market':[]}])
        now = env.state[0].observation.farms[0]['money']
        if now < prev_money:
            spend['total'] = spend.get('total',0) + (prev_money - now)
        prev_money = now
    return env.state[0].reward, rev, spend

if __name__ == '__main__':
    path = sys.argv[1]; seeds=[int(s) for s in (sys.argv[2:] or ['300001'])]
    for seed in seeds:
        r, rev, spend = run(path, seed)
        print('seed %d reward %.0f' % (seed, r))
        for k,v in sorted(rev.items(), key=lambda kv:-kv[1]):
            print('   %-12s $%9.0f' % (k, v))
        print('   TOTAL REV $%.0f  spend $%.0f' % (sum(rev.values()), spend.get('total',0)))
