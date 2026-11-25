echo S4RUN:s6_p20
ss -ltnp 2>/dev/null | grep -E ":(80|8091|8080|8000|8300|8200)\b" | cut -c1-120
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/web/music.html
ps aux | grep -E "web_server|http.server|nox" | grep -v grep | cut -c1-160 | head -5
