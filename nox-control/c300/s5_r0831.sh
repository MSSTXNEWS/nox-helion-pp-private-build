python3 - <<'P'
import json,re,os
Q="/workspace/nox/web/site/qa/"
a=json.load(open(Q+"audit.json"))
log=open("/tmp/s5_chain4.log",errors="ignore").read()
done=re.findall(r"DONE (\w+) (\d\d:\d\d)",log)
print("OUT: done",done,"CHAIN_DONE" if "CHAIN_DONE" in log else "running")
for k,t in done:
    v=a.get(k,{}); print("OUT:",k,t,v.get('status'),v.get('wow'),v.get('ARU'),v.get('vision_runs'),'vend',len(v.get('vendor_used') or []),[ (f['item'][:26],str(f['detail'])[:60]) for f in v.get('fails',[])][:6])
print("OUT: fixed",[os.path.basename(f)[:-6] for f in __import__('glob').glob(Q+'rework/*.fixed')])
P
date +%H:%M
