echo "K1: rs_t"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; A=$N/agent/autotrain; L=$N/state/rs_t.log; : > $L
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cp -a $A/donor_hybrid.cmd $A/donor_hybrid.cmd.bak_rs_$(date +%s)
cp -a $A/donor_hybrid.cmd $N/state/rs_orig.cmd
curl -fsSL "$R/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn.sh
cat > /tmp/rs_loop.sh <<'EOS'
N=/workspace/nox; A=$N/agent/autotrain; L=$N/state/rs_t.log
rv(){ bash /tmp/rv_turn.sh 2>&1 | grep -E "^(MEM_GET|ADDR|JM|MEM_SET|DRAW|LOAD)" | sed -E 's/"events": \{[^}]*\}//' | cut -c1-200; }
warm(){ python3 - <<'PY'
import json,urllib.request,uuid
for m in ("Привет","Как дела?"):
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"rv-warm","message":m,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=60)
        for _ in r: pass
    except Exception as e: print("warm err",type(e).__name__)
PY
}
echo "=== T=16 (current, baseline)" >> $L; warm; rv >> $L
for T in 8 10 12; do
  sed -E "s/^-t$/-t/" $N/state/rs_orig.cmd > /dev/null
  python3 - $T <<'PY'
import sys
T=sys.argv[1]; L=open("/workspace/nox/state/rs_orig.cmd").read().split("\n")
for i,x in enumerate(L):
    if x=="-t" and i+1<len(L): L[i+1]=T
open("/workspace/nox/agent/autotrain/donor_hybrid.t%s.cmd"%T,"w").write("\n".join(L))
PY
  echo "=== T=$T" >> $L
  bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.t$T.cmd --reason "RESTART rs_t -t $T" 2>&1 | tail -2 >> $L
  warm; warm; rv >> $L
done
echo DONE >> $L
EOS
setsid nohup bash /tmp/rs_loop.sh >/dev/null 2>&1 < /dev/null &
echo started
