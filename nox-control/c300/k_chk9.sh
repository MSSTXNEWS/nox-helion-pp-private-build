echo "C300: k_chk9"
for u in /web/chat.html /web/index.html /web/sw.js; do
 for port in 8091 18091; do curl -s -m 8 -D /tmp/h http://127.0.0.1:$port$u -o /tmp/b; echo "== $port$u $(head -1 /tmp/h) size=$(wc -c </tmp/b)"; grep -i "cache-control\|etag\|last-mod" /tmp/h; done
 grep -o 'data-nox-theme="[a-z]*"\|nox-chat-clean[^"]*\|nox-theme.js[^"]*\|CACHE[A-Z_]*\s*=\s*[^;]*\|nox-s1-v[^"'"'"']*' /tmp/b | sort -u | head -8
done
ls -la --time-style=+%m-%d_%H:%M /workspace/nox/web/site/nox-theme.js /workspace/nox/web/site/chat.html 2>/dev/null; ls -la /workspace/nox/web/ | head -5
grep -o "trycloudflare[^ ]*" /workspace/nox/state/*tunnel* /workspace/nox/agent/out/*cloudflared* 2>/dev/null | tail -3; ps -eo args | grep [c]loudflared | head -2
cat /workspace/nox/web/Caddyfile 2>/dev/null | head -30; ls /workspace/nox/state/web_auth_off
