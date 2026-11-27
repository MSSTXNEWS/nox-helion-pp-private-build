echo "K1: v1_02r"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "OWNER_ACTIVE age $(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE 2>/dev/null || echo 0) ))"
echo "--- chromium roots"
for p in $(pgrep -f chrome-headless-shell | head -40); do pp=$(ps -o ppid= -p $p | tr -d ' '); echo "$pp"; done | sort | uniq -c | sort -rn | head -5
for p in $(pgrep -f "chrome-headless-shell" | head -3); do a=$p; for i in 1 2 3 4 5 6; do a=$(ps -o ppid= -p $a | tr -d ' '); [ -z "$a" -o "$a" = 1 ] && break; echo "anc $a: $(ps -o etimes=,args= -p $a | cut -c1-170)"; done; echo; done
echo "--- node/python playwright procs"
ps -eo pid,ppid,etimes,args | grep -E "playwright|node .*(driver|run)|python.*(qa|shot)" | grep -v grep | cut -c1-200 | head -10
echo "--- body_restart.sh"
cat $N/ops/body_restart.sh | cut -c1-220 | head -40
ls $N/ops | grep -i -E "body|8104" | head
echo END
