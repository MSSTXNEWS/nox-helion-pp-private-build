#!/bin/bash
N=/workspace/nox; F=$N/qa_audit.py; D=$(date +%Y%m%d_%H%M%S)
echo "== after-8106 final"; tail -4 $N/state/p3/after_8106.txt
cp -p $F $F.bak_p3_$D
python3 - "$F" <<'PY'
import sys,re
p=sys.argv[1]; s=open(p).read(); ch=[]
if '"max_tokens": 3500' in s: s=s.replace('"max_tokens": 3500','"max_tokens": 1000'); ch.append("max_tokens 3500->1000")
if "P3_QA_LOCK" not in s:
    m=re.search(r"^import [^\n]*\n",s,re.M)
    s=s[:m.end()]+"import fcntl as _fc  # P3_QA_LOCK: один qa_audit за раз (слоты 8104 нужны чату)\n_QL=open('/tmp/qaa.lock','w'); _fc.flock(_QL,_fc.LOCK_EX)\n"+s[m.end():]; ch.append("flock /tmp/qaa.lock")
open(p,"w").write(s); print("patched:",ch)
PY
/workspace/nox/venv/bin/python -m py_compile $F && echo "syntax ok" || { cp -p $F.bak_p3_$D $F; echo "ROLLED BACK"; }
echo "== kill qa_audit older than 600s that hold vision calls (stale)"
for p in $(pgrep -f "qa_audit.py"); do e=$(ps -o etimes= -p $p | tr -d ' '); [ "${e:-0}" -gt 600 ] && { echo "kill $p age=$e"; kill $p; }; done
sleep 20
echo "== slots now"; curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print('busy',sum(1 for s in json.load(sys.stdin) if s['is_processing']),'/3')"
echo "== clients"; ss -Htnp state established '( dport = :8104 )' | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c
echo "== TTFT x3"; python3 /tmp/p3_t.py; python3 /tmp/p3_t.py; python3 /tmp/p3_t.py
echo "load $(cut -d' ' -f1-3 /proc/loadavg) $(free -m | sed -n 2p) st8104=$(ps -o stat= -p $(pgrep -f 'port 8104'|head -1))"
