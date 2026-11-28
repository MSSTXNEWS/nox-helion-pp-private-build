echo "K1: m10_probe2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "=====MEM"; cat $N/svc/mem/nox_mem.py
echo "=====RER"; cat $N/svc/mem/nox_rerank.py
echo "=====EMB"; head -c 2500 $N/canon_night/embed_server.py
echo "=====FREE"; free -g | sed -n 2p; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
echo "=====cron"; crontab -l 2>/dev/null | grep -i -E "mem|sleep|forget" | cut -c1-160
ls $N/state/core | grep -i -E "brief|morning|owner_q|question|conflict|promise" ; ls $N/state/mind | grep -i -E "brief|question|promise|conflict"
grep -n "morning_brief" $N/mods/*.py 2>/dev/null | head -5 | cut -c1-200
echo END
