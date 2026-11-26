echo "C300: ac_r038"
for r in r038 r037 r036; do echo "== $r"; grep -aE "скорость|профиль|обновление раунда|этап|phase|шаг [0-9]+," /workspace/nox/agent/autotrain/rounds/$r/train.log | tail -5 | cut -c1-220; done
echo "ps"; T=$(pgrep -f "distill_v2.py train"|head -1); echo $T $(taskset -cp $T|sed 's/.*: //') etimes $(ps -o etimes= -p $T)
for p in $(pgrep -f "subbase-qwe|--port 8141"); do echo "$p $(taskset -cp $p|sed 's/.*: //')"; done
uptime
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -l 1 & P=$!; sleep 45; kill $P
