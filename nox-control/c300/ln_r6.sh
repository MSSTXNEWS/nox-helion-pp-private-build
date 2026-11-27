echo "K1: ln_r6"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
sed -n 140,175p $N/svc/mem/nox_mem.py | cut -c1-210
echo "== pass addressing shape"; python3 -c "
import json;d=json.load(open('$N/state/core/passport.json'))['addressing']
for k,v in d['users'].items(): print('user',len(k), {a:(type(b).__name__, len(b) if hasattr(b,'__len__') else b) for a,b in (v.items() if isinstance(v,dict) else [])})
print('unknown',{a:(type(b).__name__, len(b) if hasattr(b,'__len__') else b) for a,b in d['unknown_speaker'].items()})"
echo "== who 18218 8093 8094 8810 8120 9100 8400"; for p in 18218 8093 8094 8810 8120 9100 8400 8793 8200 18217; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "$p: $(tr '\0' ' ' </proc/$pid/cmdline 2>/dev/null | cut -c1-110)"; done
echo "== inner loop status"; head -c 500 $N/state/agents/inner-loop.json; echo; pgrep -af nox_inner_loop | cut -c1-120
ls -la --time-style=+%H:%M $N/state/thoughts.jsonl /root/nox/state/thoughts.jsonl 2>&1 | cut -c1-120
grep -rn "inner" /etc/supervisor/conf.d/*.conf $N/brain/CON/con_install.sh 2>/dev/null | head -5 | cut -c1-160
