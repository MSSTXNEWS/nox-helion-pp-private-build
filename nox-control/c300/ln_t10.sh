echo "K1: ln_t10"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=$N/web/pkg/webroot; now=$(date +%s)
F=$N/agent/out/inner_loop.log
echo "lines=$(wc -l <$F)"; tail -n 300 $F | grep -iE "fail|error|отказ|traceback|exception" | sed -E 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/T/g; s/[0-9]+/N/g' | cut -c1-110 | sort | uniq -c | sort -rn | head -6
echo "first/last ts:"; tail -n 300 $F | head -1 | cut -c1-60; tail -n 1 $F | cut -c1-120
h=$(date -u +%H); tail -n 600 $F | grep -cE "^$(date -u +%Y-%m-%d)T?$h|$(date +%H):" | sed 's/^/lines_this_hour=/'
echo "== minichat snippet"; grep -n -iE "mini-?chat|nox-mini|noxMini" $R/photo.html | head -4 | cut -c1-200
ls $R | grep -iE "mini|assistant|widget" | head; ls $R/js $R/assets 2>/dev/null | grep -i mini | head
echo "== vision"; curl -s -m5 127.0.0.1:8793/v1/models | python3 -c "import sys,json;print([m['id'] for m in json.load(sys.stdin).get('data',[])][:40])" 2>&1 | cut -c1-500
ls $N/models 2>/dev/null | head -40 | tr '\n' ' '; echo; ls $N/models/warm 2>/dev/null | head -30 | tr '\n' ' '
echo; echo "worms_hb age=$(( now-$(stat -c %Y $N/state/worms_hb.json) ))s"; head -c 300 $N/state/worms_hb.json; echo
echo "== living incognito retest"
L=127.0.0.1:18091/svc/nox-living; C=lt$RANDOM
cnt(){ curl -s -m8 "$L/mem/list?n=200" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['items']))"; }
n0=$(cnt); curl -s -m8 -X POST $L/incognito -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"on\":true}" >/dev/null
curl -s -m25 -X POST $L/post -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"user\":\"launch_t\",\"text\":\"запомни: мой тайный пароль от сейфа это тестовый-инкогнито-9917 и это очень важно\",\"answer\":\"хорошо, запомнил\"}" | head -c 100; echo
sleep 4; n1=$(cnt); echo "living mem before=$n0 after_incognito_post=$n1"
curl -s -m8 -X POST $L/incognito -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"on\":false}" >/dev/null
curl -s -m25 -X POST $L/post -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"user\":\"launch_t\",\"text\":\"запомни: мой тайный пароль от сейфа это тестовый-обычный-9918 и это очень важно\",\"answer\":\"хорошо, запомнил\"}" | head -c 100; echo
sleep 4; n2=$(cnt); echo "control (incognito off) after=$n2"
curl -s -m8 "$L/mem/list?n=200" | python3 -c "
import sys,json
for i in json.load(sys.stdin)['items']:
    t=json.dumps(i,ensure_ascii=False)
    if 'тестовый-' in t: print('test item id',i.get('id'))"
