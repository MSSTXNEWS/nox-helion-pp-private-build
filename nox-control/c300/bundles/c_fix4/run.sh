set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; B=$P/fix4; O=$N/state/c_fix4.out; : > $O; exec >> $O 2>&1
cp $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_fix4; python3 $B/patch_prov.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_fix4 $P/pipeline_svc.py; echo rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/health; echo
cp -n $S/nox-chat-wow.js $S/nox-chat-wow.js.bak_c_fix4; cp $B/nox-chat-wow.js $S/; grep -n "nox-chat-wow.js" $S/chat.html | cut -c1-160
sed -i 's#nox-chat-wow.js?v=[a-z0-9]*#nox-chat-wow.js?v=w4#' $S/chat.html
echo "== /fast x6 прямой"; for q in "Столица Италии?" "Кто открыл закон всемирного тяготения?" "Сколько секунд в минуте?" "Назови столицу Японии" "Какой химический символ у золота?" "Сколько будет 12*12?"; do /bin/bash -c "S=\$(date +%s.%N); curl -s -m20 localhost:18217/fast -d '{\"q\":\"$q\"}' | cut -c1-120; echo \" t=\$(echo \"\$(date +%s.%N)-\$S\" | bc 2>/dev/null)\""; done
curl -s -m3 localhost:18217/quota; echo
echo FINISHED
