echo "K1: rs_recon3"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
grep -n "def list_facts" -A8 $W/svc/mem/nox_mem.py | cut -c1-220
grep -n "def forget" -A8 $W/svc/mem/nox_mem.py | cut -c1-220
grep -nE "18220|/recall" $W/web/pkg/server/chat_core.py | cut -c1-200 | head
curl -s -m5 -X POST -H 'Content-Type: application/json' -d '{"user":"owner","n":3}' http://127.0.0.1:18220/list | python3 -c "import sys,json;j=json.load(sys.stdin);print(len(j.get('items',[])), [list(x.keys()) if isinstance(x,dict) else type(x).__name__ for x in j.get('items',[])[:1]])"
cat $W/state/rs_t.log 2>/dev/null
