echo "K1: rs_img4"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; mkdir -p $N/logs
if [ "$(pgrep -fc image_service.py)" = "0" ]; then
  (cd $N/imgsvc && env -u RUNNER_TRACKING_ID setsid -f nohup $N/venv/bin/python -I image_service.py >>$N/logs/imgsvc.log 2>&1 </dev/null)
fi
sleep 25
echo "img_proc=$(pgrep -fc image_service.py) web=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:18091/web/chat-v1d.html)"
tail -5 $N/logs/imgsvc.log | grep -iE "error|traceback|listen|running|port" | cut -c1-160
t0=$(date +%s); C=$(curl -s -o /tmp/img.json -m 150 -w %{http_code} -H 'Content-Type: application/json' -d '{"prompt":"a cat in a spacesuit, cinematic","width":768,"height":768,"user_id":"qa-img"}' http://127.0.0.1:18091/img/generate); t1=$(date +%s)
echo "img_generate code=$C sec=$((t1-t0)) keys=$(python3 -c "import json;print(','.join(json.load(open('/tmp/img.json')).keys()))" 2>/dev/null)"
