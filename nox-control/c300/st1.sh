echo "K1: st1"
N=/workspace/nox
echo "d5_installed=$(ls $N/ops/dpo/build_dpo5.py $N/ops/dpo/merge_pairs.py 2>/dev/null | wc -l) sv_dpo5=$(supervisorctl status nox_dpo5_daily 2>/dev/null | awk '{print $2}') once_procs=$(pgrep -fc 'dpo5_daily.py')"
tail -c 600 $N/logs/dpo5_once.log 2>/dev/null | grep -oE '"[a-z_]+": *[0-9]+|step [a-z0-9]+|ждёт|wait[a-z]*' | tail -5
echo "llama $(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) web $(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:18091/web/index.html) cycle_procs=$(pgrep -fc 'train_dpo|char_cycle')"
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader)"
echo END
