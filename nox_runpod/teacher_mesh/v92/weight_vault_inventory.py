"""NOX E2 V92 — locate full-weight HF student/model/optimizer across EXISTING Vast.

One read-only native pass through V51, no data export, training, GPU allocations
or new services. Scans files' metadata only, emits anonymized parent SHA IDs.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
_prev=connection.api
def settle(method,path,key,data=None):
    result=_prev(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(13)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,json,hashlib,collections,subprocess
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V92_SCHEMA=NOX_E2_FULL_TREE_TRAINABLE_WEIGHT_VAULT_V1')
ROOT=Path('/root/nox')
skip={'.git','.cache','node_modules','__pycache__','venv','.venv','site-packages','conda','tmp','logs','.ssh','dist','build'}
groups={}
counts=collections.Counter()
visited=0
for parent,dirs,files in os.walk(ROOT,followlinks=False):
    dirs[:]=[s for s in dirs if s not in skip and not (Path(parent)/s).is_symlink()][:125]
    visited+=1
    if visited>17000:
        print('NATIVE_V92_SCAN_LIMIT=HOLD_TRUNCATED');break
    for n in files:
        if not (n.endswith(('.safetensors','.gguf','.bin','.pt','.pth','.ckpt','.json','.model'))
                or any(x in n.lower() for x in ('optimizer','tokenizer','trainer_state'))):
            continue
        try:
            p=Path(parent)/n
            s=p.lstat()
            if not stat.S_ISREG(s.st_mode) or s.st_size>70_000_000_000:continue
            g=groups.setdefault(str(p.parent),{'weights':0,'weight_bytes':0,'gguf_bytes':0,
                'gguf':0,'optimizers':0,'optimizer_bytes':0,'config':False,'tokenizer':False,
                'index':False,'trainer_state':False,'checkpoint_name':False})
            low=n.lower()
            if n.endswith('.safetensors') and s.st_size>1_000_000:
                g['weights']+=1;g['weight_bytes']+=s.st_size;counts['safetensors']+=1
            elif n.endswith('.gguf') and s.st_size>1_000_000:
                g['gguf']+=1;g['gguf_bytes']+=s.st_size;counts['gguf']+=1
            if 'optimizer' in low or 'optim_state' in low or 'optim.' in low:
                g['optimizers']+=1;g['optimizer_bytes']+=s.st_size
            if n=='config.json':g['config']=True
            if ('tokenizer' in low or n in ('vocab.json','merges.txt','vocab.model')):g['tokenizer']=True
            if 'index.json' in low:g['index']=True
            if n=='trainer_state.json':g['trainer_state']=True
            if 'checkpoint' in low:g['checkpoint_name']=True
        except OSError:continue

def safe_model_type(folder):
    config=Path(folder)/'config.json'
    if not config.is_file() or config.is_symlink() or config.stat().st_size>500000:return None
    try:
        d=json.loads(config.read_text(encoding='utf8'))
        typ=d.get('model_type')
        return typ[:45] if isinstance(typ,str) and typ.replace('_','').replace('-','').isalnum() else None
    except (ValueError,OSError):return None
ranked=sorted(((k,v) for k,v in groups.items() if v['weights'] or v['optimizers'] or v['gguf']),
              key=lambda x:x[1]['weight_bytes']+x[1]['optimizer_bytes']+x[1]['gguf_bytes'],reverse=True)
totw=sum(v['weight_bytes'] for _,v in ranked)
print('NATIVE_V92_TOTAL='+json.dumps({'dirs_scanned':visited,'groups':len(ranked),
   'weight_files':counts['safetensors'],'weights_gib':round(totw/2**30,3),
   'gguf_files':counts['gguf'],'optimizer_files':sum(v['optimizers'] for _,v in ranked),
   'full_sha_verified':False,'no_files_changed':True},separators=(',',':')))
for root,v in ranked[:65]:
    hint=hashlib.sha256(root.encode('utf8')).hexdigest()[:16]
    info={'group_sha16':hint,'weight_files':v['weights'],
        'weight_gib':round(v['weight_bytes']/2**30,3),
        'gguf_files':v['gguf'],'gguf_gib':round(v['gguf_bytes']/2**30,3),
        'optimizer_files':v['optimizers'],'optimizer_mib':round(v['optimizer_bytes']/2**20,2),
        'config':v['config'],'model_type':safe_model_type(root),
        'tokenizer':v['tokenizer'],'index':v['index'],
        'trainer_state':v['trainer_state'],'checkpoint_name':v['checkpoint_name']}
    print('NATIVE_V92_GROUP='+json.dumps(info,sort_keys=True,separators=(',',':')))
try:
    p=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.free,memory.used,utilization.gpu',
            '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if p.returncode==0:
        print('NATIVE_V92_GPU='+json.dumps([s.strip() for s in p.stdout.splitlines()[:2]],separators=(',',':')))
except Exception:print('NATIVE_V92_GPU=HOLD')
print('NATIVE_V92_TRAINABLE_STUDENT_ASSEMBLED_NOT_YET_VERIFIED=true')
print('NATIVE_V92_NO_READ_OF_PRIVATE_TENSOR_OR_S03_ROWS=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main()->int:
    connection.REMOTE=REMOTE;connection.api=settle
    buf=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buf):ok=connection.probe()
    except Exception as e:
        msg=str(e)
        print("NOX_V92_HOLD="+(msg if msg.startswith('HOLD_') and len(msg)<90 else 'SSH_OR_RUNTIME'))
    finally:
        try:
            with contextlib.redirect_stdout(buf):
                if not connection.cleanup():ok=False
        except Exception:ok=False
    lines=buf.getvalue().splitlines()
    for s in lines:
        if s.startswith(('NATIVE_V92_','TEMP_SSH_CLEANUP=')) and len(s)<790:
            print(s)
    matched=any(l.startswith('NATIVE_V92_TOTAL=') for l in lines)
    print('NOX_V92_INVENTORY_VERIFIED='+str(bool(ok and matched)).lower())
    return 0 if ok and matched else 2
if __name__=='__main__':
    raise SystemExit(main())
