#!/bin/bash
# c86: read-only: достижим ли ПК (Tailscale 100.84.111.36:8765), RAM под тёплые веса
echo "== tailscale"; (command -v tailscale && tailscale status 2>&1 | head -5) || echo "tailscale: не установлен на сервере"
echo "== route/tun"; ip -o addr 2>/dev/null | grep -E "tailscale|100\." | head -3 || true
echo "== pc http"; curl -sS -m 6 -o /dev/null -w "http=%{http_code}\n" http://100.84.111.36:8765/ 2>&1 | tail -1
echo "== ram"; free -g | sed -n 1,2p; df -h /dev/shm | tail -1
