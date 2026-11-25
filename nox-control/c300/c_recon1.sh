#!/bin/bash
# c_recon1: read-only recon for C
N=/workspace/nox; P=$N/web/pkg/server; S=$N/web/site
echo "== persona living_engines"; python3 -c "import json;d=json.load(open('$N/state/persona.json'));print(d.get('living_engines'))"
echo "== chat_core"; ls -la $P/chat_core.py* | head; wc -l $P/chat_core.py; grep -n "_living\|reply_to\|quote\|judge\|8300\|8793\|confidence\|def run_turn\|def _backend\|stream\|def .*backend" $P/chat_core.py | cut -c1-170 | head -70
echo "== site rq"; ls -la $S/nox-chat-rq.* $S/chat.html $S/nox-ghost* 2>&1 | head; grep -c "rq-judge" $S/nox-chat-rq.js; grep -c "rq-judge" $S/nox-chat-rq.css; grep -o "nox-chat-rq[^\"']*" $S/chat.html | head
echo "== judges 8300"; curl -s -m5 localhost:8300/ | head -c 400; echo; curl -s -m5 localhost:8300/health | head -c 300; echo; curl -s -m5 localhost:8300/openapi.json | head -c 600; echo
echo "== judges proc"; ps aux | grep -E "8300|judge" | grep -v grep | cut -c1-220 | head
echo "== advisors 8793"; curl -s -m5 localhost:8793/v1/models | head -c 800; echo
echo "== running llama-swap"; curl -s -m3 localhost:8200/running | head -c 400; echo
echo "== services"; ss -ltn | awk '{print $4}' | grep -E ':(8091|8104|8200|8300|8793|18215|18216|8090)$' | sort -u
echo "== pip libs"; for m in litellm openai httpx aiohttp; do python3 -c "import $m;print('$m',getattr($m,'__version__',''))" 2>&1 | tail -1; done; ls $N/venv* -d 2>/dev/null
echo "== timing /api/turn"; T0=$(date +%s.%N); curl -s -m60 -N -X POST localhost:8091/api/turn -H 'Content-Type: application/json' -d '{"conversation_id":"c_probe1","message":"Сколько будет 12*12?"}' | head -c 900; echo; echo "dt=$(echo "$(date +%s.%N)-$T0"|bc)"
echo "== meta"; curl -s -m5 "localhost:18215/meta?cid=c_probe1" | head -c 400
echo "== webserver turn adapter"; grep -n "api/turn\|api/chat" $P/web_server.py | head
echo "== lastchat tail"; ls $S | head -80
