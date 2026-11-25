#!/bin/bash
N=/workspace/nox
echo "== chain result"; cat $N/state/p3/chain_tune1.txt 2>&1 | head -40
echo "== creative.html img/generate usage"; f=$(grep -rl "/img/generate" $N/web 2>/dev/null | grep -E "\.html$|\.js$" | head -3); echo "$f"; for x in $f; do grep -n -B3 -A14 "/img/generate" $x | cut -c1-200 | head -50; done
echo "== sun_adapter /generate"; grep -n -E "def |@app|route|korea_img|disabled|/generate|\"url\"|'url'" $N/ops/sun_adapter/sun_adapter.py | cut -c1-190 | head -50
echo "== imgsvc :8500 (python pid 1903225)"; ls -la /proc/$(ss -ltnp | grep ':8500 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd 2>&1 | cut -c1-150
echo "== 8793 images"; curl -s -m 5 127.0.0.1:8793/v1/models | head -c 600; echo; curl -s -m 5 127.0.0.1:8793/openapi.json | python3 -c "import sys,json
try:
 print([p for p in json.load(sys.stdin)['paths']])
except Exception as e: print('no openapi',e)"
echo "== flags"; cat $N/state/flags.json 2>/dev/null | head -c 500; echo
echo "== test /img/generate via web 8091"; curl -s -m 60 -X POST 127.0.0.1:8091/img/generate -H 'Content-Type: application/json' -d '{"prompt":"cat","w":512,"h":512}' | head -c 400; echo
echo "== test 8097 direct"; curl -s -m 60 -X POST 127.0.0.1:8097/generate -H 'Content-Type: application/json' -d '{"prompt":"cat"}' | head -c 400; echo
