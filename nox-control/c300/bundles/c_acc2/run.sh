set -x
N=/workspace/nox; W=$N/web/pkg/server; S=$N/web/site; P=$N/svc/pipeline; B=$P/acc2; O=$N/state/c_acc2.out; : > $O
exec >> $O 2>&1
echo "== pipeline v2"; cp -n $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_3; cp $B/pipeline_svc.py $P/pipeline_svc.py
python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || cp $P/pipeline_svc.py.bak_c_3 $P/pipeline_svc.py
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 2; curl -s -m4 localhost:18217/health
echo "== css bundle"; cp $B/nox-chat-c.css $S/nox-chat-c.css; [ -f $S/chat.html.bak_c_css ] || cp -p $S/chat.html $S/chat.html.bak_c_css
grep -q nox-chat-c.css $S/chat.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-chat-c.css?v=c1">\n</head>#' $S/chat.html; grep -c nox-chat-c.css $S/chat.html
echo "== verdict tests"
for t in '{"q":"Какая столица Австралии?","answer":"Столица Австралии — Сидней.","cid":"clow1"}' '{"q":"Кто выиграл чемпионат мира по шахматам в 2086 году?","answer":"Его выиграл Иван Петров.","cid":"clow2"}' '{"q":"Какая столица Австралии?","answer":"Столица Австралии — Канберра.","cid":"clow3"}' '{"q":"Привет","answer":"Привет! Чем могу помочь?","cid":"clow4"}'; do
  timeout 70 curl -s -m65 localhost:18217/verdict -H 'Content-Type: application/json' -d "$t" | cut -c1-600; echo; done
echo "== :8810 probes"
curl -si -m5 localhost:8810/board | head -c 900; echo
curl -s -m5 localhost:8810/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(list(d['paths']))" 2>&1 | head -3
grep -rln "nox-living" $N/svc/*.py $N/svc/*.json $N/web/pkg/server/*.py 2>/dev/null | head
grep -rn "18216" $N/svc/*.json $N/svc/svc_registry* 2>/dev/null | head -3 | cut -c1-300
echo "== qa_audit"; sed -n 1,3p $N/qa_audit.py | cut -c1-200; grep -n "argv\|add_argument\|__main__\|def main" $N/qa_audit.py | head -10; ls -la $S/qa/audit.json; python3 -c "import json;d=json.load(open('$S/qa/audit.json'));print(type(d).__name__, list(d)[:5] if isinstance(d,dict) else len(d)); c=d.get('chat') if isinstance(d,dict) else None; print(json.dumps(c,ensure_ascii=False)[:800])"
echo FINISHED
