cd /workspace/nox/web/site; touch qa/rework/chat.fixed
sed -n '12,60p' studio.html | cut -c1-500
I=127.0.0.1:8091/svc/invoke
for u in /api/v1/app/version /api/v1/queue/default/status /api/v1/models/?model_type=main /api/v1/boards/?all=true; do echo "-- $u"; curl -s -m 10 $I$u | head -c 700; echo; done
curl -s -m 5 127.0.0.1:8091/svc/invoke/ | head -c 300
