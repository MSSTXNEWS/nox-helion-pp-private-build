echo "K1: rs_t2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain; L=$N/state/rs_t2.log; : > $L
pkill -f /tmp/rs_loop.sh 2>/dev/null
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
[ -s /tmp/rv_turn.sh ] || curl -fsSL "$R/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn.sh
mk(){ python3 - $1 <<'PY'
import sys
T=sys.argv[1]; L=open("/workspace/nox/state/rs_orig.cmd").read().split("\n")
for i,x in enumerate(L):
    if x=="-t" and i+1<len(L): L[i+1]=T
open("/workspace/nox/agent/autotrain/donor_hybrid.t%s.cmd"%T,"w").write("\n".join(L))
PY
}
rst(){ for k in 1 2 3 4 5 6 7 8; do bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.t$1.cmd --reason "RESTART rs_t2 -t $1" 2>&1 | tail -1 | grep -q "ИТОГ: ok" && return 0; sleep 30; done; return 1; }
warm(){ python3 - <<'PY'
import json,urllib.request
for m in ("Привет","Как дела?","Расскажи коротко о себе"):
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-warm","message":m,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
        for _ in r: pass
    except Exception as e: print("warm err",type(e).__name__)
PY
}
rv(){ bash /tmp/rv_turn.sh 2>&1 | grep -E "^(MEM_GET|ADDR|JM|LOAD)" | sed -E 's/"events": \{[^}]*\}//;s/"(sec|done|error|len)": [^,}]*,? ?//g' | cut -c1-120; }
for T in 16 12 10; do
  mk $T; echo "=== T=$T" >> $L
  if rst $T; then warm; echo "run1" >> $L; rv >> $L; echo "run2" >> $L; rv >> $L; else echo "restart_failed" >> $L; fi
done
echo DONE >> $L; cat $L
