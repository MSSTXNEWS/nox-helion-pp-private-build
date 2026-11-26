echo "C300: srv_k16"
cd /workspace/nox
grep -n "moe_backend\|speed.json\|rollback\|ref_s_per_step" ops/p3_axis_guard.py | cut -c1-220 | head -30
ls -t agent/autotrain/rounds | head -4
R=agent/autotrain/rounds/$(ls -t agent/autotrain/rounds | head -1); ls $R | head; tail -n 4 $R/train.log 2>/dev/null | cut -c1-250
grep -h "с/шаг\|s/step\|it/s\|step_time" $R/train.log 2>/dev/null | tail -3 | cut -c1-200
cat state/speed.json | tail -c 700
