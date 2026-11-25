#!/bin/bash
W=/workspace/nox/web/pkg/server
echo "== _img_file handler"; n=$(grep -n "def _img_file" $W/web_server.py | cut -d: -f1); sed -n "${n},$((n+22))p" $W/web_server.py | cut -c1-210
grep -n "/img/file" $W/web_server.py | head -3 | cut -c1-160
echo "== 8793 images test"; time (curl -s -m 100 -X POST 127.0.0.1:8793/v1/images/generations -H 'Content-Type: application/json' -d '{"prompt":"a cute cat, photo","model":"auto"}' | python3 -c "
import sys,json
raw=sys.stdin.read()
try:
    d=json.loads(raw); print({k:(str(v)[:200]) for k,v in d.items()}); x=d.get('data',[{}])[0]; print({k:str(v)[:120] for k,v in x.items()})
except Exception as e: print('raw',raw[:300])")
echo "== web is running python/where does /img/file read"; ls -d /workspace/nox/state/img* /workspace/nox/data/img* /workspace/nox/state/web/img* 2>/dev/null | head
echo "== TTFT x2"; python3 /tmp/p3_t.py; python3 /tmp/p3_t.py; curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print('busy',sum(1 for s in json.load(sys.stdin) if s['is_processing']),'/3')"; echo "load $(cut -d' ' -f1-3 /proc/loadavg) avail $(grep MemAvailable /proc/meminfo)"
