#!/bin/bash
python3 - <<'P'
s=open('/root/nox/web_server.py',encoding='utf-8').read()
print('NOXHF' in s, len(s))
for k in ('🧠','_deep = '):
    i=s.find(k); print(k, i, ascii(s[max(0,i-60):i+130]) if i>=0 else '')
P
