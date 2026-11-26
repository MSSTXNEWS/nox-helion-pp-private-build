echo "C300: srv_k109"
D=/workspace/nox/ops/dpo; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo
pkill -9 -f "ops/dpo/chain5.sh"; sleep 1; ls /workspace/nox/STOP || touch /workspace/nox/STOP
curl -sfL "$R/chain5.sh?cb=$(date +%s)" -o $D/chain5.sh && chmod +x $D/chain5.sh && bash -n $D/chain5.sh && echo deployed
pgrep -af "venv/bin/python.* distill_v2.py (gen|judge|prep|train)" | cut -c1-100
nohup setsid $D/chain5.sh </dev/null >/dev/null 2>&1 &
sleep 40; cat $D/run5.log | tail -5; pgrep -fa "teacher_dump|port 8199" | cut -c1-100
