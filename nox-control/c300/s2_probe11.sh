#!/bin/bash
D=/workspace/nox/svc/podcastfy; ls $D | head -20
ls $D/*.py 2>/dev/null; for f in $D/*.py; do echo "== $f"; head -c 3000 $f; done 2>/dev/null | head -120
ps aux | grep -i podcastfy | grep -v grep | cut -c1-250 | head -3
curl -s -m5 http://127.0.0.1:18208/openapi.json | python3 -c "import sys,json;d=json.load(sys.stdin);print(json.dumps(d['paths'])[:1500])"
curl -s -m5 -X POST http://127.0.0.1:8091/svc/tts2/synth -H 'Content-Type: application/json' -d '{"text":"тест","voice":"xenia","format":"wav"}' -o /tmp/x.wav -w "tts xenia %{http_code} %{size_download}\n"
curl -s -m5 http://127.0.0.1:8091/svc/tts2/voices | head -c 400
