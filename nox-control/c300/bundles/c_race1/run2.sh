set -x
N=/workspace/nox; W=$N/web/pkg/server; S=$N/web/site; P=$N/svc/pipeline; B=$P/race3; O=$N/state/c_race3.out; : > $O
exec >> $O 2>&1
for i in $(seq 1 70); do pgrep -f qa_audit.py >/dev/null || break; sleep 10; done
echo "== audit status from race1 run"; tail -c 1800 $N/state/c_race1.out
echo "== deploy v4: quota/breaker + stage events"
cp $B/pipeline_svc.py $P/pipeline_svc.py; python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_4 $P/pipeline_svc.py; echo pc_rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 2; curl -s -m4 localhost:18217/quota; echo
python3 $B/patch_race2.py && python3 -m py_compile $W/chat_core.py && echo cc_ok || { cp $W/chat_core.py.bak_c_5 $W/chat_core.py; echo cc_rollback; }
cp $B/nox-chat-wow.js $S/; sed -i 's#nox-chat-wow.js?v=[a-z0-9]*#nox-chat-wow.js?v=w3#' $S/chat.html
( $W/run_web.sh restart </dev/null >/tmp/c_web_restart.log 2>&1 ); sleep 7; tail -1 /tmp/c_web_restart.log
echo "== forced race x2 (race_s=0.3), degradation expected if pool limited"
for q in "Назови пять цветов радуги" "Чем отличается TCP от UDP? Коротко"; do timeout 150 python3 $P/c_test.py "$q" crace$RANDOM 140 '{"race_s":0.3}'; done
curl -s -m4 localhost:18217/quota; echo
echo FINISHED
