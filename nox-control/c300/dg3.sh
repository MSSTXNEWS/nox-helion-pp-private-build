echo "K1: dg3 (read-only)"
N=/workspace/nox
echo "--- writers of OWNER_ACTIVE (file:line, kind)"
grep -rIn "OWNER_ACTIVE" $N --include=*.py --include=*.sh --include=*.conf --include=*.js -s 2>/dev/null | grep -vE "/(venv|models|node_modules|__pycache__)/|\.bak|\.orig" | grep -E "touch|open\(|write|utime|Path\(|os\.(utime|replace)|>[ ]*\S*OWNER" | sed -E 's#^/workspace/nox/##' | cut -c1-110 | head -15
echo "--- owner_active mtime samples"; for i in 1 2 3 4 5 6; do echo -n "$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE) )) "; sleep 10; done; echo
echo "--- chat_hold/LIVE_TURN"; ls -l --time-style=+%s $N/state/orch/chat_hold $N/agent/LIVE_TURN 2>&1 | awk '{print $6,$7}' | sed "s/^/now=$(date +%s) /" | head -3
echo "--- train_dpo proc"; P=$(pgrep -f 'python -I train_dpo.py' | head -1); echo "pid=$P state=$(awk '{print $3}' /proc/$P/stat 2>/dev/null) vram_proc_MiB=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | awk -F', ' -v p=$P '$1==p{print $2}')"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | awk -F', ' '{print $1"="$2"MiB"}' | tr '\n' ' '; echo
echo "--- trainer dir"; ls -d $N/distill_v2/ckpt_keep/cand_dpo_*_trainer 2>/dev/null | sed 's#.*/##'; ls -la --time-style=+%m%d-%H:%M $N/distill_v2/ckpt_keep/ 2>/dev/null | awk '{print $6,$7}' | tail -8
echo "--- who runs 'step 126'"; python3 -c "
import json;d=json.load(open('$N/state/dispatcher_state.json'));print({k:d[k] for k in ('phase','low_for','ss_round') if k in d})"
tail -c 600 $N/agent/out/train.log 2>/dev/null | grep -oE "(step|шаг)[^,;]{0,40}" | tail -3
echo "====== INVENTORY (path size_MB mtime base rank sha8)"
find / -xdev \( -path /proc -o -path /sys -o -path $N/venv -o -path '*/node_modules' \) -prune -o \( -name adapter_config.json -o -iname '*lora*.safetensors' -o -iname '*lora*.gguf' -o -iname 'adapter_model.safetensors' -o -iname 'adapter_model.bin' \) -print 2>/dev/null | sort -u > /tmp/inv.txt
echo "found=$(wc -l < /tmp/inv.txt)"
python3 - <<'PY'
import json,os,hashlib,time
seen=set()
for p in open("/tmp/inv.txt"):
    p=p.strip(); d=os.path.dirname(p)
    if p.endswith("adapter_config.json"):
        try: c=json.load(open(p))
        except Exception: c={}
        w=[f for f in ("adapter_model.safetensors","adapter_model.bin") if os.path.exists(d+"/"+f)]
        f=d+"/"+w[0] if w else None
        base=(c.get("base_model_name_or_path") or "?").split("/")[-1][:40]; r=c.get("r","?")
    else:
        if d in seen and os.path.exists(d+"/adapter_config.json"): continue
        f=p; base="-"; r="-"
    if not f or not os.path.exists(f) or f in seen: continue
    seen.add(f); h=hashlib.sha256(open(f,"rb").read(1<<22)).hexdigest()[:8]
    print("%s %d %s %s r=%s %s"%(d.replace("/workspace/nox/",""),os.path.getsize(f)>>20,time.strftime("%m%d-%H:%M",time.localtime(os.path.getmtime(f))),base,r,h))
PY
echo "--- image/sd adapters"; ls -d $N/*image* $N/ops/*image* $N/models/*sd* $N/models/*diffus* $N/models/*flux* 2>/dev/null | sed 's#/workspace/nox/##'
supervisorctl status 2>/dev/null | grep -iE "image|sd|diffus|img" | awk '{print $1"="$2}'
echo "--- gguf lora converter: $(find / -xdev -name convert_lora_to_gguf.py -not -path '*/proc/*' 2>/dev/null | head -2 | tr '\n' ' ')"
echo "--- body cmd lora flags: $(grep -c -- '--lora' $N/agent/autotrain/donor_hybrid.cmd.gpu_ncmoe0)"
echo END
