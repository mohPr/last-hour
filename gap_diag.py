import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fast_kaggr_env import FastKaggrEnvPy as Env
from harness import load

DSM_MONEY = {0:3000,6:740,10:599,12:12668,15:23460,20:53846,25:76996,29:95614}
DSM_W = {6:0,9:7,10:17,12:26,15:24,20:23,25:30,29:11}
DSM_HERD = {6:(4,3,0),10:(7,4,3),12:(7,5,5),15:(7,6,5),20:(7,6,5),25:(6,6,5),29:(6,1,4)}

def run(path, seed, tag):
    ns = load(path, tag)
    env = Env({'seed': seed, 'episodeSteps': 720}); env.reset(2)
    dummy = {'agent': lambda o,c:{'farmer':['PASS'],'hands':[],'market':[]}}
    a = ns['agent']
    days = {}
    prev_head = 0; escapes = 0
    verbs = {}
    last_day = -1
    weeds_prev = None; digs_since = 0; deaths = []
    while not env.done:
        o = env.state[0].observation
        day = int(getattr(o,'day',0)); hour = int(getattr(o,'hour',0))
        farms = o.farms; farm = farms[0]
        tiles = farm['tiles']
        herd = {'COW':0,'SHEEP':0,'GOOSE':0}; standing={}; weeds_now = 0
        for row in tiles:
            for t in row:
                if isinstance(t,dict):
                    if t.get('animal') in herd: herd[t['animal']]+=1
                    elif t.get('kind')=='PLANT': standing[t.get('crop')]=standing.get(t.get('crop'),0)+1
                    elif t.get('kind')=='WEED': weeds_now += 1
        head = sum(herd.values())
        if day != last_day:
            if last_day >= 0:
                if head < prev_head: escapes += prev_head - head
                if weeds_prev is not None:
                    deaths.append(weeds_now - weeds_prev + digs_since)
            last_day = day; digs_since = 0
        prev_head = head
        if hour == 0:
            days[day] = {'money': round(farm['money']), 'herd': dict(herd),
                         'W': standing.get('WHEAT',0), 'stands': standing,
                         'hands': len(farm['hands'])}
            weeds_prev = weeds_now
        r = a(o, None)
        for k in r.get('farmer',[]):
            verbs[k] = verbs.get(k,0)+1
            if k == 'DIG': digs_since += 1
        for h in r.get('hands',[]):
            for k in h:
                verbs[k]=verbs.get(k,0)+1
                if k == 'DIG': digs_since += 1
        env.step([r, {'farmer':['PASS'],'hands':[],'market':[]}])
    rep = ns['REPORT']() if 'REPORT' in ns else {}
    return env.state[0].reward, days, escapes, verbs, rep, deaths

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv)>1 else 'my_dsm341.py'
    seeds = [int(s) for s in (sys.argv[2:] or ['300001'])]
    tot = 0
    for seed in seeds:
        r, days, esc, verbs, rep, deaths = run(path, seed, 'A%d'%seed)
        tot += r
        print('=== seed %d reward %.0f escapes=%d deaths_total=%d' % (seed, r, esc, sum(deaths)))
        print('   deaths by day:', dict(list(enumerate(deaths))[1:]))
        print('  day  $    | ours W / DSM W | herd C/S/G / DSM | hands')
        for d in sorted(days):
            if d in (0,1,2,3,4,5,6,9,10,11,12,15,18,20,23,25,27,28,29):
                dd = days[d]
                dh = DSM_HERD.get(d, ())
                print('  d%2d $%7d | W%2d / %-2s | %d/%d/%d / %s | %d' % (
                    d, dd['money'], dd['W'], DSM_W.get(d,'-'),
                    dd['herd']['COW'], dd['herd']['SHEEP'], dd['herd']['GOOSE'],
                    '/'.join(map(str,dh)) if dh else '-', dd['hands']))
        print('  verbs:', {k:v for k,v in sorted(verbs.items(), key=lambda kv:-kv[1])})
        et = rep.get('exec_tasks', {})
        print('  stig:', {k[5:]:v for k,v in sorted(et.items(), key=lambda kv:-kv[1]) if k.startswith('stig_')})
    print('MEAN %.0f' % (tot/len(seeds)))
