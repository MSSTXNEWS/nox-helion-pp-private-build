echo "K1: p5_recon"; N=/workspace/nox
echo "--cmd:"; cat $N/agent/autotrain/donor_hybrid.cmd.gpu_ncmoe0 | sed -E 's#(/[A-Za-z0-9_.-]+)+/#<dir>/#g'
echo "--body_restart:"; sed -n 1,60p $N/ops/body_restart.sh | sed -E 's/(KEY|TOKEN|PASS)[^ ]*/<x>/gI'
echo "--proc:"; ps -eo pid,etimes,args | grep -E "llama-server" | grep -v grep | sed -E 's#(/[A-Za-z0-9_.-]+)+/#<dir>/#g' | cut -c1-400
echo "--gpu:"; nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
echo "--disk:"; df -BG /workspace | tail -1
echo "--llama:"; B=$(ps -eo args | grep llama-server | grep -v grep | head -1 | awk '{print $1}'); echo $B | sed -E 's#.*/##'; $B --version 2>&1 | head -3
$B --help 2>&1 | grep -E -- "flash-attn|-ub,|cache-reuse|cache-type|--parallel|spec|draft|lookup|ngram|--mlock|--threads|cont-batching|--slot|kv-unified|cache-ram" | cut -c1-160
echo "--ggufs:"; find /workspace -name "*.gguf" -size +50M 2>/dev/null | xargs -r ls -la | awk '{printf "%d MB %s\n",$5/1048576,$9}' | sed -E 's#/[^ ]*/#<dir>/#' | sort -k4 | head -60
echo "--lock:"; ls -d $N/state/BODY_LOCK /home/claude/brain/BODY_LOCK 2>&1
curl -s localhost:8104/props | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ('total_slots','model_alias','build_info')}); print(d.get('default_generation_settings',{}).get('n_ctx'))" 2>&1
curl -s localhost:8104/slots | python3 -c "import json,sys;d=json.load(sys.stdin);print([(s['id'],s.get('is_processing'),s.get('n_ctx')) for s in d])" 2>&1
uptime
echo END
