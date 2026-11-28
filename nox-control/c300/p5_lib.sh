# usage: set NAME and MODS (python list literal) then: . p5_lib.sh ; uses REF raw for helpers
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain; P=$N/state/p5; mkdir -p $P
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
BASE=$A/donor_hybrid.cmd.gpu_ncmoe0; NEW=$A/donor_hybrid.cmd.p5_$NAME
curl -fsSL $RAW/p5_bench.py -o /tmp/p5_bench.py; curl -fsSL $RAW/p5_cmp.py -o /tmp/p5_cmp.py
echo "base_md5=$(md5sum < $BASE | cut -c1-8) running_ncmoe=$(ps -eo args | grep 'llama-server.*--port 8104' | grep -v grep | grep -o 'n-cpu-moe [0-9]*' | head -1)"
GPUOTHER=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | grep -v "^$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)," | awk -F, '{s+=$2} END{print s+0}')
echo "gpu_other_mib=$GPUOTHER"
if [ "${FORCE_P5:-0}" != 1 ] && [ "$GPUOTHER" -gt 1500 ]; then echo "ABORT train_active_on_gpu"; echo END; exit 0; fi
python3 - "$BASE" "$NEW" "$MODS" <<'PY'
import sys, ast
src, dst, mods = sys.argv[1], sys.argv[2], ast.literal_eval(sys.argv[3])
t = open(src).read().split("\n")
if t and t[-1] == "": t.pop()
for m in mods:
    op, flag = m[0], m[1]; vals = m[2] if len(m) > 2 else []
    if flag in t:
        i = t.index(flag); nold = int(m[3]) if len(m) > 3 else len(vals)
        if op == "set": t[i + 1:i + 1 + nold] = vals
        elif op == "del": del t[i:i + 1 + nold]
    elif op == "set": t += [flag] + vals
open(dst, "w").write("\n".join(t) + "\n")
print("newcmd_lines", len(t))
PY
echo "diff_vs_base:"; diff $BASE $NEW | grep '^[<>]' | tr '\n' ' '; echo
restart(){ bash $N/ops/body_restart.sh --force --cmd $1 --reason "$2" 2>&1 | tail -2 | sed -E 's#/[^ ]*/#<d>/#g' | cut -c1-200; }
restart $NEW "p5 try $NAME"
sleep 5
echo "after_restart: $(curl -s -m3 localhost:8104/health) vram_mib=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) load=$(cut -d' ' -f1 /proc/loadavg)"
python3 /tmp/p5_bench.py $NAME quick 2>&1 | tail -3 | cut -c1-1800
python3 /tmp/p5_cmp.py $P/bench_base.json $P/bench_$NAME.json | tee $P/verdict_$NAME.txt
if grep -q "VERDICT KEEP" $P/verdict_$NAME.txt; then echo "KEEP $NAME (cmd оставлен работающим)"; echo $NAME > $P/last_keep; cp $NEW $P/best_cmd.txt 2>/dev/null
else echo "REVERT $NAME"; restart $BASE "p5 revert $NAME"; fi
echo "final: $(curl -s -m3 localhost:8104/health) ncmoe=$(ps -eo args | grep 'llama-server.*--port 8104' | grep -v grep | grep -o 'n-cpu-moe [0-9]*' | head -1)"
echo END
