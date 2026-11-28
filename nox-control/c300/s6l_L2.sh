echo "K1: s6l_L2"
N=/workspace/nox; C=$N/canon/canon.py; B=$N/state/s6/backup; mkdir -p $B
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s6l_files
curl -fsSL --retry 3 $RAW/life_time.py -o $N/mods/life_time.py
[ -f $B/canon.py.pre_L2 ] || cp $C $B/canon.py.pre_L2
grep -q "life_time" $C && { echo "already patched"; echo END; exit 0; }
python3 - <<PY
p="$C"; s=open(p,encoding="utf-8").read()
s=s.replace("def morning():\n","def _morning_old():\n",1).replace("def evening():\n","def _evening_old():\n",1)
shim='''
def _lt():
    import sys
    if "/workspace/nox/mods" not in sys.path: sys.path.insert(0, "/workspace/nox/mods")
    import life_time; return life_time
def morning():
    try:
        lt = _lt()
        if lt.off(lt.N, "life_time.off"): raise RuntimeError("off")
        try: lt.update_registry()
        except Exception: pass
        L = lt.morning_lines()
        o = {"ts": now().isoformat(), "kind": "morning", "lines": L[:5], "src": "life_time"}; jw(M + "/morning_brief_v5.json", o); return o
    except Exception: return _morning_old()
def evening():
    try:
        lt = _lt()
        if lt.off(lt.N, "life_time.off"): raise RuntimeError("off")
        L = lt.evening_lines()
        o = {"ts": now().isoformat(), "kind": "evening", "lines": L, "src": "life_time"}; jw(M + "/evening_brief_v5.json", o); return o
    except Exception: return _evening_old()
def life_tick():
    try: _lt().tick()
    except Exception: pass
'''
i=s.index("# ---- weekly exam"); s=s[:i]+shim.lstrip("\n")+s[i:]
a='            if n.weekday() == 6 and n.hour == 3 and k("x") not in done: exam(); done[k("x")] = 1\n'
assert a in s; s=s.replace(a,a+"            life_tick()\n",1)
open(p,"w",encoding="utf-8").write(s)
PY
python3 -m py_compile $C && echo compiled || { cp $B/canon.py.pre_L2 $C; echo ROLLBACK; echo END; exit 0; }
cd $N && python3 -I - <<'PY'
import importlib.util,sys,json
sp=importlib.util.spec_from_file_location("canon_t","/workspace/nox/canon/canon.py"); m=importlib.util.module_from_spec(sp)
try: sp.loader.exec_module(m)
except SystemExit: pass
for f in ("morning","evening"):
    o=getattr(m,f)(); L=o["lines"]; print(f,"lines",len(L),"src",o.get("src"),"HOLD",sum("HOLD" in x for x in L),"max_len",max(len(x) for x in L))
m.life_tick(); import json; print("tick",json.load(open("/workspace/nox/state/mind/initiative_v2.json")).get("last_reason"),json.load(open("/workspace/nox/state/mind/initiative_v2.json")).get("sent_today"))
PY
(supervisorctl restart nox_canon 2>&1 || true) | tail -2
sleep 8; ps aux | grep -c "[c]anon/canon.py"
echo END
