#!/bin/bash
F=/workspace/nox/ops/draw/invoke_draw.py
cp -n $F $F.bak_srv_win20
python3 -I - <<'PY'
F="/workspace/nox/ops/draw/invoke_draw.py"; s=open(F,encoding="utf-8").read()
a='time.time() - os.path.getmtime(CHAT_HOLD) < 45'
if a in s: s=s.replace(a,'time.time() - os.path.getmtime(CHAT_HOLD) < 20').replace("чат молчит >=45 с","чат молчит >=20 с (прерывание при ходе чата: _flux/_window_still_ok)"); open(F,"w",encoding="utf-8").write(s); print("patched")
else: print("already/none")
import py_compile; py_compile.compile(F,doraise=True)
PY
grep -n "< 20\|>=20" $F | cut -c1-120
