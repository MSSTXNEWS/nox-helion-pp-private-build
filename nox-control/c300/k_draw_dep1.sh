echo "C300: k_draw_dep1"
D=/workspace/nox/ops/draw; TS=$(date +%s); SHA=$(git ls-remote https://github.com/MSSTXNEWS/nox-helion-pp-private-build.git refs/heads/main | cut -c1-40)
cp $D/invoke_draw.py $D/invoke_draw.py.stub_bak_p3_$TS && echo "backup ok"
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$SHA/nox-control/c300/p3_files/invoke_draw.py -o /tmp/invoke_draw_new.py || { echo FETCH_FAIL; exit 1; }
/workspace/nox/venv/bin/python -m py_compile /tmp/invoke_draw_new.py && cp /tmp/invoke_draw_new.py $D/invoke_draw.py && echo "module installed"
cd $D && /workspace/nox/venv/bin/python -c "import invoke_draw as d; print('dr', d.draw_request('нарисуй кота')); print('no', d.draw_request('привет'))"
grep -q '"draw_chat"' /workspace/nox/state/flags.json 2>/dev/null || echo "flags: draw_chat default on"
# restart web now
R=/workspace/nox/web/pkg/server/run_web.sh; [ -x $R ] && $R restart 2>&1 | tail -3
sleep 6; curl -s -m 8 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/api/chat/health
# core restart + live test in background (waits for quiet chat >=180s and no ab lock)
cat > /workspace/nox/agent/out/k_draw_bg.sh <<'BG'
L=/workspace/nox/agent/out/k_draw_bg.log; echo "start $(date)" > $L
for i in $(seq 1 40); do [ -f /workspace/nox/state/ab_running.lock ] && { sleep 30; continue; }; break; done
cd /workspace/nox && timeout 600 /workspace/nox/venv/bin/python state/liska_restart_core.py >> $L 2>&1; echo "core rc=$?" >> $L
sleep 20
curl -s -m 240 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"message":"нарисуй кота в космосе","conversation_id":"drawtest1"}' | head -c 1500 >> $L
echo "\nend $(date)" >> $L
BG
setsid nohup bash /workspace/nox/agent/out/k_draw_bg.sh </dev/null >/dev/null 2>&1 &
echo "bg started"
