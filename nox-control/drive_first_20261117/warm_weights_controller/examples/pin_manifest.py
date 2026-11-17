"""Pin a real local file. This hashes bytes; it never downloads or loads a model."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--file',required=True);p.add_argument('--id',required=True);p.add_argument('--remote-path',required=True)
p.add_argument('--mode',choices=['WORK','TRAIN'],default='WORK');p.add_argument('--ram-load-bytes',required=True,type=int)
p.add_argument('--gpu-load-bytes',required=True,type=int);p.add_argument('--warm-bytes',type=int,default=0)
p.add_argument('--preload',action='store_true');p.add_argument('--out',required=True)
a=p.parse_args();f=Path(a.file);h=hashlib.sha256()
with f.open('rb') as source:
    for b in iter(lambda:source.read(1024*1024),b''):h.update(b)
g={'id':a.id,'remote_path':a.remote_path,'cache_path':f.name,'size_bytes':f.stat().st_size,'sha256':h.hexdigest(),
   'priority':1,'warm_bytes':a.warm_bytes,'ram_load_bytes':a.ram_load_bytes,'gpu_load_bytes':a.gpu_load_bytes,
   'tier':'GPU' if a.gpu_load_bytes else 'warmSSD','modes':[a.mode],'startup_preload':a.preload,
   'protected':True,'may_unload':False}
d={'schema':'NOX_WARM_MANIFEST_V1','source_policy':'DRIVE_FIRST','startup_storage':'ownedRAM','allow_ssd_cache':False,'groups':[g],'mode_groups':{'WORK':[],'TRAIN':[]},
   'budgets':{'chat_reserve_bytes':1073741824,'train_reserve_bytes':2147483648,'system_reserve_bytes':1073741824,
              'ssd_reserve_bytes':2147483648,'startup_transfer_bytes':0,'startup_warm_bytes':0,'startup_ram_bytes':0,'startup_max_groups':3}}
d['mode_groups'][a.mode]=[a.id]
Path(a.out).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'manifest':a.out,'sha256':g['sha256'],'bytes':g['size_bytes'],'startup_budgets_default_zero':True}))
