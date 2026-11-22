#!/bin/bash
B=/root/nox/llama.cpp-f/build/bin/llama-server
$B --help 2>&1 | grep -A6 -- '--reasoning-effort' | cut -c1-160 | head -9
curl -s localhost:8081/props | python3 -c "
import sys,json,re;t=json.load(sys.stdin)['chat_template']
for m in re.finditer(r'.{90}(enable_thinking|nothink|thinking|reasoning_effort|<think>).{90}',t.replace('\n',' ')): print(m.group(0)[:200]); 
" | head -8
cat > /tmp/rt2.py <<'PY'
import json,urllib.request
def q(extra,label,umsg='Сколько будет 17*23? Ответь коротко.'):
    d={'messages':[{'role':'user','content':umsg}],'max_tokens':60,'temperature':0}; d.update(extra)
    try:
        o=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',json.dumps(d).encode(),{'Content-Type':'application/json'}),timeout=150))
        m=o['choices'][0]['message']; print(label,'| fin=',o['choices'][0]['finish_reason'],'| c=',repr((m.get('content') or '')[:50]),'| r=',repr((m.get('reasoning_content') or '')[:40]),'| n=',o['usage']['completion_tokens'])
    except Exception as e: print(label,'ERR',repr(e)[:100])
q({'chat_template_kwargs':{'enable_thinking':False}},'enable_thinking=false')
q({'chat_template_kwargs':{'thinking':False}},'thinking=false')
q({'reasoning_effort':'none'},'effort_none')
q({'chat_template_kwargs':{'reasoning_effort':'none'}},'kw_effort_none')
q({},'nothink_suffix','Сколько будет 17*23? Ответь коротко. /nothink')
PY
timeout 240 python3 /tmp/rt2.py
