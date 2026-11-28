echo "K1: s6l_a1"
# Поток 6 Личность: разведка, только имена/размеры/числа
N=/workspace/nox; NOW=$(date +%s)
echo "## gate/chat logs"
find $N -maxdepth 4 \( -iname "*gate_log*" -o -iname "chat_gate*" -o -iname "*judge*log*" -o -iname "chat_pairs*" -o -iname "*episodes*.jsonl" \) -not -path "*/archive/*" 2>/dev/null | head -30 | while read f; do echo "$f $(stat -c %s "$f" 2>/dev/null) lines=$( [ -f "$f" ] && wc -l < "$f" )"; done
echo "## ops/dpo"; ls -la $N/ops/dpo 2>/dev/null | awk '{print $5,$9}' | head -60
echo "## exam/test sets"; find $N -maxdepth 5 \( -iname "soul_recognition*" -o -iname "ext_cases*" -o -iname "fidelity_cases*" -o -iname "hold_frozen*" -o -iname "*eval*.jsonl" \) -not -path "*/archive/*" 2>/dev/null | head -30 | while read f; do echo "$f $(stat -c %s "$f")"; done
echo "## mods"; ls $N/mods 2>/dev/null | tr '\n' ' '; echo
echo "## passport structure (ключи и типы, без значений)"
python3 -I - <<'PY'
import json
try: p=json.load(open("/workspace/nox/state/core/passport.json",encoding="utf-8"))
except Exception as e: print("passport err",type(e).__name__); raise SystemExit
def walk(o,pre="",d=0):
    if isinstance(o,dict):
        for k,v in o.items():
            t=type(v).__name__; n=len(v) if hasattr(v,'__len__') else ''
            filled = bool(v) if not isinstance(v,(int,float)) else True
            print("%s%s:%s%s filled=%s"%(pre,k,t,('['+str(n)+']') if n!='' else '',filled))
            if d<2 and isinstance(v,(dict,)): walk(v,pre+"  ",d+1)
walk(p)
PY
echo "## chat_gate.log"; for f in $N/state/chat_gate.log; do [ -f $f ] && echo "lines=$(wc -l <$f) size=$(stat -c %s $f)"; done
echo "## free disk GB $(df -BG /workspace | awk 'NR==2{print $4}')"; python3 -V; pip list 2>/dev/null | grep -i -E "^(datasets|huggingface|pytest|pymorphy)" 
echo END
