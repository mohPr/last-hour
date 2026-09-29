import sys, os
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
from fast_kaggr_env import FastKaggrEnvPy as Env
from harness import load
ap, op = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv)>3 else 200001
nsA, nsO = load(ap,'newA'), load(op,'opp')
env=Env({'seed':seed,'episodeSteps':720}); env.reset(2)
for step in range(720):
    o0=env.state[0].observation; o1=env.state[1].observation
    day=int(getattr(o0,'day',0))
    if o0.step%24==0 and day<=12:
        for seat,o in ((0,o0),(1,o1)):
            f=o.farms[seat]
            try: shedW=o.private['shed'].get('WHEAT',0); seeds=dict(o.private['seeds'])
            except Exception: shedW='?'; seeds='?'
            print(f"step={o.step} d{day} seat{seat} money={round(f['money'])} hands={len(f['hands'])} hires_today={f.get('hires_today')} shedW={shedW} seeds={seeds}")
    try: r0=nsA['agent'](o0,None)
    except Exception as e: r0={'farmer':['PASS'],'hands':[],'market':[]}
    try: r1=nsO['agent'](o1,None)
    except Exception as e: r1={'farmer':['PASS'],'hands':[],'market':[]}
    if o0.step<260:
        # log market orders d0-d10
        if r0.get('market'): print(f"  step={o0.step} US market={r0['market']}")
        if r1.get('market'): print(f"  step={o0.step} OPP market={r1['market']}")
    env.step([r0,r1])
    if env.done: break
print('rewards',env.state[0].reward,env.state[1].reward)
