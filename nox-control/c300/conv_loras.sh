echo "K1: conv_loras (CPU; dry-run unless GO=1)"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; O=$N/ops/lora_gguf; CV=/workspace/llama.cpp/convert_lora_to_gguf.py; BASE=$N/models/student/Qwen/Qwen3.6-35B-A3B
find $N/distill_v2 $N/ops/v5_live_adapter_20261125 $N/ops/v5_ready4850_20261124 /workspace/pc_jail/outbox/warm $N/ops/v5_knowledge_gpu_20261125 -name adapter_config.json 2>/dev/null | sort -u > /tmp/cl_list.txt
python3 - <<'PY' > /tmp/cl_todo.txt
import json,os,hashlib
seen=set()
for p in open("/tmp/cl_list.txt"):
    d=os.path.dirname(p.strip()); f=d+"/adapter_model.safetensors"
    try: c=json.load(open(p.strip()))
    except Exception: continue
    if not os.path.exists(f) or "Qwen3.6-35B-A3B" not in str(c.get("base_model_name_or_path")) or d.endswith("_trainer"): continue
    h=hashlib.sha256(open(f,"rb").read(1<<22)).hexdigest()[:8]
    if h in seen: continue
    seen.add(h); print(h,d)
PY
echo "compatible_unique=$(wc -l < /tmp/cl_todo.txt) converter=$([ -f $CV ] && echo 1 || echo 0) disk_free_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9) already=$(ls $O/*.gguf 2>/dev/null | wc -l)"
if [ "$GO" = 1 ]; then mkdir -p $O; while read h d; do [ -f $O/$h.gguf ] && continue; A=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9); [ "$A" -lt 13 ] && { echo "disk ${A}G < 13: стоп"; break; }; CUDA_VISIBLE_DEVICES="" nice -n 19 $N/venv/bin/python -I $CV --base $BASE --outfile $O/$h.gguf $d >/dev/null 2>&1; echo "$h rc=$? size_MB=$(( $(stat -c %s $O/$h.gguf 2>/dev/null || echo 0) / 1048576 ))"; done < /tmp/cl_todo.txt; fi
echo END
