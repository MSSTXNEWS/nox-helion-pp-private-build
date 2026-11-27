echo "K1: ln_r5"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== mem routes"; grep -nE "path *==|startswith\(\"/|\"/[a-z_/]+\"" $N/svc/mem/nox_mem.py | head -30 | cut -c1-140
echo "== living routes"; grep -nE "\"/[a-z_/]+\"" $N/svc/living/living_svc.py | head -20 | cut -c1-120
echo "== passport keys"; python3 - <<'PY'
import json
d=json.load(open('/workspace/nox/state/core/passport.json'))
def ks(x,p='',dep=0):
    if isinstance(x,dict):
        for k,v in list(x.items())[:25]:
            print(p+k, type(v).__name__, (len(v) if hasattr(v,'__len__') else ''))
            if dep<1: ks(v,p+k+'.',dep+1)
ks(d)
PY
echo "== inner loop"; ls $N/brain/CON | head; ls -t $N/logs/*inner* $N/state/*/*inner* $N/brain/CON/*.log 2>/dev/null | head -3
grep -n "log\|\.jsonl" $N/brain/CON/nox_inner_loop.py | head -8 | cut -c1-140
echo "== guard 18218"; grep -nE "\"/[a-z_/]+\"" $N/svc/guard/*.py 2>/dev/null | head -8 | cut -c1-120; ls $N/svc
echo "== stt tts"; ls $N/c300_voice 2>/dev/null | head; grep -nE "\"/[a-z_/]+\"" $N/svc/*/stt*.py $N/svc/*/tts*.py 2>/dev/null | head -10 | cut -c1-120
echo "== agents routes"; grep -rnE "\"/(task|tasks|consilium|worms|golden|board)[a-z_/]*\"" $N/agent/nox_agents/*.py 2>/dev/null | head -10 | cut -c1-140
