echo "K1: q27a_re"
export RUNNER_TRACKING_ID=""
for i in $(seq 1 40); do c=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8104/health); [ "$c" = 200 ] && break; sleep 10; done; echo "8104=$c waited=$i"
[ "$c" = 200 ] || { echo END; exit 0; }
sleep 20
echo "md5 $(md5sum < /workspace/nox/web/pkg/server/chat_core.py | cut -c1-32)"
python3 /tmp/q27a_t.py 2>&1 | grep -E "^(DISTINCT|TOTAL|GREET_LATER|BAD|JF |NOW_|SELF_)" | cut -c1-160
echo END
