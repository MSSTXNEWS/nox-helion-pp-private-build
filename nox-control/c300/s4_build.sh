# S4 build: deploy mods/foreign_mark.py (new file, chat_core not touched) + builder; run builder in background (writes ops/dpo/dpo_inj1_*.jsonl only)
N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4_files"
echo "S4B $(date +%F_%H:%M) disk_avail=$(df -BG --output=avail $N | tail -1)"
[ -d $N/mods ] || { echo "no $N/mods"; ls $N | head -30; exit 0; }
mkdir -p $N/mods/tests
for f in foreign_mark.py; do curl -fsSL --retry 3 "$RAW/$f" -o $N/mods/$f && echo "ok $f $(stat -c %s $N/mods/$f)"; done
curl -fsSL --retry 3 "$RAW/test_foreign_mark.py" -o $N/mods/tests/test_foreign_mark.py && echo "ok test"
curl -fsSL --retry 3 "$RAW/build_dpo6_inj.py" -o $N/ops/dpo/build_dpo6_inj.py && echo "ok builder"
cd $N/mods && python3 -I -m pytest -q tests 2>&1 | tail -3
export RUNNER_TRACKING_ID=""
setsid nohup python3 -I $N/ops/dpo/build_dpo6_inj.py > $N/ops/dpo/build_dpo6_inj.log 2>&1 < /dev/null &
sleep 100; tail -c 3000 $N/ops/dpo/build_dpo6_inj.log
