echo "C300: u_rec4"
S=/workspace/nox/web/site; cd $S
echo "== 8080 https"; curl -sk -m 8 -o /dev/null -w "%{http_code}\n" https://localhost:8080/web/index.html; curl -sk -m 8 -o /dev/null -w "svc %{http_code}\n" https://localhost:8080/svc/advgw/health
echo "== Caddyfile"; grep -n "8091\|18091\|basicauth\|forward_auth\|nox_web\|handle\|reverse_proxy\|:8080\|:1" /etc/Caddyfile | cut -c1-180 | head -40
echo "== chat5 sys col"; grep -n "sys\b\|cx5-sys\|cx-right" nox-chat-5.js | cut -c1-230 | head -20
