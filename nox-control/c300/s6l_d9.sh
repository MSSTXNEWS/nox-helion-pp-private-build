echo "K1: s6l_d9"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/ops/dpo
cat > $D/s6_after_open.sh <<'XX'
#!/bin/bash
D=/workspace/nox/ops/dpo
while pgrep -f s6_open.py >/dev/null; do sleep 30; done
cp $D/dpo_pers1_train.jsonl $D/dpo_pers1_train.jsonl.prev 2>/dev/null
python3 -I $D/s6_assemble.py > $D/s6_assemble.log 2>&1
XX
chmod +x $D/s6_after_open.sh; setsid nohup $D/s6_after_open.sh > /dev/null 2>&1 < /dev/null &
sleep 2; echo "watcher=$(pgrep -f s6_after_open | wc -l) open=$(pgrep -f s6_open.py | wc -l)"
echo END
