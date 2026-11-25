import json,sys,shutil,os
p='/workspace/nox/web/pkg/server/svc_registry.json'
if not os.path.exists(p+'.bak_d_1'): shutil.copy(p,p+'.bak_d_1')
n,port,mode,title,note=sys.argv[1:6]
d=json.load(open(p)); d[n]={'port':int(port),'mode':mode,'title':title,'note':note}
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2); print('registered',n,port,mode)
