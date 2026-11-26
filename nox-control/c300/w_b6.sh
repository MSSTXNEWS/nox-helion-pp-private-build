echo "C300: w_b6"
CF=/workspace/nox/ops/web_chat_auth/Caddyfile
grep -n -i -E '503|S2|respond|/api/|@' $CF | grep -v -i -E 'hash|pass|token|secret|\$2' | cut -c1-200
grep -c nox_api_bridge $CF
grep -n -i 'api/settings\|training/status\|nox/activity' /workspace/nox/web/web_server.py 2>/dev/null | head -8 | cut -c1-200
