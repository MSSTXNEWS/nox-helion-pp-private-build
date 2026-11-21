#!/bin/bash
# Шарды 2-9 в shm оказались битыми (дубль-докачка, размеры > ожидаемых). Удалить, скачать заново по одному потоку на файл (P4), сверить sha256 с HF (lfs.oid).
exec 9>/root/nox/logs/redo.lock; flock -n 9 || { echo running; tail -c 400 /root/nox/logs/redo.log; exit 0; }
pkill -f scripts_glm_dl_worker; pkill -f "glm-5.3-gguf" ; sleep 1
cat > /root/nox/redo_worker.py <<'W'
import json,urllib.request,subprocess,os,hashlib,sys
from concurrent.futures import ThreadPoolExecutor
API="https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/main/UD-Q4_K_XL"
B="https://huggingface.co/unsloth/GLM-5.3-GGUF/resolve/main/"
meta={os.path.basename(f['path']):f for f in json.load(urllib.request.urlopen(API))}
def place(n):
    i=int(n.split('-')[-3]); return ('/dev/shm/nox_glm' if i<=9 else '/root/nox/glm53_disk')
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        while True:
            b=f.read(8<<20)
            if not b:break
            h.update(b)
    return h.hexdigest()
def one(n):
    m=meta[n]; sz=m['size']; oid=(m.get('lfs') or {}).get('oid'); d=place(n); os.makedirs(d,exist_ok=True); p=d+'/'+n
    os.makedirs('/root/nox/glm53',exist_ok=True)
    if os.path.lexists('/root/nox/glm53/'+n): os.remove('/root/nox/glm53/'+n)
    os.symlink(p,'/root/nox/glm53/'+n)
    if os.path.exists(p) and os.path.getsize(p)!=sz: os.remove(p)
    for t in range(6):
        if os.path.exists(p) and os.path.getsize(p)==sz: break
        subprocess.run(['curl','-fsSL','-C','-','--retry','5','-o',p,B+'UD-Q4_K_XL/'+n])
    ok=os.path.exists(p) and os.path.getsize(p)==sz
    if ok and oid: ok = sha(p)==oid
    print(n,sz,'OK' if ok else 'BAD',flush=True); return ok
names=sorted(meta)
# битые шарды 2..9 в shm: удалить сразу
for n in names:
    i=int(n.split('-')[-3]); p=place(n)+'/'+n
    if i in range(2,10) and os.path.exists(p) and os.path.getsize(p)!=meta[n]['size']: os.remove(p); print('removed bad',n,flush=True)
with ThreadPoolExecutor(4) as ex: r=list(ex.map(one,names))
print('ALL_OK' if all(r) else 'SOME_BAD',r,flush=True)
W
nohup setsid bash -c 'exec 9>&-; python3 /root/nox/redo_worker.py' > /root/nox/logs/redo.log 2>&1 < /dev/null &
sleep 30; cat /root/nox/logs/redo.log; df -h /dev/shm | tail -1; pgrep -c curl
