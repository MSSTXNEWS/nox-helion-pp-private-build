import sys,shutil,time,py_compile
F="/workspace/nox/distill_v2/code/distill_v2.py"; s=open(F,encoding="utf-8").read()
if "MOE_BACKEND_P3" in s: print("already"); sys.exit(0)
shutil.copy(F,F+".bak_moebe_%d"%int(time.time()))
a="import urllib.request\n"; assert s.count(a)==1
b=a+'''try:  # MOE_BACKEND_P3: A/B бэкенда MoE Unsloth через state/speed.json moe_backend (до импорта unsloth). Откат: убрать ключ.
    _mb = json.load(open("/workspace/nox/state/speed.json")).get("moe_backend")
    if _mb in ("grouped_mm", "unsloth_triton", "native_torch"): os.environ["UNSLOTH_MOE_BACKEND"] = _mb
except Exception: pass
'''
s=s.replace(a,b,1); open(F,"w",encoding="utf-8").write(s); py_compile.compile(F,doraise=True); print("patched")
