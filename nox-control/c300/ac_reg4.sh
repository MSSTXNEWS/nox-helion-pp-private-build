echo "C300: ac_reg4"
R=/workspace/nox/stewards/orch_registry.json
cp -n $R $R.bak_accel_20261126
python3 - <<'PY'
import json
R='/workspace/nox/stewards/orch_registry.json'
d=json.load(open(R))
for j in d['jobs']:
    c=j.get('cmd') or []
    s=' '.join(map(str,c))
    if '--port 8141' in s or '8105' in s and 'Qwen3-30B' in s:
        print('was',j.get('cpus'),s[:60]); j['cpus']='4-7,20-23'
json.dump(d,open(R,'w'),ensure_ascii=False,indent=1)
PY
python3 -c "import json;[print(j.get('cpus')) for j in json.load(open('$R'))['jobs'][:6]]"
for p in $(pgrep -f "subbase-qwe|--port 8141|--port 8144"); do taskset -a -cp 4-7,20-23 $p >/dev/null; echo "$p $(taskset -cp $p|sed 's/.*: //')"; done
grep -n "OTHER=" /workspace/nox/ops/p3_excl_once.sh
sleep 90; for p in $(pgrep -f "subbase-qwe"); do echo "after90s $p $(taskset -cp $p|sed 's/.*: //')"; done
ls -t /workspace/nox/agent/autotrain/rounds | head -2; uptime
