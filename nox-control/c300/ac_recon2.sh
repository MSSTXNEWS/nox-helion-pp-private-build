echo "C300: ac_recon2"
echo "== GPU util 40x1s"; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader -l 1 & P=$!; sleep 40; kill $P
echo "== trainer"; T=$(pgrep -f "distill_v2.py train" | head -1); echo pid $T; taskset -cp $T; ps -L -p $T -o tid,psr,pcpu,ni | sort -k3 -nr | head -6
echo "== mpstat"; mpstat -P ALL 3 1 2>/dev/null | tail -18 || top -bn1 | head -20
echo "== venv"; V=/workspace/nox/venv/bin/python; $V -c "
import importlib
for m in ['torch','unsloth','unsloth_zoo','liger_kernel','peft','transformers','trl','bitsandbytes','triton','xformers']:
    try:
        x=importlib.import_module(m);print(m,getattr(x,'__version__','?'))
    except Exception as e: print(m,'NO',str(e)[:60])
" 2>&1 | grep -v Warn
echo "== disk"; df -h /workspace /tmp | cat; du -xsh /workspace/nox/* 2>/dev/null | sort -rh | head -8
echo "== train log"; ls -t /workspace/nox/distill_v2/*.log /workspace/nox/logs/*train* 2>/dev/null | head -3; tail -n 12 $(ls -t /workspace/nox/logs/*train* /workspace/nox/distill_v2/train*.log 2>/dev/null | head -1) | cut -c1-250
echo "== speed.json tail"; tail -c 900 /workspace/nox/state/speed.json
