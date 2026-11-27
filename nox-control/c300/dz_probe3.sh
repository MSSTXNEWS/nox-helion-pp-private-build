echo "K1: dz_probe3"
W=/workspace/nox/web/pkg/server
echo "--- mode in chat_core"; grep -nE "\"mode\"|'mode'|\bmode ==|mode in|deep|\"fast\"" $W/chat_core.py | cut -c1-200 | head -30
echo "--- mode in web_server"; grep -nE "mode" $W/web_server.py | cut -c1-180 | head -12
for u in api/chat/health svc/nox-living/status svc/nox-living/quiet api/nox/outbox "svc/advisors/draft?typed=при&chat=" svc/nox-mem/health svc/nox-mem/list "svc/nox-mem/search?q=test" api/feedback svc/nox-living/incognito api/nox/self_now; do echo "GET $u $(curl -s -m 5 -o /tmp/p3.out -w '%{http_code} %{size_download}' "http://127.0.0.1:18091/$u") $(head -c 140 /tmp/p3.out | tr '\n' ' ')"; done
