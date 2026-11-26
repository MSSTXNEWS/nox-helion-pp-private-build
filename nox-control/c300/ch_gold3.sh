echo "C300: ch_gold3"
cb=$(date +%s); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/golden3.py?cb=$cb" -o /tmp/golden3.py && grep -q ernie /tmp/golden3.py || { echo STALE; exit 0; }
setsid -f python3 /tmp/golden3.py > /workspace/nox/state/ch_golden3.out 2>&1 < /dev/null; echo started
