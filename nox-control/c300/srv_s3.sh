#!/bin/bash
F=/workspace/nox/agent/nox_agents/lib.py
cp -n $F $F.bak_srv_atomic
python3 -I - <<'PY'
F="/workspace/nox/agent/nox_agents/lib.py"; s=open(F,encoding="utf-8").read()
old='    tmp = path + ".tmp"\n    with open(tmp, "w", encoding="utf-8") as f:'
new='    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), __import__("threading").get_ident())   # ATOMIC_P3: уникальный tmp, без гонки писателей\n    with open(tmp, "w", encoding="utf-8") as f:'
if "ATOMIC_P3" in s: print("already")
elif old in s:
    s=s.replace(old,new,1); open(F,"w",encoding="utf-8").write(s); import py_compile; py_compile.compile(F,doraise=True); print("patched")
else: print("anchor missing")
PY
sed -n 50,60p $F
grep -rn '\.tmp"' /workspace/nox/agent/nox_agents/*.py | grep -v "lib.py" | head -5 | cut -c1-150
cat /workspace/nox/state/p3/persona_gen.json
