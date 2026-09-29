import sys, os
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
from harness import load, play
agent=sys.argv[1] if len(sys.argv)>1 else HERE+'/base_dsm348.py'
seeds=[200001,200002]
OPPS={
 'opp_pipe19': HERE+'/opps/opp_pipe19.py',
 'opp_pipe18': HERE+'/opps/opp_pipe18.py',
 'opp_kagg': HERE+'/opps/opp_kagg.py',
 'opp_v57': HERE+'/opps/opp_v57.py',
 'base_v76': HERE+'/opps/base_v76.py',
 'main': HERE+'/opps/main.py',
 'main1': HERE+'/opps/main1.py',
 'main_copy_1': HERE+'/opps/main_copy_1.py',
}
total=0; wins=0; n=0
for oname,opath in OPPS.items():
    for seed in seeds:
        nsA=load(agent,'newA'); nsO=load(opath,'opp')
        r,_,_,_=play(nsA,nsO,seed); m=r[0]-r[1]
        total+=m; n+=1; wins+=1 if m>0 else 0
        print(f'{oname} seed={seed} rewards={[round(x) for x in r]} margin={m:+.0f}',flush=True)
print(f'TOTAL={total:+.0f} over {n} games WINS={wins}/{n} AVG={total/n:+.0f}')
