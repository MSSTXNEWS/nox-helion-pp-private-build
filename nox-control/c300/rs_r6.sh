echo "K1: rs_r6"
export RUNNER_TRACKING_ID=""
W=/workspace/nox; C=$W/web/pkg/server/chat_core.py
grep -n "def _k1_fast_ok" -A12 $C | cut -c1-260
grep -n "def _via_fast" -A40 $C | cut -c1-260
grep -n "def _via_rte" -A30 $C | cut -c1-200 | grep -nE "req|post|POST|stream|nox_user|messages" | head -12
grep -n "def _le\b\|def _le_num\|def _living_call_t" -A5 $C | cut -c1-200 | head -24
echo "--- fast keys"; curl -s -m30 -X POST -H 'Content-Type: application/json' -d '{"q":"Что такое энтропия? кратко","history":[]}' http://127.0.0.1:18217/fast | python3 -c "import sys,json;j=json.load(sys.stdin);print({k:(v if k!='text' else len(v)) for k,v in j.items()})" 2>&1 | cut -c1-500
echo "--- litellm models"; curl -s -m6 http://127.0.0.1:8793/v1/models | python3 -c "import sys,json;print(' '.join(m['id'] for m in json.load(sys.stdin)['data']))" | cut -c1-2500
echo "--- judge routes"; grep -nE "@app\.(get|post)|def .*fast" $W/judges/judge_service.py | head -20
echo "--- draft"; curl -s -m10 -o /tmp/d.o -w "%{http_code} %{time_total}\n" "http://127.0.0.1:18091/svc/advisors/draft?typed=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("расскажи мне про солнце"))')&chat=rv-x"; head -c 300 /tmp/d.o | sed 's/[а-яА-Я]/x/g'
echo "--- rte"; grep -n "RTE\b" $C | head -5 | cut -c1-120; grep -n "/v1/turns" $C | cut -c1-200 | head -4
