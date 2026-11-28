echo "K1: s6l_t1"
N=/workspace/nox; S=$N/state/core
ls -la $N/canon | awk '{print $5,$9}' | head -30
F=$N/canon/canon.py; echo "lines=$(wc -l < $F) md5=$(md5sum < $F | cut -c1-8)"
grep -n "^def \|^class \|morning\|evening\|initiative\|quiet" $F | cut -c1-170 | head -70
echo "## who calls / supervisor"; grep -rl "canon.py\|morning_brief" $N/supervisor $N/agent 2>/dev/null | head -5; supervisorctl status 2>/dev/null | grep -i -E "canon|brief|initiat|life|tick" | head
python3 -I - <<'PY'
import json,os
S="/workspace/nox/state/core"
def shape(o,d=0):
    if isinstance(o,dict): return {k:shape(v,d+1) for k,v in list(o.items())[:14]} if d<2 else "dict[%d]"%len(o)
    if isinstance(o,list): return [len(o),shape(o[0],d+1) if o else None] if d<2 else "list[%d]"%len(o)
    return type(o).__name__+(("%d"%len(o)) if isinstance(o,str) else "")
for f in ["morning_brief_v5.json","evening_brief_v5.json","initiative.json","promises.json","self_now.json","life_loop.json","outbox_cfg.json"]:
    p=S+"/"+f
    if not os.path.exists(p): print(f,"absent"); continue
    try: d=json.load(open(p,encoding="utf-8")); print(f,os.path.getsize(p),json.dumps(shape(d),ensure_ascii=False)[:700])
    except Exception as e: print(f,"err",type(e).__name__)
for f in ["journal.jsonl","registry.json"]:
    p=S+"/"+f; print(f,os.path.getsize(p) if os.path.exists(p) else "absent")
PY
ls $N/state/outbox | head -5; ls $N/state/outbox | wc -l
echo END
