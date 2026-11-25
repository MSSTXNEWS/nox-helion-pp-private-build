N=/workspace/nox
echo "== hunger defs"; grep -n -i -E "hunger|голод" $N/brain/BRAIN/self_awareness.py $N/brain/GENOME/MATRIX/_build/g_life.py $N/state/worms_hb.json | head -10 | cut -c1-220
echo "== worms_hb"; head -c 500 $N/state/worms_hb.json; echo
echo "== results_v2.json"; python3 -c "
import json;d=json.load(open('$N/distill_v2/results_v2.json'));print(type(d).__name__, list(d)[:8] if isinstance(d,dict) else len(d)); 
x=d if isinstance(d,dict) else d[-1]
import itertools
print(json.dumps(x,ensure_ascii=False)[:900])"
echo "== latest rounds"; ls -t $N/distill_v2/gates 2>/dev/null | head -4; ls -t $N/distill_v2/train_logs | head -2
L=$N/distill_v2/train_logs/$(ls -t $N/distill_v2/train_logs | head -1); grep -E "шаг [0-9]+, loss|ворота|NO_GAIN|откат|раунд" $L | tail -6 | cut -c1-200
echo "== ckpt_guard actions"; grep -n -E "EARLY_STOP|rollback|откат|NO_GAIN" $N/distill_v2/code/ckpt_guard.py 2>/dev/null | head -8 | cut -c1-170; ls $N/distill_v2/code | head -20
echo "== training queue / orchestrator state"; ls $N/state/orch | head -20
echo "== executors in c300 logs (heartbeat for item 8)"; ls $N/state/p3
