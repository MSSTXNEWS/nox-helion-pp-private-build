set -x
N=/workspace/nox; W=$N/web/pkg/server; S=$N/web/site; P=$N/svc/pipeline; B=$P/race1; O=$N/state/c_race1.out; : > $O
exec >> $O 2>&1
echo "== 1. pipeline v3"; cp -n $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_4; cp $B/pipeline_svc.py $P/pipeline_svc.py
python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_4 $P/pipeline_svc.py; echo pc_rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 2; curl -s -m4 localhost:18217/health; echo
echo "== fast probe"; curl -s -m20 localhost:18217/fast -H 'Content-Type: application/json' -d '{"q":"Столица Франции? Одно слово."}' | cut -c1-300; echo
echo "== 2. race patch"; cp -n $W/chat_core.py $W/chat_core.py.bak_c_5
cp $B/c_test.py $P/c_test.py; cp $B/live_ui2.py $P/live_ui2.py
python3 $B/patch_race.py && python3 -m py_compile $W/chat_core.py && echo cc_ok || { cp $W/chat_core.py.bak_c_5 $W/chat_core.py; echo cc_rollback; }
cp $N/state/persona.json $N/state/persona.json.bak_c_5
python3 -c "import json;p='/workspace/nox/state/persona.json';d=json.load(open(p));d['living_engines']=dict(d.get('living_engines') or {},race=True,race_s=7,race_wait=20);json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print(d['living_engines'])"
echo "== 3. site"; cp -p $S/chat.html $S/chat.html.bak_c_race; cp -n $S/nox-chat-rq.js $S/nox-chat-rq.js.bak_c_5
cp $B/nox-chat-wow.js $B/nox-chat-wow.css $B/nox-chat-demo.js $S/; python3 $B/patch_rq2.py
sed -i 's#nox-chat-wow.css?v=[a-z0-9]*#nox-chat-wow.css?v=w2#; s#nox-chat-wow.js?v=[a-z0-9]*#nox-chat-wow.js?v=w2#; s#nox-chat-rq.js?v=[0-9a-z]*#nox-chat-rq.js?v=c3#' $S/chat.html
grep -q nox-chat-demo.js $S/chat.html || sed -i '0,/<head[^>]*>/s##&\n<script src="./nox-chat-demo.js?v=d1"></script>#' $S/chat.html
grep -c "nox-chat-demo\|nox-chat-wow" $S/chat.html
R=$W/svc_registry.json; python3 - <<'PY'
import json
p="/workspace/nox/web/pkg/server/svc_registry.json"; r=json.load(open(p))
r["nox-pipe"]={"port":18217,"mode":"strip","title":"NOX pipeline","ui":False,"note":"POST /feedback (👍/👎 в датасет); внутренние /verdict, /fast"}
json.dump(r,open(p,"w"),ensure_ascii=False,indent=1); print("registered")
PY
( $W/run_web.sh restart </dev/null >/tmp/c_web_restart.log 2>&1 ); sleep 7; tail -1 /tmp/c_web_restart.log
echo "== feedback probe"; curl -s -m5 localhost:8091/svc/nox-pipe/feedback -H 'Content-Type: application/json' -d '{"cid":"ctest","rating":-1,"q":"тест","a":"тест-ответ","note":"проверка"}'; echo; tail -2 $N/state/dataset/feedback.jsonl | cut -c1-200; tail -2 $N/state/lessons_feedback.md
echo "== 3b. сбой черновика"; grep -rn "сбой черновика" $N --include=*.py --include=*.json --include=*.md -l 2>/dev/null | head -5
F=$(grep -rln "сбой черновика" $N/agent $N/core $N/web/pkg 2>/dev/null | head -1); [ -n "$F" ] && grep -n -B6 -A3 "сбой черновика" "$F" | cut -c1-220 | head -40
echo "== 4. live ui (demo, reply)"; $N/venv/bin/python $B/live_ui2.py 2>&1 | tail -12
echo "== 5. race timing, 5 questions (real)"
for q in "Привет, как дела?" "Сколько будет 17*23?" "Назови три столицы Европы" "Объясни простыми словами что такое DNS" "Что лучше для сервера: Python или Go? Коротко"; do timeout 150 python3 $P/c_test.py "$q" crace$RANDOM 140; done
echo "== 5b. forced race (race_s=0.3)"
for q in "Назови пять цветов радуги" "Чем отличается TCP от UDP? Коротко"; do timeout 150 python3 $P/c_test.py "$q" crace$RANDOM 140 '{"race_s":0.3}'; done
echo "== pipe_err"; tail -6 $N/state/pipe_err.log
echo "== 6. qa_audit chat (with demo)"; cp $S/qa/audit.json $S/qa/audit.json.bak_c_5 2>/dev/null
cd $N && timeout 900 $N/venv/bin/python $N/qa_audit.py chat.html | tail -8
python3 -c "
import json;d=json.load(open('$S/qa/audit.json'));c=d.get('chat');print(json.dumps(c,ensure_ascii=False)[:2200])"
echo FINISHED
