#!/bin/bash
python3 -c "
import json;d=json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'))
for k in ('whisperlive','podcastfy','tts2'):print(k,d.get(k))
print(len(d))"
grep -n "svc_registry" -r /workspace/nox/web/pkg/server/*.py 2>/dev/null | head -5
P=/workspace/nox/svc/podcastfy/venv/lib/python3.11/site-packages/podcastfy
grep -n "def generate_podcast" -A22 $P/client.py | head -40
head -12 /workspace/nox/svc/start_extra.sh; sed -n 1,14p /workspace/nox/svc/start_d.sh | cut -c1-200
