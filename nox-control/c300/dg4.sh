echo "K1: dg4 (read-only)"
N=/workspace/nox
echo "--- OWNER_ACTIVE / chat_hold mentions by file (counts)"
grep -rIlE "OWNER_ACTIVE|chat_hold" $N /etc/supervisor* /etc/cron* /var/spool/cron 2>/dev/null --exclude-dir=venv --exclude-dir=models --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=.git | grep -vE "\.bak|\.orig|\.log|\.jsonl" | sed 's#/workspace/nox/##' | head -30
echo "--- writer lines"
grep -rInE "OWNER_ACTIVE" $N --include=*.py --include=*.sh --exclude-dir=venv --exclude-dir=models --exclude-dir=node_modules 2>/dev/null | grep -vE "\.bak|\.orig|ops/dpo/|k2_" | sed -E 's#/workspace/nox/##' | cut -c1-170 | head -14
echo "--- chat_hold writers"
grep -rInE "chat_hold" $N --include=*.py --include=*.sh --exclude-dir=venv --exclude-dir=models 2>/dev/null | grep -vE "\.bak|\.orig" | sed -E 's#/workspace/nox/##' | cut -c1-170 | head -8
echo "--- age of OWNER_ACTIVE over 3 min, every 15s"; for i in $(seq 12); do echo -n "$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE) )) "; sleep 15; done; echo
echo "--- inventory (no -xdev)"
find /workspace /home /root /mnt /data /opt /srv /var/lib -maxdepth 9 \( -path '*/venv' -o -path '*/node_modules' -o -path '*/site-packages' -o -path '*/.git' \) -prune -o \( -name adapter_config.json -o -iname '*lora*.safetensors' -o -iname '*lora*.gguf' -o -name 'adapter_model.safetensors' -o -name '*.lora' \) -print 2>/dev/null | sort -u > /tmp/inv.txt
echo "found=$(wc -l < /tmp/inv.txt) mounts: $(df --output=target | tr '\n' ' ' | cut -c1-200)"
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
        base=(c.get("base_model_name_or_path") or "?").split("/")[-1][:36]; r=c.get("r","?")
    else:
        f=p; base="-"; r="-"
        if os.path.exists(d+"/adapter_config.json"): continue
    if not f or not os.path.exists(f) or f in seen: continue
    seen.add(f); h=hashlib.sha256(open(f,"rb").read(1<<22)).hexdigest()[:8]
    print("%s %dMB %s %s r=%s %s"%(d.replace("/workspace/nox/",""),os.path.getsize(f)>>20,time.strftime("%m%d-%H:%M",time.localtime(os.path.getmtime(f))),base,r,h))
PY
echo "--- images dir"; ls $N/images 2>/dev/null | head -5 | wc -l; ls -d $N/models/flux/* 2>/dev/null | sed 's#.*/##' | head; find $N/models/flux -iname '*lora*' 2>/dev/null | head -5 | sed 's#/workspace/nox/##'
echo "--- converter: $(find / -name 'convert_lora_to_gguf.py' 2>/dev/null | head -2 | tr '\n' ' ')"; echo "llama-server: $(pgrep -fa llama-server | head -1 | awk '{print $1}')"
echo END
