echo "K1: ln_t5"
export RUNNER_TRACKING_ID=""
for q in "python" "курс доллара" "who is the president of france" "погода"; do curl -s -m20 "127.0.0.1:8888/search?q=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$q")&format=json" | python3 -c "
import sys,json;d=json.load(sys.stdin);print(len(d['results']),d.get('unresponsive_engines'))"; done
curl -s -m20 "127.0.0.1:8888/search?q=python&format=json&categories=general&language=en" | python3 -c "
import sys,json;d=json.load(sys.stdin);print('en',len(d['results']),d.get('unresponsive_engines'), sorted({r['engine'] for r in d['results']}))"
