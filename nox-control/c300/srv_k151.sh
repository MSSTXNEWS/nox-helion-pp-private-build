echo "C300: srv_k151"
cd /workspace/nox/web/pkg/server
sed -n 497,545p chat_core.py | cut -c1-300
echo ===; grep -n "^def \(draw_request\|stage_level\|_le\b\|_le_num\)" chat_core.py | head
