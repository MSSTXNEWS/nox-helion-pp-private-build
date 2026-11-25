# QA_FAST=1: 1 vision-прогон, только 1440, max_tokens<=600; по умолчанию выключен
import re,sys,shutil,time
q='/workspace/nox/qa_audit.py'; s=open(q,encoding='utf-8').read()
if 'QA_FAST' in s: print('ALREADY'); sys.exit()
shutil.copy(q,q+'.bak_ux_fast_%d'%time.time())
n=0
def rep(a,b):
    global s,n
    if a in s: s=s.replace(a,b,1); n+=1
    else: print('MISS',a[:50])
rep('def vision(jpg, prompt):','FAST = os.environ.get("QA_FAST") == "1"\n\ndef vision(jpg, prompt):')
rep('"max_tokens": 1000,','"max_tokens": (600 if FAST else 1000),')
rep('for vp, (w, h) in {"desk": (1440, 900), "mob": (390, 844)}.items():','for vp, (w, h) in ({"desk": (1440, 900)} if FAST else {"desk": (1440, 900), "mob": (390, 844)}).items():')
rep('    for vp in ("desk", "mob"): open(f"{OUT}/audit_{vp}_{key}.jpg", "wb").write(shots[vp])','    shots.setdefault("mob", shots["desk"])\n    for vp in ("desk", "mob"): open(f"{OUT}/audit_{vp}_{key}.jpg", "wb").write(shots[vp])')
rep('    for _ in range(2):\n        try: runs.append(_parse(vision(','    for _ in range(0 if FAST else 2):\n        try: runs.append(_parse(vision(')
open(q,'w',encoding='utf-8').write(s); print('PATCHED',n)
