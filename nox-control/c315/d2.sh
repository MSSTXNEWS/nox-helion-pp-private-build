#!/bin/bash
/root/nox/llama.cpp-f/build/bin/llama-server --help 2>&1 | grep -a -i -A2 -E "reasoning|think" | cut -c1-200 | head -30
curl -s http://127.0.0.1:8081/props | python3 -c "
import sys,json,re
d=json.load(sys.stdin); t=d.get('chat_template','')
print(len(t)); 
for m in re.finditer(r'.{80}(enable_thinking|nothink|thinking|<think>).{80}',t,re.S): print(repr(m.group(0)))
" | head -14
