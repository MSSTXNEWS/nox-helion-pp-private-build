echo "C300: k_url3"
for p in 3887718 84781; do echo "== pid $p"; for fd in 1 2; do f=$(readlink /proc/$p/fd/$fd); echo "fd$fd -> $f"; [ -f "$f" ] && grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$f" | tail -1; done; done
for u in $(grep -rhoE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp /workspace/nox/state /var/log 2>/dev/null | sort -u); do c=$(curl -s -m 8 -o /dev/null -w "%{http_code}" "$u/web/chat.html"); echo "$u $c"; done
