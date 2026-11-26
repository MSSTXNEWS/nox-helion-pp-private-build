echo "C300: srv_k18"
cat > /workspace/nox/state/p3/moe_ab_watch.sh <<'W'
#!/bin/bash
# SRV K1: следит за r033, пишет итог A/B MoE в state/p3/moe_ab_result.txt (только чтение логов)
N=/workspace/nox; O=$N/state/p3/moe_ab_result.txt
while true; do
  R=$N/agent/autotrain/rounds/r033/train.log
  if [ -f $R ]; then
    S=$(grep -c "скорость:" $R)
    if [ "$S" -ge 2 ]; then
      { date -u +%FT%TZ; echo "moe_backend=$(grep -o '"moe_backend": *"[a-z_]*"' $N/state/speed.json) ref=23.7 (r032 22.4-25.7)"; grep "скорость:\|профиль" $R | tail -4 | cut -c1-200; grep -o "moe_backend.*" $N/state/p3/axis_rollback.jsonl | tail -1; } > $O
      [ "$S" -ge 4 ] && exit 0
    fi
  fi
  sleep 300
done
W
chmod +x /workspace/nox/state/p3/moe_ab_watch.sh
setsid -f bash /workspace/nox/state/p3/moe_ab_watch.sh </dev/null >/dev/null 2>&1
sleep 2; pgrep -f moe_ab_watch | head -1
