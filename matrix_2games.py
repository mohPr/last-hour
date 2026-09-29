import sys, os, time
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
from harness import load, play
AGENT=HERE+'/base_dsm348.py'
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
seed=int(sys.argv[1]) if len(sys.argv)>1 else 200001
total=0; rows=[]
for oname,opath in OPPS.items():
    for seat in (0,1):
        nsA=load(AGENT,'newA'); nsO=load(opath,'opp')
        t0=time.time()
        if seat==0:
            r,_,_,_=play(nsA,nsO,seed); margin=r[0]-r[1]
        else:
            r,_,_,_=play(nsO,nsA,seed); margin=r[1]-r[0]
        dt=time.time()-t0
        total+=margin
        rows.append((oname,seat,r,margin))
        print(f'{oname} seed={seed} seat={seat} rewards={[round(x) for x in r]} margin={margin:+.0f} ({dt:.1f}s)',flush=True)
print(f'TOTAL={total:+.0f} over {len(rows)} games')
wins=sum(1 for _,_,_,m in rows if m>0)
print(f'WINS={wins}/{len(rows)}')
