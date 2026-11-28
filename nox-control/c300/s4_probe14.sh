N=/workspace/nox
echo "S4P14 $(date +%F_%H:%M)"
supervisorctl status 2>/dev/null | grep -i -E "tunnel|caddy|gate|sidecar|voice|web|chat|owner" | cut -c1-120
echo "## listen"; ss -ltnp 2>/dev/null | grep -E ":(18092|18091|18797|8400|8091|8080|8104) " | awk '{print $4,$6}' | cut -c1-120
echo "## tunnel procs"; ps -eo pid,etimes,args | grep -i -E "cloudflared|tunnel|ngrok|localtunnel|trycloudflare" | grep -v grep | cut -c1-260 | head
echo "## tunnel files"; ls $N/state/core | grep -i -E "url|tunnel|public"; ls $N/state | grep -i -E "tunnel|url|public" | head; find $N -maxdepth 3 -iname "*tunnel*" -not -path "*/venv*" 2>/dev/null | head -12
for f in $N/state/core/public_url.json $N/state/public_url* $N/state/tunnel_url*; do [ -f $f ] && { echo "### $f"; head -c 400 $f; echo; }; done
echo "## tunnel_manager"; F=$(find $N /etc/supervisor -iname "*tunnel_manager*" -not -path "*/venv*" 2>/dev/null | head -3); echo "$F"; for f in $F; do echo "### $f"; head -c 2500 $f | cut -c1-220; done
echo "## supervisor tunnel conf"; grep -rl -i tunnel /etc/supervisor/conf.d 2>/dev/null | head; for f in $(grep -rl -i tunnel /etc/supervisor/conf.d 2>/dev/null | head -3); do echo "## $f"; head -12 $f | cut -c1-200; done
