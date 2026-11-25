echo "C300: k_draw_chk2"
T0=$(date +%s)
curl -s -m 280 -X POST http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"нарисуй кота в космосе"}],"conversation_id":"drawtest2"}' | head -c 1200
echo; echo "secs $(( $(date +%s)-T0 ))"
ls -t /workspace/nox/state/advisor_images 2>/dev/null | head -3
