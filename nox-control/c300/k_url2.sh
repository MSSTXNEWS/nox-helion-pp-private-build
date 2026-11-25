echo "C300: k_url2"
pgrep -af "caddy|cloudflared|tailscale|ngrok|portal" | cut -c1-160
for f in /etc/caddy/Caddyfile /workspace/nox/Caddyfile /workspace/nox/*/Caddyfile; do [ -f $f ] && { echo "== $f"; grep -vE "basicauth|password|hash|\\$2" $f | head -30; }; done
tailscale status 2>/dev/null | head -5; tailscale serve status 2>/dev/null | head; 
ss -ltnp 2>/dev/null | grep -E ":(1111|6006|72299|8080|18091) " | cut -c1-140
grep -rhoE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp /workspace/nox/state /var/log 2>/dev/null | sort -u | tail -3
