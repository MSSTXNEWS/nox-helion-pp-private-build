#!/bin/bash
# Подключает сервер NOX к частной сети Tailscale (userspace, без TUN). Ключ приходит через stdin и не печатается.
read -r K
[ -z "$K" ] && { echo "NO_KEY: добавь секрет TS_AUTHKEY в GitHub и запусти ещё раз"; exit 0; }
V=1.78.1
if [ ! -x /opt/tailscale/tailscale ]; then
  mkdir -p /opt/tailscale && cd /opt/tailscale
  curl -fsSL -m 120 "https://pkgs.tailscale.com/stable/tailscale_${V}_amd64.tgz" -o ts.tgz || { echo "DOWNLOAD_FAILED"; exit 0; }
  tar xzf ts.tgz --strip-components=1 && rm -f ts.tgz
fi
cat > /etc/supervisor/conf.d/nox-tailscaled.conf <<'EOF'
[program:nox-tailscaled]
command=/opt/tailscale/tailscaled --tun=userspace-networking --socks5-server=127.0.0.1:1055 --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscaled.sock
autostart=true
autorestart=true
stdout_logfile=/root/nox/logs/tailscaled.log
stderr_logfile=/root/nox/logs/tailscaled.log
EOF
mkdir -p /var/lib/tailscale
supervisorctl reread >/dev/null; supervisorctl update >/dev/null; sleep 5
/opt/tailscale/tailscale --socket=/var/run/tailscaled.sock up --authkey="$K" --hostname=nox-server --accept-dns=false 2>&1 | sed 's/tskey-[A-Za-z0-9-]*/***/g' | tail -3
/opt/tailscale/tailscale --socket=/var/run/tailscaled.sock status 2>&1 | head -8
