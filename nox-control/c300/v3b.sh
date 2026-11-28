echo "K1: v3b"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; ts=$(date +%s)
# 1) судья до показа давал 13-30 с на коде/совете -> выключить, скорость важнее
touch $N/state/chat_bo2.off; echo "bo2_off=1"
# 2) /api/roles в Caddy -> сайдкар
CF=$N/ops/web_chat_auth/Caddyfile; cp -a $CF $CF.bak_v3b_$ts
if ! grep -q "/api/roles" $CF; then sed -i 's#path /api/draft /api/context#path /api/roles /api/roles/* /api/draft /api/context#' $CF; fi
PID=$(pgrep -f "caddy.*web_chat_auth/Caddyfile" | head -1); BIN=$(readlink /proc/$PID/exe)
if $BIN validate --config $CF --adapter caddyfile >/dev/null 2>&1; then echo valid=yes
  SV=$(supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do supervisorctl pid $p 2>/dev/null | grep -qx "$PID" && echo $p; done | head -1)
  [ -n "$SV" ] && supervisorctl restart $SV >/dev/null 2>&1 && echo caddy_restarted
else echo "valid=no -> restore"; cp -a $CF.bak_v3b_$ts $CF; fi
sleep 3; echo "roles_api $(curl -s -o /dev/null -m 6 -w %{http_code} http://127.0.0.1:18091/api/roles) side_direct $(curl -s -o /dev/null -m 6 -w %{http_code} http://127.0.0.1:18798/api/roles)"
echo "sidecar_off=$([ -f $N/state/sidecar.off ] && echo 1 || echo 0)"
# 3) где цикл обучения берёт данные (только имена путей)
C=$N/ops/dpo/char_cycle.sh; [ -f $C ] && grep -oE '(/workspace/nox/[A-Za-z0-9_./-]+\.(jsonl|json|parquet)|/workspace/nox/[A-Za-z0-9_./-]*(data|pairs|dpo)[A-Za-z0-9_./-]*)' $C | sort -u | head -15
ls $N/ops/dpo/*.py 2>/dev/null | xargs -n1 basename | tr '\n' ' '; echo
echo "trainer_nice=$(ps -o ni= -p $(pgrep -f 'dpo|char_cycle' | head -1) 2>/dev/null) gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader)"
python3 - <<'PY'
import json,urllib.request,time,uuid
for q in ("Напиши на Python функцию сортировки слиянием","/совет Учить ли Go в 2026?"):
    t0=time.time();first=None
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-"+uuid.uuid4().hex[:6],"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=170)
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s)
        if o.get("t")=="delta" and first is None: first=time.time()-t0
        if o.get("t") in("done","error"): break
    print("XT ttft=%.2f total=%.1f"%(first or 99,time.time()-t0))
PY
echo END
