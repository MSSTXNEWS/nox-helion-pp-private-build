#!/bin/bash
N=/workspace/nox; S=$N/state/p3; T=$(date +%Y%m%d_%H%M%S)
echo "== living restart"; P=$(pgrep -f "venv_living/bin/python living_svc.py"|head -1); PP=$(ps -o ppid= -p $P|tr -d ' '); echo "parent: $(tr '\0' ' ' </proc/$PP/cmdline | cut -c1-150)"
tr '\0' '\n' </proc/$P/environ > /tmp/p3_livenv.txt; LOG=$(readlink /proc/$P/fd/1)
kill -TERM $P; for i in $(seq 1 20); do kill -0 $P 2>/dev/null || break; sleep 0.5; done
sleep 3; NP=$(pgrep -f "venv_living/bin/python living_svc.py"|head -1)
if [ -z "$NP" ]; then (cd $N/svc/living && set -a && . /tmp/p3_livenv.txt 2>/dev/null; set +a; setsid nohup $N/venv_living/bin/python living_svc.py >> ${LOG:-/tmp/living.log} 2>&1 9>&- &); sleep 5; NP=$(pgrep -f "venv_living/bin/python living_svc.py"|head -1); echo "started manually"; else echo "respawned by parent"; fi
echo "new pid $NP"; curl -s -m5 127.0.0.1:18215/health | head -c 200; echo
curl -s -m5 127.0.0.1:18215/ritual/next 2>/dev/null | head -c 200
echo "== speed.json ckpt_every"; F=$N/state/speed.json; cp -p $F $F.bak_p3_$T
python3 - <<'PY'
import json
p="/workspace/nox/state/speed.json"; d=json.load(open(p)); print("before ckpt_every",d.get("ckpt_every"),"holdout_every",d.get("holdout_every"))
d["ckpt_every"]=50; d["_ckpt_why"]="P3 25.11: 25->50 (holdout ~15% интервала; -7..8% времени), применится на перезапуске раунда"
json.dump(d,open(p,"w"),ensure_ascii=False,indent=1); print("after",d["ckpt_every"])
PY
echo "== distill_v2 reads speed.json keys"; grep -n -E "speed\.json|SPEED\.get|spd\.get|sp\.get\(|ckpt.every|holdout" $N/distill_v2/code/distill_v2.py | cut -c1-170 | head -30
echo "== NO_GAIN/rollback in code"; grep -n -E "NO_GAIN|rollback|откат|ворота|G1|axis|ось" $N/distill_v2/code/distill_v2.py | cut -c1-150 | head -15
echo "== genesis_ledger.json"; head -c 700 $N/state/core/genesis_ledger.json; echo; ls -la $N/state/core | head -20 | cut -c1-120
echo "== training reports dir"; ls -t $N/distill_v2 | head -12; ls -t $N/distill_v2/reports 2>/dev/null | head -3
echo "== imgsvc gate code"; grep -rn -E "korea_img_disabled|GB10-only|GB10 only" $N/agent $N/ops/sun_adapter $N/web/pkg/server 2>/dev/null | grep -v -E "\.bak|\.pyc" | cut -c1-190 | head -8
echo "== sd binary"; $N/bin/sd --help 2>&1 | head -3; ls $N/bin | head -30; find $N/models -maxdepth 4 \( -iname "*turbo*" -o -iname "*schnell*" -o -iname "*sdxl*" -o -iname "*.safetensors" -size +1G \) 2>/dev/null | head -10
