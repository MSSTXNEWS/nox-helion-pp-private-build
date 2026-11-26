echo "C300: srv_k97"
D=/workspace/nox/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo
cd $D; cp -n gates_only.py gates_only.py.bak_k1_c5
for f in teacher_dump.py quant4.py chain5.sh gates_only.py; do curl -sfL "$R/$f?cb=$(date +%s)" -o $f.new && mv $f.new $f || echo "FAIL $f"; done
chmod +x chain5.sh; python3 -m py_compile teacher_dump.py quant4.py gates_only.py && bash -n chain5.sh && echo syntax_ok
pgrep -f chain5.sh >/dev/null && echo "уже идёт" || { nohup setsid $D/chain5.sh </dev/null >/dev/null 2>&1 & }
sleep 5; ls -la /workspace/nox/STOP; tail -n 3 $D/run5.log; pgrep -fa "distill_v2.py" | cut -c1-90 | head -3; df -h /workspace | tail -1
