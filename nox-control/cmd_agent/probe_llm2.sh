#!/bin/bash
echo "== full args"; tr '\0' ' ' < /proc/3266857/cmdline | sed 's#/root/nox/models/deepseek_v41_flash_iq2xxs/##g' | cut -c150-1200; echo
echo "== supervisor"; grep -l 8098 /etc/supervisor/conf.d/*.conf 2>/dev/null | head -3
F=$(grep -l 8098 /etc/supervisor/conf.d/*.conf 2>/dev/null | head -1); [ -n "$F" ] && grep -E "^(\[program|command|autostart|autorestart)" "$F" | cut -c1-200
echo "== speed now"; curl -s -m 120 http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Count from 1 to 60 separated by commas."}],"max_tokens":200}' | python3 -c "import sys,json;d=json.load(sys.stdin);t=d.get('timings',{});print('gen tok/s',round(t.get('predicted_per_second',0),1),'prompt tok/s',round(t.get('prompt_per_second',0),1),'n',t.get('predicted_n'))"
echo "== slots"; curl -s -m 5 http://127.0.0.1:8098/slots | python3 -c "import sys,json;d=json.load(sys.stdin);print([ (s.get('id'),s.get('n_ctx'),s.get('is_processing')) for s in d])" 2>&1 | cut -c1-200
