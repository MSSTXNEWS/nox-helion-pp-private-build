echo "K1: ln_t9"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=$N/web/pkg/webroot; now=$(date +%s)
echo "== no minichat pages"; for f in $(cd $R; ls *.html); do grep -qiE "mini-?chat|nox-mini|noxMini" $R/$f || echo -n "$f "; done; echo
echo "== inner runner"; P=$(pgrep -f "inner_runner.py" | head -1); ls -l /proc/$P/fd 2>/dev/null | grep -E "\.log|\.jsonl" | sed 's/.*-> //' | head -3
for f in $(ls -l /proc/$P/fd 2>/dev/null | grep -E "\.log|\.jsonl" | sed 's/.*-> //' | head -3); do echo "$f age=$(( now-$(stat -c %Y $f) ))s"; tail -n 300 $f | grep -ciE "fail|error|отказ|traceback|exception" | sed 's/^/err_last300=/'; done
find $N -maxdepth 4 -name 'inner_runner.py' | head -2; find $N/logs $N/state -maxdepth 3 -iname '*inner*' -mmin -120 2>/dev/null | head -5
echo "== thoughts/outbox files"; find $N/state -maxdepth 2 \( -name 'thoughts*' -o -name 'outbox*' \) -mmin -240 | head -4
echo "== worms"; curl -s -m8 127.0.0.1:8810/worms/agenda | head -c 160; echo; curl -s -m8 127.0.0.1:8810/worms/status | head -c 200; echo; pgrep -af "worm" | cut -c1-110 | head -5
ls -t $N/state/worms* $N/state/agents/logs/worm* 2>/dev/null | head -3
echo "== dispatcher"; pgrep -af "dispatcher" | cut -c1-110 | head -5; tail -2 $N/dispatcher_journal.md | cut -c1-200
echo "== vision"; grep -niE "vl|vision|mmproj|llava|minicpm" $N/serve/llama-swap.yaml | head -6 | cut -c1-140
ls $N/models 2>/dev/null | grep -iE "vl|vision|llava|minicpm|florence|moondream" | head
echo "== secrets scan (counts)"
for pat in 'ghp_[A-Za-z0-9]{20,}' 'github_pat_[A-Za-z0-9_]{20,}' 'sk-[A-Za-z0-9]{24,}' 'hf_[A-Za-z0-9]{30,}' 'AKIA[0-9A-Z]{16}' 'BEGIN [A-Z ]*PRIVATE KEY' 'trycloudflare\.com' '\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{40,}'; do w=$(grep -rEl "$pat" $R 2>/dev/null | wc -l); g=$(grep -rEl "$pat" /workspace/nox/agent/out/*.log 2>/dev/null | wc -l); r=$(cd /tmp; git -C /home/claude 2>/dev/null; echo -); echo "$pat webroot_files=$w agent_out_logs=$g"; done
echo "== living incognito"
L=127.0.0.1:18091/svc/nox-living; C=lt$RANDOM
n0=$(curl -s -m8 "$L/mem/list?n=100000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['items']))")
curl -s -m8 -X POST $L/incognito -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"on\":true}" | head -c 60; echo
curl -s -m20 -X POST $L/post -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"text\":\"запомни: мой тайный пароль от сейфа это тестовый-инкогнито-9917\",\"answer\":\"хорошо запомнил\",\"incognito\":true}" | head -c 120; echo
sleep 3; n1=$(curl -s -m8 "$L/mem/list?n=100000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['items']))"); echo "living mem before=$n0 after_incognito_post=$n1"
curl -s -m8 -X POST $L/incognito -H 'Content-Type: application/json' -d "{\"cid\":\"$C\",\"on\":false}" | head -c 40; echo
