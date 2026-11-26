echo "C300: srv_k39"
cd /workspace/nox
date -u +%T; tail -n 6 agent/out/autotrain.log | cut -c1-300
for r in r032 r033 r034; do echo "-- $r"; ls -la --time-style=+%T agent/autotrain/rounds/$r | head -4 | tail -2; grep "скорость:\|ранний стоп\|MOE\|moe" agent/autotrain/rounds/$r/train.log 2>/dev/null | tail -3 | cut -c1-220; done
tail -n 3 state/p3/axis_rollback.jsonl | cut -c1-250; grep -o '"moe_[a-z_]*": *[^,]*' state/speed.json
