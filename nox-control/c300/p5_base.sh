echo "K1: p5_base"; export RUNNER_TRACKING_ID=""; N=/workspace/nox; A=$N/agent/autotrain; P=$N/state/p5; mkdir -p $P
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL $RAW/p5_bench.py -o /tmp/p5_bench.py
[ -f $P/bench_base.json ] && [ ! -f $P/bench_base0.json ] && cp $P/bench_base.json $P/bench_base0.json
echo "running_ncmoe=$(ps -eo args | grep 'llama-server.*--port 8104' | grep -v grep | grep -o 'n-cpu-moe [0-9]*' | head -1)"
GPUOTHER=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | grep -v "^$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)," | awk -F, '{s+=$2} END{print s+0}'); echo "gpu_other_mib=$GPUOTHER"
if pgrep -f "train_dpo.py|distill_v2.py train" >/dev/null; then echo "ABORT train_active_on_gpu"; echo END; exit 0; fi
bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.cmd.gpu_ncmoe0 --reason "p5 baseline" 2>&1 | tail -1 | sed -E 's#/[^ ]*/#<d>/#g' | cut -c1-200
sleep 5; echo "vram_mib=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) load=$(cut -d' ' -f1 /proc/loadavg)"
P5_BG9=1 python3 /tmp/p5_bench.py base quick 2>&1 | tail -3 | cut -c1-1800
echo END
