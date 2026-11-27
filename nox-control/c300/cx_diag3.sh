echo "K1: cx_diag3"
P=$(ss -ltnp | grep ":8104 " | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1)
tr '\0' ' ' < /proc/$P/cmdline | grep -oE -- '(-t|--threads|-ngl|--n-gpu-layers|--n-cpu-moe|-ncmoe|--cpu-moe|--parallel|-np|-c|--ctx-size|-fa|--flash-attn|-ctk|-ctv|-ub|-b|--override-tensor|-ot) [^ ]+' | tr '\n' ' '; echo
echo "uptime_s=$(( $(date +%s) - $(stat -c %Y /proc/$P) )) nice=$(ps -o ni= -p $P) state=$(ps -o stat= -p $P)"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total --format=csv,noheader
curl -s -m 5 http://127.0.0.1:8104/slots | python3 -c "import json,sys;d=json.load(sys.stdin);print('busy',[s['id'] for s in d if s.get('is_processing')])"
ls -1t /workspace/nox/agent/autotrain/donor_hybrid.cmd* | head -4 | xargs -n1 basename
diff <(tr '\n' ' ' < /workspace/nox/agent/autotrain/donor_hybrid.cmd) <(tr '\n' ' ' < $(ls -1tr /workspace/nox/agent/autotrain/donor_hybrid.cmd.bak_rs_* | head -1)) | head -5 | cut -c1-300
echo "load=$(cut -d' ' -f1 /proc/loadavg)"
ps -eo pcpu,comm --sort=-pcpu | head -6
