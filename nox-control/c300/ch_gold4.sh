echo "C300: ch_gold4"
cb=$(date +%s); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/golden4.py?cb=$cb" -o /tmp/golden4.py && grep -q "done=set" /tmp/golden4.py || { echo STALE; exit 0; }
setsid -f python3 /tmp/golden4.py > /workspace/nox/state/ch_golden4.out 2>&1 < /dev/null; echo started
echo "== scheduler recon"; N=/workspace/nox; ls $N | head -40; ls $N/agent 2>/dev/null | head -30
grep -rln "nox_agents" $N/*.json $N/agent/*.json $N/state/*.json 2>/dev/null | head -5
pgrep -af "nox_agents" | cut -c1-140 | head -4
