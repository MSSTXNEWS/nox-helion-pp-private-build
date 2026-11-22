#!/bin/bash
Q="расскажи в двух словах чем ты отличаешься от обычного чат-бота"
ask() { curl -s -m 150 -H 'content-type: application/json' -H 'x-nox-conversation: c400-cache' -d "$(python3 -I -c 'import json,sys;print(json.dumps({"messages":[{"role":"user","content":sys.argv[1]}],"max_tokens":200}))' "$Q")" http://127.0.0.1:8090/v1/chat/completions | python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d["nox"]["path"],"|",d["choices"][0]["message"]["content"][:150].replace("\n"," "),"|",d["nox"]["trace"])'; }
echo A1: $(ask); sleep 6
echo A2: $(ask)
T=$(ask | grep -o '/v1/core/trace/[^ ]*' | head -1); sleep 1
curl -s -m5 localhost:8090/health | python3 -I -c 'import json,sys;print("opt",json.load(sys.stdin)["opt"])'
cd /root/nox/repo/nox-control/wow7/brain && NOX_STATE=/tmp python3 -I - <<'PY'
import sys; sys.path.insert(0,'.')
import optlayer as OL
o=OL.OptLayer('/tmp/c400_judge_t')
print('judge busy?',OL.BJ.judge_busy(o.judge_url))
p=o.judge_sync("Столица Франции?","Столица Франции - Париж.","Столица Франции - Лион.")
print('judge p(cached better)=',p,o.stats)
PY
