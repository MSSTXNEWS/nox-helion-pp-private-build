#!/bin/bash
tr '\0' '\n' < /proc/$(pgrep -f "python3 .*gateway.py" | head -1)/environ | grep -E "NOX_UPSTREAM|NOX_FAST|NOX_TWO|NOX_SOUL"
Q='{"messages":[{"role":"user","content":"Объясни по-русски в двух предложениях, что такое оперативная память."}],"max_tokens":80,"stream":false}'
t(){ echo "### $1"; curl -s -m ${3:-100} "$2" -H 'Content-Type: application/json' -d "$Q" -w "\ntime=%{time_total}\n" | python3 -c "
import sys,json;s=sys.stdin.read();i=s.rfind('\ntime=');b=s[:i]
try:
    j=json.loads(b);m=j['choices'][0]['message'];print((m.get('content') or '')[:300]);print('RC:',(m.get('reasoning_content') or '')[:120]);print(j.get('timings',{}).get('predicted_per_second'))
except Exception as e: print('RAW',b[:300])
print(s[i+1:])"; }
t fast http://127.0.0.1:8083/v1/chat/completions 40
t glm8081 http://127.0.0.1:8081/v1/chat/completions 120
t gateway http://127.0.0.1:8082/v1/chat/completions 120
