echo "K1: rs_fix3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; mkdir -p $N/logs
echo "web=$(pgrep -fc web_server.py) img=$(pgrep -fc image_service.py) code8091=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8091/web/chat-dc.html)"
grep -rlE "web_server\.py" $N/ops $N/svc $N/stewards $N/canon_night /etc/supervisor 2>/dev/null | grep -vE "\.bak|\.log" | head -12
grep -rlE "image_service\.py" $N/ops $N/svc $N/stewards $N/canon_night $N/imgsvc /etc/supervisor 2>/dev/null | grep -vE "\.bak|\.log" | head -8
grep -rhE "^[^#]*(nohup|setsid|exec|python)[^#]*web_server\.py" $N/ops $N/svc $N/stewards $N/canon_night 2>/dev/null | grep -v bak | head -5 | cut -c1-260
grep -rhE "^[^#]*(nohup|setsid|exec|python)[^#]*image_service\.py" $N/ops $N/svc $N/stewards $N/canon_night $N/imgsvc 2>/dev/null | grep -v bak | head -5 | cut -c1-260
