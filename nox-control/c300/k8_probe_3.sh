echo "C300: k8_probe_3"
curl -s -o /dev/null -w "8091 %{http_code}\n" http://127.0.0.1:8091/web/index.html
ps aux | grep -i "web_server\|8091\|uvicorn" | grep -v grep | cut -c1-220 | head
ss -ltnp 2>/dev/null | grep -E "8091|80[0-9][0-9]" | head
ls /workspace/nox | head -40; ls /workspace/nox/web | head -20
grep -rl "web_server.py" /workspace/nox/*.sh /workspace/nox/web/*.sh /etc/supervisor* 2>/dev/null | head
ls /workspace/nox/logs 2>/dev/null | head
echo "K8 probe3 done"
