#!/bin/bash
B=/root/nox/llama.cpp-f/build/bin/llama-server
$B --help 2>&1 | grep -iE -A1 'reasoning|think' | cut -c1-200 | head -14
for i in $(seq 90); do curl -sf localhost:8081/health >/dev/null && break; sleep 3; done
cat > /tmp/rt.py <<'PY'
import json,urllib.request,sys
def q(extra,label):
    d={'messages':[{'role':'user','content':'Сколько будет 17*23? Ответь коротко.'}],'max_tokens':150,'temperature':0}; d.update(extra)
    try:
        o=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',json.dumps(d).encode(),{'Content-Type':'application/json'}),timeout=400))
        m=o['choices'][0]['message']; print(label,'| fin=',o['choices'][0]['finish_reason'],'| content=',repr((m.get('content') or '')[:120]),'| reasoning=',repr((m.get('reasoning_content') or '')[:80]),'| toks=',o['usage']['completion_tokens'])
    except Exception as e: print(label,'ERR',repr(e)[:150])
q({},'default')
q({'chat_template_kwargs':{'enable_thinking':False}},'kwargs_false')
q({'reasoning_budget':0},'budget0')
PY
python3 /tmp/rt.py
curl -s localhost:8081/props | python3 -c "import sys,json;d=json.load(sys.stdin);t=d.get('chat_template','');print('tmpl_len',len(t),'think' in t, [x for x in ('enable_thinking','<think>','</think>','/nothink') if x in t])"
ps -eo args | grep '[l]lama-server.*8081' | grep -o 'reasoning[^ ]* [^ ]*\|--chat-template[^ ]* [^ ]*' 
