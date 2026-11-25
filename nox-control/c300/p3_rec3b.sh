#!/bin/bash
N=/workspace/nox
echo "== chat_hold age $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) ))s; mode $(cat $N/agent/autotrain/mode); gpu_phase: $(cat $N/state/gpu_phase)"
echo "== arbiter.py"; wc -l $N/agent/arbiter.py; sed -n 1,40p $N/agent/arbiter.py | cut -c1-190
echo "== body_restart.sh"; sed -n 1,30p $N/ops/body_restart.sh | cut -c1-190
echo "== rituals living_svc"; f=$(find $N -maxdepth 3 -name living_svc.py | head -1); echo $f; sed -n 250,270p $f | cut -c1-200; grep -n -E "08:00|22:30|ritual|ритуал|MSK|МСК|hour" $f | head -15 | cut -c1-160
echo "== speed.json"; cat $N/state/speed.json | head -c 800; echo
echo "== training gate refs"; grep -n -E "NO_GAIN|born_at|genesis|Genesis|ledger" $N/ops/*.py $N/ops/distill_v2.py $N/agent/autotrain/autotrain.sh 2>/dev/null | head -10 | cut -c1-160; find $N -maxdepth 3 -iname "*genesis*" -o -maxdepth 3 -iname "*ledger*" 2>/dev/null | grep -v venv | head
echo "== distill_v2 path"; find $N -maxdepth 3 -name distill_v2.py | head -3
echo "== imgsvc 8500"; curl -s -m5 127.0.0.1:8500/health | head -c 300; echo; ls /proc/$(ss -ltnp | grep ':8500 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd -l | sed 's/.*-> //'; grep -n -i -E "korea_img_disabled|GB10-only" -r $N/agent/*.py $N/ops/sun_adapter/*.py 2>/dev/null | head -5 | cut -c1-200
echo "== VRAM"; nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "== invokeai models"; curl -s -m8 127.0.0.1:9090/api/v2/models/ 2>/dev/null | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin); [print(m.get('name'),m.get('base'),m.get('type')) for m in d.get('models',[])[:20]]
except Exception as e: print('no models api',e)"
ls $N/invoke_root/models 2>/dev/null | head; du -sh $N/invoke_root 2>/dev/null
echo "== priority proxy candidates"; which haproxy nginx caddy 2>/dev/null; pip list 2>/dev/null | grep -i -E "litellm|aiohttp" | head
echo "== web_auth_off"; ls -la $N/state/web_auth_off 2>&1
