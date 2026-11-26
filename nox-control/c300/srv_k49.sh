echo "C300: srv_k49"
cd /workspace/nox
cp ops/liska_selfkd.py ops/liska_selfkd.py.bak_k1_live_$(date +%s)
/workspace/nox/venv/bin/python -I - <<'PY'
p='/workspace/nox/ops/liska_selfkd.py'; s=open(p,encoding='utf8').read()
a="        for pp, wp in zip(parts, w):\n            if not pp:\n                continue\n"
assert s.count(a)==1, s.count(a)
b="        for pp, wp in zip(parts, w):\n            _lw = 0   # K1 26.11: чат первый — пауза между микро-частями шага, пока идёт живой ход (макс. 90 с, откат: убрать эти 3 строки)\n            while _lw < 360 and __import__(\"os\").path.exists(\"/workspace/nox/agent/LIVE_TURN\"): time.sleep(0.25); _lw += 1\n            if not pp:\n                continue\n"
open(p,'w',encoding='utf8').write(s.replace(a,b))
PY
/workspace/nox/venv/bin/python -I -m py_compile ops/liska_selfkd.py && echo COMPILED
grep -n "^import\|^from" ops/liska_selfkd.py | head -5
grep -n "def split_batches" -A8 ops/liska_selfkd.py | cut -c1-160 | head -12
grep -n "split\b.*=" ops/liska_selfkd.py | head -6 | cut -c1-160
echo == flux
grep -n "def _flux\|def _window" -A28 ops/draw/invoke_draw.py | cut -c1-230 | head -80
